# Version 1.3
#!/usr/bin/env python3
# sCMD — dual-pane DOS-style file commander for SharkDeck.

# Stdlib only. Run:  python3 scmd.py [path]
# Config: ~/.scmd.menu   ~/.scmd.jumps


from __future__ import annotations

import curses
import curses.textpad
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime

NAME = "sCMD"
MENU_FILE = os.path.expanduser("~/.scmd.menu")
JUMP_FILE = os.path.expanduser("~/.scmd.jumps")
START = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()))

SORTS = ("name", "size", "date")


def fmt_size(n: int) -> str:
    n = int(n)
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f}K"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}M"
    return f"{n / (1024 * 1024 * 1024):.1f}G"


def disk_free(path: str) -> str:
    try:
        u = shutil.disk_usage(path)
        return f"free {fmt_size(u.free)}/{fmt_size(u.total)}"
    except OSError:
        return "free ?"


def first_existing(paths: list[str]) -> str | None:
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    return None


def default_jumps() -> list[tuple[str, str]]:
    rows = [
        ("home", os.path.expanduser("~")),
        ("work", "/home/working/SharkDeck/SharkDeck"),
        ("led", "/home/working/SharkDeck/SharkDeck/led"),
        ("drop", "/home/working/SharkDeck/SharkDeck/drop"),
        ("cmd", "/home/working/SharkDeck/SharkDeck/cmd"),
        ("tmp", "/tmp"),
        ("root", "/"),
        ("sd", "/media"),
    ]
    return [(n, p) for n, p in rows if os.path.isdir(p)]


def load_jumps() -> list[tuple[str, str]]:
    if not os.path.exists(JUMP_FILE):
        return default_jumps()
    out = []
    with open(JUMP_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, path = line.split("|", 1)
            path = os.path.expanduser(path.strip())
            if os.path.isdir(path):
                out.append((name.strip(), path))
    return out or default_jumps()


def default_menu_text() -> str:
    drop = first_existing(
        [
            "/home/working/SharkDeck/SharkDeck/drop/sharkdrop.py",
            "/home/working/SharkDeck/SharkDeck/led/../drop/sharkdrop.py",
        ]
    )
    led = first_existing(["/home/working/SharkDeck/SharkDeck/led/sharkledger.py"])
    lines = [
        "# sCMD user menu — label|command",
        "# tokens: %p pane dir   %f file   %d other pane dir   %n filename",
        "shell here|bash",
    ]
    if drop:
        lines.append(f"SharkDrop this dir|python3 {drop} start %p")
    if led:
        lines.append(f"SharkLedger log|python3 {led} log")
    lines.append("chmod +x current|chmod +x %f")
    usb = first_existing(["/dev/ttyUSB0", "/dev/ttyACM0"])
    if usb:
        lines.append(f"push file to pico|sh -c 'cat %f > {usb}'")
    return "\n".join(lines) + "\n"


def load_menu() -> list[tuple[str, str]]:
    if not os.path.exists(MENU_FILE):
        try:
            with open(MENU_FILE, "w", encoding="utf-8") as fh:
                fh.write(default_menu_text())
        except OSError:
            pass
    path = MENU_FILE if os.path.exists(MENU_FILE) else None
    text = open(path, encoding="utf-8").read() if path else default_menu_text()
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        label, cmd = line.split("|", 1)
        out.append((label.strip(), cmd.strip()))
    return out


def list_dir(path: str, hidden: bool, sort: str) -> list[dict]:
    parent = os.path.dirname(path) or path
    out = [{"name": "..", "path": parent, "dir": True, "size": 0, "mtime": 0}]
    try:
        names = os.listdir(path)
    except OSError:
        return out
    for name in names:
        if not hidden and name.startswith("."):
            continue
        full = os.path.join(path, name)
        try:
            st = os.lstat(full)
        except OSError:
            continue
        is_dir = stat.S_ISDIR(st.st_mode)
        out.append(
            {
                "name": name + ("/" if is_dir else ""),
                "path": full,
                "dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
            }
        )
    def key(e: dict):
        if e["name"] == "..":
            return (0, 0, "")
        if sort == "size":
            return (1, 0 if e["dir"] else 1, -e["size"], e["name"].lower())
        if sort == "date":
            return (1, 0 if e["dir"] else 1, -e["mtime"], e["name"].lower())
        return (1, 0 if e["dir"] else 1, e["name"].lower())

    out.sort(key=key)
    return out


class Pane:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.cursor = 0
        self.scroll = 0
        self.marks: set[str] = set()
        self.hidden = False
        self.filter = ""
        self.sort = "name"
        self.entries: list[dict] = []
        self.reload()

    def reload(self) -> None:
        keep = self.current_path() if self.entries else None
        rows = list_dir(self.path, self.hidden, self.sort)
        if self.filter:
            q = self.filter.lower()
            rows = [e for e in rows if e["name"] == ".." or q in e["name"].lower()]
            if not any(e["name"] == ".." for e in rows):
                parent = os.path.dirname(self.path) or self.path
                rows.insert(0, {"name": "..", "path": parent, "dir": True, "size": 0, "mtime": 0})
        self.entries = rows
        self.marks &= {e["path"] for e in self.entries}
        if keep:
            for i, e in enumerate(self.entries):
                if e["path"] == keep:
                    self.cursor = i
                    break
        self.cursor = max(0, min(self.cursor, max(0, len(self.entries) - 1)))

    def current(self) -> dict:
        if not self.entries:
            return {"name": "..", "path": self.path, "dir": True, "size": 0, "mtime": 0}
        return self.entries[self.cursor]

    def current_path(self) -> str:
        return self.current()["path"]

    def marked_or_current(self) -> list[dict]:
        marked = [e for e in self.entries if e["path"] in self.marks and e["name"] != ".."]
        if marked:
            return marked
        cur = self.current()
        if cur["name"] == "..":
            return []
        return [cur]

    def toggle_mark(self) -> None:
        e = self.current()
        if e["name"] == "..":
            return
        if e["path"] in self.marks:
            self.marks.discard(e["path"])
        else:
            self.marks.add(e["path"])
        self.move(1)

    def move(self, delta: int) -> None:
        if not self.entries:
            return
        self.cursor = max(0, min(len(self.entries) - 1, self.cursor + delta))

    def page(self, h: int, direction: int) -> None:
        self.move(direction * max(1, h - 2))

    def enter(self) -> None:
        e = self.current()
        if not e["dir"]:
            return
        if e["name"] == "..":
            self.parent()
            return
        self.path = os.path.abspath(e["path"])
        self.cursor = 0
        self.scroll = 0
        self.marks.clear()
        self.filter = ""
        self.reload()

    def parent(self) -> None:
        old = self.path
        parent = os.path.dirname(self.path) or self.path
        if parent == self.path:
            return
        self.path = parent
        self.filter = ""
        self.reload()
        for i, row in enumerate(self.entries):
            if row["path"] == old:
                self.cursor = i
                break

    def jump(self, path: str) -> None:
        if not os.path.isdir(path):
            return
        self.path = os.path.abspath(path)
        self.cursor = 0
        self.scroll = 0
        self.filter = ""
        self.marks.clear()
        self.reload()


class App:
    def __init__(self, stdscr, left: str, right: str):
        self.stdscr = stdscr
        self.panes = [Pane(left), Pane(right)]
        self.active = 0
        self.msg = ""
        self.msg_err = False
        self.preview = False

    @property
    def pane(self) -> Pane:
        return self.panes[self.active]

    @property
    def other(self) -> Pane:
        return self.panes[1 - self.active]

    def say(self, text: str, err: bool = False) -> None:
        self.msg = text[:80]
        self.msg_err = err

    def prompt(self, title: str, default: str = "") -> str | None:
        h, w = self.stdscr.getmaxyx()
        ph, pw = 5, min(w - 2, 52)
        y, x = max(0, h // 2 - 2), max(0, (w - pw) // 2)
        win = curses.newwin(ph, pw, y, x)
        win.bkgd(" ", curses.color_pair(4))
        win.box()
        win.addnstr(1, 2, title[: pw - 4], pw - 4)
        win.refresh()
        sub = win.derwin(1, pw - 4, 3, 2)
        try:
            sub.addstr(0, 0, default[: pw - 4])
        except curses.error:
            pass
        curses.curs_set(1)
        tb = curses.textpad.Textbox(sub)
        try:
            raw = tb.edit().strip()
        except KeyboardInterrupt:
            raw = ""
        curses.curs_set(0)
        if raw == "":
            return None
        return raw

    def confirm(self, title: str) -> bool:
        ans = self.prompt(title + "  y/n", "n")
        return bool(ans) and ans.lower().startswith("y")

    def pick_list(self, title: str, rows: list[str]) -> int | None:
        if not rows:
            self.say("empty")
            return None
        h, w = self.stdscr.getmaxyx()
        ph = min(h - 2, len(rows) + 3)
        pw = min(w - 2, max(20, max(len(title), max(len(r) for r in rows)) + 4))
        y, x = max(0, (h - ph) // 2), max(0, (w - pw) // 2)
        cur = 0
        while True:
            win = curses.newwin(ph, pw, y, x)
            win.bkgd(" ", curses.color_pair(4))
            win.box()
            win.addnstr(1, 2, title[: pw - 4], pw - 4)
            vis = ph - 3
            top = max(0, min(cur - vis + 1, max(0, len(rows) - vis)))
            for i in range(vis):
                idx = top + i
                if idx >= len(rows):
                    break
                attr = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                win.addnstr(2 + i, 2, rows[idx][: pw - 4], pw - 4, attr)
            win.refresh()
            k = win.getch()
            if k in (27, ord("q")):
                return None
            if k == curses.KEY_UP:
                cur = max(0, cur - 1)
            elif k == curses.KEY_DOWN:
                cur = min(len(rows) - 1, cur + 1)
            elif k in (10, 13, curses.KEY_ENTER):
                return cur

    def preview_lines(self, path: str, n: int) -> list[str]:
        if os.path.isdir(path):
            return ["<DIR>"]
        try:
            with open(path, "rb") as fh:
                data = fh.read(8 * 1024)
        except OSError as exc:
            return [str(exc)]
        if b"\x00" in data[:512]:
            return ["<binary>"]
        text = data.decode("utf-8", errors="replace").splitlines() or [""]
        return text[:n]

    def view_file(self, path: str) -> None:
        if os.path.isdir(path):
            self.say("not a file")
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read(128 * 1024)
        except OSError as exc:
            self.say(str(exc), True)
            return
        if b"\x00" in data[:2048]:
            self.say("binary file")
            return
        text = data.decode("utf-8", errors="replace").splitlines() or [""]
        h, w = self.stdscr.getmaxyx()
        top = 0
        while True:
            self.stdscr.erase()
            self.stdscr.addnstr(0, 0, path[:w], w, curses.A_REVERSE)
            for i in range(1, h - 1):
                li = top + i - 1
                if li < len(text):
                    self.stdscr.addnstr(i, 0, text[li][:w], w)
            self.stdscr.addnstr(h - 1, 0, "q back  arrows scroll", w, curses.A_REVERSE)
            self.stdscr.refresh()
            k = self.stdscr.getch()
            if k in (ord("q"), 27, curses.KEY_F10):
                break
            if k == curses.KEY_DOWN:
                top = min(max(0, len(text) - (h - 2)), top + 1)
            elif k == curses.KEY_UP:
                top = max(0, top - 1)
            elif k == curses.KEY_NPAGE:
                top = min(max(0, len(text) - (h - 2)), top + h - 2)
            elif k == curses.KEY_PPAGE:
                top = max(0, top - (h - 2))

    def help_screen(self) -> None:
        lines = [
            "sCMD keys",
            "Tab       other pane",
            "Enter     open dir",
            "Bksp      parent",
            "Space     mark",
            "/         filter name",
            "j         jump list",
            "s         sort name/size/date",
            "p         preview other pane",
            "h         hidden files",
            "x         chmod +x",
            "l         symlink into other pane",
            "d         SharkDrop this dir",
            "F1 help   F2 rename  F3 view",
            "F4 edit   F5 copy    F6 move",
            "F7 mkdir  F8 delete  F9 menu",
            "F10 / q   quit",
            "%p pane  %f file  %d other  %n name",
        ]
        self.pick_list("help (Enter/q)", lines)

    def expand_cmd(self, tmpl: str) -> str:
        pane = self.pane
        cur = pane.current()
        fname = os.path.basename(cur["path"].rstrip("/"))
        return (
            tmpl.replace("%p", pane.path)
            .replace("%d", self.other.path)
            .replace("%f", cur["path"])
            .replace("%n", fname)
        )

    def run_external(self, cmd: str) -> None:
        curses.endwin()
        try:
            subprocess.call(cmd, shell=True)
        except OSError as exc:
            print(exc)
        input("\n[enter]")
        self.stdscr = curses.initscr()
        curses.cbreak()
        curses.noecho()
        self.stdscr.keypad(True)
        curses.curs_set(0)
        self.pane.reload()
        self.other.reload()

    def user_menu(self) -> None:
        items = load_menu()
        if not items:
            self.say("empty ~/.scmd.menu", True)
            return
        idx = self.pick_list("F9 menu", [label for label, _ in items])
        if idx is None:
            return
        self.run_external(self.expand_cmd(items[idx][1]))

    def jump_menu(self) -> None:
        jumps = load_jumps()
        if not jumps:
            self.say("no jumps")
            return
        idx = self.pick_list("jump", [f"{n}  {p}" for n, p in jumps])
        if idx is None:
            return
        self.pane.jump(jumps[idx][1])
        self.say(jumps[idx][0])

    def set_filter(self) -> None:
        raw = self.prompt("filter (empty clears)", self.pane.filter)
        if raw is None:
            return
        self.pane.filter = raw
        self.pane.cursor = 0
        self.pane.reload()
        self.say("filter off" if not raw else f"filter {raw}")

    def edit_file(self) -> None:
        cur = self.pane.current()
        if cur["dir"]:
            self.say("not a file")
            return
        editor = os.environ.get("EDITOR") or "nano"
        self.run_external(f"{editor} {cur['path']}")

    def dest_path(self, src: str, dest_dir: str, dest_name: str | None = None) -> str:
        name = dest_name or os.path.basename(src.rstrip("/"))
        return os.path.join(dest_dir, name)

    def copy_one(self, src: str, dest: str, is_dir: bool, move: bool) -> None:
        if move:
            shutil.move(src, dest)
        elif is_dir:
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

    def copy_or_move(self, move: bool, same_pane: bool = False) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        dest_dir = self.pane.path if same_pane else self.other.path
        verb = "move" if move else "copy"
        dest_name = None
        if same_pane or len(items) == 1:
            suggested = os.path.basename(items[0]["path"].rstrip("/"))
            typed = self.prompt(f"{verb} as", suggested)
            if typed is None:
                self.say("cancelled")
                return
            dest_name = typed
        elif not self.confirm(f"{verb} {len(items)} -> other pane?"):
            self.say("cancelled")
            return

        ok = 0
        for i, item in enumerate(items, 1):
            src = item["path"]
            dest = self.dest_path(src, dest_dir, dest_name if len(items) == 1 else None)
            self.say(f"{verb} {i}/{len(items)} {os.path.basename(src)}")
            self.draw()
            if os.path.abspath(src) == os.path.abspath(dest):
                continue
            if os.path.exists(dest):
                if not self.confirm(f"overwrite {os.path.basename(dest)}?"):
                    continue
                try:
                    if os.path.isdir(dest) and not os.path.islink(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                except OSError as exc:
                    self.say(str(exc), True)
                    return
            try:
                self.copy_one(src, dest, item["dir"], move)
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                break
        self.pane.marks.clear()
        self.pane.reload()
        self.other.reload()
        if ok:
            self.say(f"{verb} {ok}")

    def mkdir(self) -> None:
        name = self.prompt("mkdir")
        if not name:
            return
        dest = os.path.join(self.pane.path, name)
        try:
            os.mkdir(dest)
            self.pane.reload()
            self.say(f"made {name}")
        except OSError as exc:
            self.say(str(exc), True)

    def rename(self) -> None:
        cur = self.pane.current()
        if cur["name"] == "..":
            return
        old = os.path.basename(cur["path"].rstrip("/"))
        name = self.prompt("rename", old)
        if not name or name == old:
            return
        dest = os.path.join(self.pane.path, name)
        try:
            os.rename(cur["path"], dest)
            self.pane.reload()
            self.say(f"renamed {name}")
        except OSError as exc:
            self.say(str(exc), True)

    def delete(self) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        if not self.confirm(f"delete {len(items)} item(s)?"):
            self.say("cancelled")
            return
        ok = 0
        for item in items:
            try:
                if item["dir"]:
                    shutil.rmtree(item["path"])
                else:
                    os.remove(item["path"])
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                break
        self.pane.marks.clear()
        self.pane.reload()
        if ok:
            self.say(f"deleted {ok}")

    def chmod_x(self) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        ok = 0
        for item in items:
            try:
                mode = os.stat(item["path"]).st_mode
                os.chmod(item["path"], mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                return
        self.say(f"+x {ok}")
        self.pane.reload()

    def symlink_other(self) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        ok = 0
        for item in items:
            dest = os.path.join(self.other.path, os.path.basename(item["path"].rstrip("/")))
            if os.path.exists(dest):
                if not self.confirm(f"overwrite {os.path.basename(dest)}?"):
                    continue
                try:
                    os.remove(dest)
                except OSError as exc:
                    self.say(str(exc), True)
                    return
            try:
                os.symlink(item["path"], dest)
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                return
        self.other.reload()
        self.say(f"link {ok}")

    def sharkdrop(self) -> None:
        drop = first_existing(
            [
                "/home/working/SharkDeck/SharkDeck/drop/sharkdrop.py",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drop", "sharkdrop.py"),
            ]
        )
        if not drop:
            self.say("sharkdrop.py not found", True)
            return
        self.run_external(f"python3 {os.path.abspath(drop)} start {self.pane.path}")

    def draw(self) -> None:
        scr = self.stdscr
        h, w = scr.getmaxyx()
        scr.erase()
        mid = max(10, w // 2)
        list_h = max(3, h - 4)

        for i, pane in enumerate(self.panes):
            x0 = 0 if i == 0 else mid
            pw = mid if i == 0 else w - mid
            active = i == self.active
            show_preview = self.preview and i != self.active
            filt = f" [{pane.filter}]" if pane.filter else ""
            header = f"{pane.path}{filt} {pane.sort}"
            attr = curses.color_pair(1) | (curses.A_BOLD if active else 0)
            try:
                scr.addnstr(0, x0, header.ljust(pw)[:pw], pw, attr)
            except curses.error:
                pass

            if show_preview:
                lines = self.preview_lines(self.pane.current_path(), list_h)
                for row, line in enumerate(lines[:list_h]):
                    try:
                        scr.addnstr(1 + row, x0, line[:pw].ljust(pw)[:pw], pw, curses.color_pair(3))
                    except curses.error:
                        pass
                continue

            vis = list_h
            if pane.cursor < pane.scroll:
                pane.scroll = pane.cursor
            if pane.cursor >= pane.scroll + vis:
                pane.scroll = pane.cursor - vis + 1
            pane.scroll = max(0, pane.scroll)

            for row in range(vis):
                idx = pane.scroll + row
                y = 1 + row
                if idx >= len(pane.entries):
                    continue
                e = pane.entries[idx]
                mark = "*" if e["path"] in pane.marks else " "
                size = "<DIR>" if e["dir"] else fmt_size(e["size"])
                name_w = max(8, pw - 8)
                line = f"{mark}{e['name'][:name_w-1]:<{name_w-1}}{size:>6}"
                a = curses.A_NORMAL
                if idx == pane.cursor and active:
                    a = curses.color_pair(2) | curses.A_BOLD
                elif e["dir"]:
                    a = curses.color_pair(3)
                try:
                    scr.addnstr(y, x0, line[:pw].ljust(pw)[:pw], pw, a)
                except curses.error:
                    pass

        if 0 < mid < w:
            for y in range(1, list_h + 1):
                try:
                    scr.addch(y, mid, curses.ACS_VLINE)
                except curses.error:
                    pass

        cur = self.pane.current()
        when = ""
        if cur.get("mtime"):
            when = datetime.fromtimestamp(cur["mtime"]).strftime("%m-%d %H:%M")
        info = f"{cur['name']} {when} *{len(self.pane.marks)} {disk_free(self.pane.path)}"
        try:
            scr.addnstr(h - 3, 0, info[:w].ljust(w)[:w], w, curses.color_pair(4))
        except curses.error:
            pass

        msg_attr = curses.color_pair(5) if self.msg_err else curses.color_pair(4)
        try:
            scr.addnstr(h - 2, 0, (self.msg or NAME)[:w].ljust(w)[:w], w, msg_attr)
        except curses.error:
            pass

        help_line = "F1?  F3 view  F4 ed  F5 cp  F6 mv  F7 md  F8 rm  F9 menu  / j s p x l d"
        try:
            scr.addnstr(h - 1, 0, help_line[:w].ljust(w)[:w], w, curses.A_REVERSE)
        except curses.error:
            pass
        scr.refresh()

    def run(self) -> None:
        while True:
            self.draw()
            k = self.stdscr.getch()
            self.msg_err = False
            if k in (ord("q"), curses.KEY_F10):
                break
            if k in (curses.KEY_F1, ord("?")):
                self.help_screen()
            elif k == 9:
                self.active = 1 - self.active
            elif k == curses.KEY_UP:
                self.pane.move(-1)
            elif k == curses.KEY_DOWN:
                self.pane.move(1)
            elif k == curses.KEY_PPAGE:
                self.pane.page(max(3, self.stdscr.getmaxyx()[0] - 4), -1)
            elif k == curses.KEY_NPAGE:
                self.pane.page(max(3, self.stdscr.getmaxyx()[0] - 4), 1)
            elif k == curses.KEY_HOME:
                self.pane.cursor = 0
            elif k == curses.KEY_END:
                self.pane.cursor = max(0, len(self.pane.entries) - 1)
            elif k in (curses.KEY_ENTER, 10, 13):
                if self.pane.current()["dir"]:
                    self.pane.enter()
                else:
                    self.view_file(self.pane.current_path())
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                self.pane.parent()
            elif k == ord(" "):
                self.pane.toggle_mark()
            elif k in (ord("h"), ord("H")):
                self.pane.hidden = not self.pane.hidden
                self.pane.reload()
            elif k == ord("/"):
                self.set_filter()
            elif k in (ord("j"), ord("J")):
                self.jump_menu()
            elif k in (ord("s"), ord("S")):
                i = SORTS.index(self.pane.sort)
                self.pane.sort = SORTS[(i + 1) % len(SORTS)]
                self.pane.reload()
                self.say(f"sort {self.pane.sort}")
            elif k in (ord("p"), ord("P")):
                self.preview = not self.preview
                self.say("preview on" if self.preview else "preview off")
            elif k in (ord("x"), ord("X")):
                self.chmod_x()
            elif k in (ord("l"), ord("L")):
                self.symlink_other()
            elif k in (ord("d"), ord("D")):
                self.sharkdrop()
            elif k in (ord("c"), ord("C")):
                self.copy_or_move(False, same_pane=True)
            elif k == curses.KEY_F3:
                cur = self.pane.current()
                if cur["dir"]:
                    self.pane.enter()
                else:
                    self.view_file(cur["path"])
            elif k == curses.KEY_F4:
                self.edit_file()
            elif k == curses.KEY_F5:
                self.copy_or_move(False)
            elif k == curses.KEY_F6:
                self.copy_or_move(True)
            elif k == curses.KEY_F7:
                self.mkdir()
            elif k == curses.KEY_F8:
                self.delete()
            elif k == curses.KEY_F2:
                self.rename()
            elif k == curses.KEY_F9:
                self.user_menu()
            elif k == curses.KEY_RESIZE:
                pass


def _curses_main(stdscr) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)
    left = START
    right = os.path.expanduser("~")
    if os.path.isdir("/home/working/SharkDeck/SharkDeck"):
        right = "/home/working/SharkDeck/SharkDeck"
    App(stdscr, left, right).run()


def main() -> int:
    if not sys.stdout.isatty():
        sys.stderr.write("sCMD needs a real terminal\n")
        return 2
    try:
        curses.wrapper(_curses_main)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import curses
import curses.textpad
import os
import shutil
import stat
import sys
from datetime import datetime

NAME = "SharkCommander"
START = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()))


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f}K"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}M"
    return f"{n / (1024 * 1024 * 1024):.1f}G"


def list_dir(path: str, hidden: bool) -> list[dict]:
    out = [{"name": "..", "path": os.path.dirname(path) or path, "dir": True, "size": 0, "mtime": 0}]
    try:
        names = os.listdir(path)
    except OSError:
        return out
    for name in names:
        if not hidden and name.startswith("."):
            continue
        full = os.path.join(path, name)
        try:
            st = os.lstat(full)
        except OSError:
            continue
        is_dir = stat.S_ISDIR(st.st_mode)
        out.append(
            {
                "name": name + ("/" if is_dir else ""),
                "path": full,
                "dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
            }
        )
    out.sort(key=lambda e: (0 if e["name"] == ".." else 1, not e["dir"], e["name"].lower()))
    return out


class Pane:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.cursor = 0
        self.scroll = 0
        self.marks: set[str] = set()
        self.hidden = False
        self.entries: list[dict] = []
        self.reload()

    def reload(self) -> None:
        keep = self.current_path() if self.entries else None
        self.entries = list_dir(self.path, self.hidden)
        self.marks &= {e["path"] for e in self.entries}
        if keep:
            for i, e in enumerate(self.entries):
                if e["path"] == keep:
                    self.cursor = i
                    break
        self.cursor = max(0, min(self.cursor, len(self.entries) - 1))

    def current(self) -> dict:
        if not self.entries:
            return {"name": "..", "path": self.path, "dir": True, "size": 0, "mtime": 0}
        return self.entries[self.cursor]

    def current_path(self) -> str:
        return self.current()["path"]

    def marked_or_current(self) -> list[dict]:
        marked = [e for e in self.entries if e["path"] in self.marks and e["name"] != ".."]
        if marked:
            return marked
        cur = self.current()
        if cur["name"] == "..":
            return []
        return [cur]

    def toggle_mark(self) -> None:
        e = self.current()
        if e["name"] == "..":
            return
        if e["path"] in self.marks:
            self.marks.discard(e["path"])
        else:
            self.marks.add(e["path"])
        self.move(1)

    def move(self, delta: int) -> None:
        if not self.entries:
            return
        self.cursor = max(0, min(len(self.entries) - 1, self.cursor + delta))

    def page(self, h: int, direction: int) -> None:
        self.move(direction * max(1, h - 2))

    def enter(self) -> None:
        e = self.current()
        if e["dir"]:
            new = e["path"] if e["name"] != ".." else os.path.dirname(self.path) or self.path
            if e["name"] == "..":
                old = self.path
                self.path = os.path.abspath(new)
                self.reload()
                for i, row in enumerate(self.entries):
                    if row["path"] == old:
                        self.cursor = i
                        break
            else:
                self.path = os.path.abspath(new)
                self.cursor = 0
                self.scroll = 0
                self.marks.clear()
                self.reload()

    def parent(self) -> None:
        old = self.path
        parent = os.path.dirname(self.path) or self.path
        if parent == self.path:
            return
        self.path = parent
        self.reload()
        for i, row in enumerate(self.entries):
            if row["path"] == old:
                self.cursor = i
                break


class App:
    def __init__(self, stdscr, left: str, right: str):
        self.stdscr = stdscr
        self.panes = [Pane(left), Pane(right)]
        self.active = 0
        self.msg = ""
        self.msg_err = False

    @property
    def pane(self) -> Pane:
        return self.panes[self.active]

    @property
    def other(self) -> Pane:
        return self.panes[1 - self.active]

    def say(self, text: str, err: bool = False) -> None:
        self.msg = text[:80]
        self.msg_err = err

    def prompt(self, title: str, default: str = "") -> str | None:
        h, w = self.stdscr.getmaxyx()
        ph, pw = 5, min(w - 2, 48)
        y, x = max(0, h // 2 - 2), max(0, (w - pw) // 2)
        win = curses.newwin(ph, pw, y, x)
        win.bkgd(" ", curses.color_pair(4))
        win.box()
        win.addnstr(1, 2, title[: pw - 4], pw - 4)
        win.refresh()
        sub = win.derwin(1, pw - 4, 3, 2)
        sub.addstr(0, 0, default[: pw - 4])
        curses.curs_set(1)
        tb = curses.textpad.Textbox(sub)
        try:
            raw = tb.edit().strip()
        except KeyboardInterrupt:
            raw = ""
        curses.curs_set(0)
        if raw == "":
            return None
        return raw

    def confirm(self, title: str) -> bool:
        ans = self.prompt(title + "  y/n", "n")
        return bool(ans) and ans.lower().startswith("y")

    def view_file(self, path: str) -> None:
        if os.path.isdir(path):
            self.say("not a file")
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read(64 * 1024)
        except OSError as exc:
            self.say(str(exc), True)
            return
        if b"\x00" in data:
            self.say("binary file")
            return
        text = data.decode("utf-8", errors="replace").splitlines() or [""]
        h, w = self.stdscr.getmaxyx()
        top = 0
        while True:
            self.stdscr.erase()
            self.stdscr.addnstr(0, 0, path[:w], w, curses.A_REVERSE)
            for i in range(1, h - 1):
                li = top + i - 1
                if li < len(text):
                    self.stdscr.addnstr(i, 0, text[li][:w], w)
            self.stdscr.addnstr(h - 1, 0, "q back  arrows scroll", w, curses.A_REVERSE)
            self.stdscr.refresh()
            k = self.stdscr.getch()
            if k in (ord("q"), 27, curses.KEY_F10):
                break
            if k == curses.KEY_DOWN:
                top = min(max(0, len(text) - (h - 2)), top + 1)
            elif k == curses.KEY_UP:
                top = max(0, top - 1)
            elif k == curses.KEY_NPAGE:
                top = min(max(0, len(text) - (h - 2)), top + h - 2)
            elif k == curses.KEY_PPAGE:
                top = max(0, top - (h - 2))

    def copy_or_move(self, move: bool) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        dest_dir = self.other.path
        verb = "move" if move else "copy"
        names = ", ".join(os.path.basename(i["path"].rstrip("/")) for i in items)
        if not self.confirm(f"{verb} {len(items)} -> other pane?"):
            self.say("cancelled")
            return
        ok = 0
        for item in items:
            src = item["path"]
            dest = os.path.join(dest_dir, os.path.basename(src.rstrip("/")))
            try:
                if os.path.abspath(src) == os.path.abspath(dest):
                    continue
                if move:
                    shutil.move(src, dest)
                elif item["dir"]:
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                break
        self.pane.marks.clear()
        self.pane.reload()
        self.other.reload()
        if ok:
            self.say(f"{verb} {ok}  {names[:24]}")

    def mkdir(self) -> None:
        name = self.prompt("mkdir")
        if not name:
            return
        dest = os.path.join(self.pane.path, name)
        try:
            os.mkdir(dest)
            self.pane.reload()
            self.say(f"made {name}")
        except OSError as exc:
            self.say(str(exc), True)

    def rename(self) -> None:
        cur = self.pane.current()
        if cur["name"] == "..":
            return
        old = os.path.basename(cur["path"].rstrip("/"))
        name = self.prompt("rename", old)
        if not name or name == old:
            return
        dest = os.path.join(self.pane.path, name)
        try:
            os.rename(cur["path"], dest)
            self.pane.reload()
            self.say(f"renamed {name}")
        except OSError as exc:
            self.say(str(exc), True)

    def delete(self) -> None:
        items = self.pane.marked_or_current()
        if not items:
            self.say("nothing selected")
            return
        if not self.confirm(f"delete {len(items)} item(s)?"):
            self.say("cancelled")
            return
        ok = 0
        for item in items:
            try:
                if item["dir"]:
                    shutil.rmtree(item["path"])
                else:
                    os.remove(item["path"])
                ok += 1
            except OSError as exc:
                self.say(str(exc), True)
                break
        self.pane.marks.clear()
        self.pane.reload()
        if ok:
            self.say(f"deleted {ok}")

    def draw(self) -> None:
        scr = self.stdscr
        h, w = scr.getmaxyx()
        scr.erase()
        mid = w // 2
        list_h = max(3, h - 4)

        for i, pane in enumerate(self.panes):
            x0 = 0 if i == 0 else mid
            pw = mid if i == 0 else w - mid
            active = i == self.active
            header = pane.path
            attr = curses.color_pair(1) | (curses.A_BOLD if active else 0)
            try:
                scr.addnstr(0, x0, header.ljust(pw)[:pw], pw, attr)
            except curses.error:
                pass

            vis = list_h
            if pane.cursor < pane.scroll:
                pane.scroll = pane.cursor
            if pane.cursor >= pane.scroll + vis:
                pane.scroll = pane.cursor - vis + 1
            pane.scroll = max(0, pane.scroll)

            for row in range(vis):
                idx = pane.scroll + row
                y = 1 + row
                if idx >= len(pane.entries):
                    continue
                e = pane.entries[idx]
                mark = "*" if e["path"] in pane.marks else " "
                if e["name"] == "..":
                    size = "<DIR>"
                elif e["dir"]:
                    size = "<DIR>"
                else:
                    size = fmt_size(e["size"])
                name_w = max(8, pw - 8)
                line = f"{mark}{e['name'][:name_w-1]:<{name_w-1}}{size:>6}"
                a = curses.A_NORMAL
                if idx == pane.cursor and active:
                    a = curses.color_pair(2) | curses.A_BOLD
                elif e["dir"]:
                    a = curses.color_pair(3)
                try:
                    scr.addnstr(y, x0, line[:pw].ljust(pw)[:pw], pw, a)
                except curses.error:
                    pass

        # divider
        if 0 < mid < w:
            for y in range(1, list_h + 1):
                try:
                    scr.addch(y, mid, curses.ACS_VLINE)
                except curses.error:
                    pass

        # status
        cur = self.pane.current()
        when = ""
        if cur.get("mtime"):
            when = datetime.fromtimestamp(cur["mtime"]).strftime("%m-%d %H:%M")
        info = f"{cur['name']}  {when}  marks:{len(self.pane.marks)}"
        try:
            scr.addnstr(h - 3, 0, info[:w].ljust(w)[:w], w, curses.color_pair(4))
        except curses.error:
            pass

        msg_attr = curses.color_pair(5) if self.msg_err else curses.color_pair(4)
        try:
            scr.addnstr(h - 2, 0, (self.msg or NAME)[:w].ljust(w)[:w], w, msg_attr)
        except curses.error:
            pass

        help_line = "TAB  F3 view  F5 copy  F6 move  F7 mkdir  F8 del  F2 ren  F10 quit"
        try:
            scr.addnstr(h - 1, 0, help_line[:w].ljust(w)[:w], w, curses.A_REVERSE)
        except curses.error:
            pass
        scr.refresh()

    def run(self) -> None:
        while True:
            self.draw()
            k = self.stdscr.getch()
            self.msg_err = False
            if k in (ord("q"), curses.KEY_F10):
                break
            if k == 9:  # tab
                self.active = 1 - self.active
            elif k == curses.KEY_UP:
                self.pane.move(-1)
            elif k == curses.KEY_DOWN:
                self.pane.move(1)
            elif k == curses.KEY_PPAGE:
                self.pane.page(max(3, self.stdscr.getmaxyx()[0] - 4), -1)
            elif k == curses.KEY_NPAGE:
                self.pane.page(max(3, self.stdscr.getmaxyx()[0] - 4), 1)
            elif k == curses.KEY_HOME:
                self.pane.cursor = 0
            elif k == curses.KEY_END:
                self.pane.cursor = len(self.pane.entries) - 1
            elif k in (curses.KEY_ENTER, 10, 13):
                self.pane.enter()
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                self.pane.parent()
            elif k == ord(" "):
                self.pane.toggle_mark()
            elif k in (ord("h"), ord("H")):
                self.pane.hidden = not self.pane.hidden
                self.pane.reload()
            elif k == curses.KEY_F3:
                cur = self.pane.current()
                if cur["dir"]:
                    self.pane.enter()
                else:
                    self.view_file(cur["path"])
            elif k == curses.KEY_F5:
                self.copy_or_move(False)
            elif k == curses.KEY_F6:
                self.copy_or_move(True)
            elif k == curses.KEY_F7:
                self.mkdir()
            elif k == curses.KEY_F8:
                self.delete()
            elif k == curses.KEY_F2:
                self.rename()
            elif k == curses.KEY_RESIZE:
                pass


def _curses_main(stdscr) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)
    left = START
    right = os.path.expanduser("~")
    if os.path.isdir("/home/working/SharkDeck/SharkDeck"):
        right = "/home/working/SharkDeck/SharkDeck"
    App(stdscr, left, right).run()


def main() -> int:
    if not sys.stdout.isatty():
        sys.stderr.write("SharkCommander needs a real terminal\n")
        return 2
    try:
        curses.wrapper(_curses_main)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
