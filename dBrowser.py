#!/usr/bin/env python3
"""dBrowser — reader browser for SharkDeck 480x320."""

import html as htmlmod
import os
import re
import sys
import http.cookiejar
import urllib.parse
import urllib.request
from html.parser import HTMLParser

NAME = "dBrowser"
HOME = "https://lite.duckduckgo.com/lite/"
SEARCH = "https://lite.duckduckgo.com/lite/?q=%s"
DIR = os.path.expanduser("~/.dbrowser")
BM = os.path.join(DIR, "bookmarks")
HIST = os.path.join(DIR, "history")
COOKIES = os.path.join(DIR, "cookies")
UA = "dBrowser/4 (SharkDeck; text reader)"
MAX_BODY = 180000
CACHE_N = 8
COLS = 52

os.makedirs(DIR, exist_ok=True)
JAR = http.cookiejar.MozillaCookieJar(COOKIES)
try:
    JAR.load(ignore_discard=True, ignore_expires=True)
except Exception:
    pass
OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(JAR),
    urllib.request.HTTPRedirectHandler(),
)
OPENER.addheaders = [
    ("User-Agent", UA),
    ("Accept", "text/html,text/plain;q=0.9,*/*;q=0.1"),
    ("Accept-Language", "en"),
]


def resolve(raw, current=""):
    raw = (raw or "").strip()
    if not raw:
        return current
    if "://" in raw or raw.startswith("file:"):
        return raw
    if raw.startswith("/") and current:
        return urllib.parse.urljoin(current, raw)
    host = raw.split("/")[0]
    if " " in raw or "." not in host:
        return SEARCH % urllib.parse.quote_plus(raw)
    return "https://" + raw


def wrap(text, width=COLS):
    lines = []
    for para in text.splitlines():
        para = para.rstrip()
        if not para:
            lines.append("")
            continue
        pad = len(para) - len(para.lstrip(" ")) if para.startswith("  ") else 0
        while para:
            if len(para) <= width:
                lines.append(para)
                break
            cut = para.rfind(" ", pad + 1, width)
            if cut <= pad:
                cut = width
            lines.append(para[:cut])
            para = (" " * pad) + para[cut:].lstrip()
    return "\n".join(lines)


def charset_from_header(ctype):
    if not ctype:
        return None
    m = re.search(r"charset\s*=\s*([\"']?)([A-Za-z0-9._-]+)\1", ctype, re.I)
    return m.group(2) if m else None


def charset_from_meta(raw):
    head = raw[:4096]
    m = re.search(br"charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", head, re.I)
    if m:
        return m.group(1).decode("ascii", "ignore")
    return None


def decode_body(raw, header_cs):
    for cs in (header_cs, charset_from_meta(raw), "utf-8", "cp1252"):
        if not cs:
            continue
        try:
            return raw.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


class Doc(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    CHROME = {"nav", "header", "footer", "aside"}
    MAIN = {"article", "main"}

    def __init__(self, base, reader=True):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.reader = reader
        self.skip = 0
        self.chrome = 0
        self.in_main = 0
        self.title = ""
        self._title = False
        self._href = None
        self._ltxt = []
        self._pre = False
        self.blocks = []  # (region, kind, text) region=main|body
        self.cur = []
        self.links = []
        self.images = []
        self.region = "body"

    def _flush(self, kind="p"):
        t = "".join(self.cur)
        self.cur = []
        if not self._pre:
            t = " ".join(t.split())
        if t.strip():
            self.blocks.append((self.region, kind, t.strip()))

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if self.reader and tag in self.CHROME:
            self.chrome += 1
            return
        if self.chrome:
            return
        if tag in self.MAIN:
            self.in_main += 1
            self.region = "main"
        if tag == "title":
            self._title = True
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush()
        elif tag in ("p", "div", "section", "tr"):
            self._flush()
        elif tag == "br":
            self.cur.append("\n")
        elif tag == "li":
            self._flush()
            self.cur.append("• ")
        elif tag == "blockquote":
            self._flush()
        elif tag in ("pre", "code") and not self._pre:
            self._flush()
            self._pre = True
        elif tag == "hr":
            self._flush()
            self.blocks.append((self.region, "hr", ""))
        elif tag == "img":
            src = ad.get("src") or ad.get("data-src") or ""
            alt = (ad.get("alt") or "").strip()
            if src and not src.startswith("data:"):
                self.images.append(urllib.parse.urljoin(self.base, src))
            if alt:
                self.cur.append(" [%s] " % alt)
        elif tag == "a":
            self._href = urllib.parse.urljoin(self.base, ad.get("href") or "")
            self._ltxt = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if self.reader and tag in self.CHROME and self.chrome:
            self.chrome -= 1
            return
        if self.chrome:
            return
        if tag in self.MAIN and self.in_main:
            self._flush()
            self.in_main -= 1
            if self.in_main <= 0:
                self.region = "body"
        if tag == "title":
            self._title = False
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush(tag)
        elif tag in ("p", "div", "section", "li", "blockquote", "tr"):
            kind = "q" if tag == "blockquote" else ("li" if tag == "li" else "p")
            self._flush(kind)
        elif tag in ("pre", "code") and self._pre:
            self._flush("pre")
            self._pre = False
        elif tag == "a" and self._href:
            lab = " ".join("".join(self._ltxt).split()) or self._href
            n = len(self.links) + 1
            self.links.append((lab, self._href))
            self.cur.append("%s[%d]" % (lab, n))
            self._href = None

    def handle_data(self, data):
        if self.skip or self.chrome:
            return
        if self._title:
            self.title += data
        elif self._href is not None:
            self._ltxt.append(data)
        else:
            self.cur.append(data)

    def pick_blocks(self):
        main = [b for b in self.blocks if b[0] == "main"]
        if main and sum(len(b[2]) for b in main) > 80:
            return main
        # longest run of body paragraphs
        best, run, cur = [], [], 0
        score, best_s = 0, 0
        for b in self.blocks:
            if b[1] in ("p", "h1", "h2", "h3", "li", "q"):
                run.append(b)
                score += len(b[2])
            else:
                if score > best_s:
                    best, best_s = run, score
                run, score = [], 0
        if score > best_s:
            best = run
        if best_s >= 120 or (best and sum(len(x[2]) for x in best) > 80):
            # include nearby headings: use best run
            return best or self.blocks
        return self.blocks

    def finish(self, reader=True):
        self._flush()
        blocks = self.pick_blocks() if reader else self.blocks
        parts = []
        for _reg, kind, t in blocks:
            if kind == "h1":
                parts += [t.upper(), "=" * min(len(t), COLS)]
            elif kind == "h2":
                parts += [t, "-" * min(len(t), COLS)]
            elif kind in ("h3", "h4"):
                parts.append(t)
            elif kind == "hr":
                parts.append("--")
            elif kind == "q":
                parts.append("  " + t)
            else:
                parts.append(t)
            parts.append("")
        return wrap("\n".join(parts).strip())


def http_get(url, limit=MAX_BODY, timeout=12):
    if url.startswith("file://"):
        data = open(urllib.parse.urlparse(url).path, "rb").read(limit)
        return url, data, "text/html", None
    resp = OPENER.open(url, timeout=timeout)
    try:
        ctype = resp.headers.get("Content-Type") or "text/html"
        data = resp.read(limit)
        final = resp.geturl()
        try:
            JAR.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
        return final, data, ctype, charset_from_header(ctype)
    finally:
        resp.close()


def load_page(url, reader=True):
    try:
        final, raw, ctype, cs = http_get(url)
    except Exception as exc:
        return {"url": url, "title": "error", "text": str(exc), "links": [], "images": []}
    text = decode_body(raw, cs)
    if "html" not in (ctype or "").lower() and not text.lstrip().lower().startswith("<!"):
        return {
            "url": final, "title": final, "text": wrap(text),
            "links": [], "images": [],
        }
    doc = Doc(final, reader=reader)
    try:
        doc.feed(text)
        doc.close()
    except Exception:
        pass
    return {
        "url": final,
        "title": " ".join(doc.title.split()) or urllib.parse.urlparse(final).netloc,
        "text": doc.finish(reader=reader),
        "links": doc.links,
        "images": list(dict.fromkeys(doc.images))[:8],
    }


def read_kv(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and "|" in line and not line.startswith("#"):
                a, b = line.split("|", 1)
                rows.append((a.strip(), b.strip()))
    return rows


def write_kv(path, rows, cap=50):
    with open(path, "w", encoding="utf-8") as fh:
        for a, b in rows[:cap]:
            fh.write("%s|%s\n" % (a, b))


def thumb(url, max_px=64, max_b=20000):
    try:
        _u, data, ctype, _cs = http_get(url, limit=max_b, timeout=5)
    except Exception:
        return None
    if len(data) >= max_b:
        return None
    try:
        from PIL import Image, ImageTk
        import io
        im = Image.open(io.BytesIO(data))
        im.thumbnail((max_px, max_px))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        return ImageTk.PhotoImage(im)
    except Exception:
        return None


def main():
    try:
        import tkinter as tk
    except ImportError:
        sys.stderr.write("apt install -y python3-tk\n")
        return 2

    start = resolve(sys.argv[1] if len(sys.argv) > 1 else HOME)
    cache = {}
    hist = []
    reader = True
    pics_on = False
    page = {"url": start, "title": "", "text": "", "links": [], "images": []}
    photos = []
    tagged = []
    find_at = "1.0"
    mode = "go"  # go | find | search

    C = dict(bg="#0d1117", fg="#c9d1d9", dim="#8b949e", acc="#58a6ff",
             bar="#161b22", line="#30363d", hit="#5c4a00")
    root = tk.Tk()
    root.title(NAME)
    root.geometry("480x320+0+0")
    root.configure(bg=C["bg"])
    root.option_add("*Font", "TkFixedFont 9")
    root.option_add("*Background", C["bg"])
    root.option_add("*Foreground", C["fg"])
    root.option_add("*Button.Relief", "flat")
    root.option_add("*Button.BorderWidth", 0)
    root.option_add("*Button.Background", C["bar"])
    root.option_add("*Button.Foreground", C["acc"])
    root.option_add("*HighlightThickness", 0)
    root.option_add("*Entry.Background", "#010409")
    root.option_add("*Entry.Foreground", C["fg"])
    root.option_add("*Entry.Relief", "flat")
    root.option_add("*Text.Background", C["bg"])
    root.option_add("*Text.Foreground", C["fg"])
    root.option_add("*Listbox.Background", C["bar"])
    root.option_add("*Listbox.Foreground", C["fg"])

    urlv = tk.StringVar(value=start)
    titlev = tk.StringVar(value=NAME)
    stv = tk.StringVar(value="")
    findv = tk.StringVar()

    head = tk.Frame(root, bg=C["bar"])
    head.pack(fill="x")
    tk.Label(head, textvariable=titlev, fg=C["fg"], bg=C["bar"],
             anchor="w").pack(fill="x", padx=8, pady=(5, 2))
    row = tk.Frame(root, bg=C["bar"])
    row.pack(fill="x")
    tk.Frame(root, bg=C["line"], height=1).pack(fill="x")

    body = tk.Text(root, wrap="word", bd=0, highlightthickness=0, undo=False,
                   spacing1=2, spacing3=4, padx=8, pady=6)
    body.pack(fill="both", expand=True)
    sb = tk.Scrollbar(body, command=body.yview, width=6, bg=C["bar"],
                      troughcolor=C["bg"], bd=0)
    body.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")

    lst = tk.Listbox(root, height=2, bd=0, highlightthickness=0, activestyle="none")
    lst.pack(fill="x")
    foot = tk.Frame(root, bg=C["bar"])
    foot.pack(fill="x")
    tk.Label(foot, textvariable=stv, fg=C["dim"], bg=C["bar"],
             anchor="w").pack(side="left", fill="x", expand=True, padx=6)
    find_ent = tk.Entry(foot, textvariable=findv, width=18, insertbackground=C["fg"])
    # shown only in find/search mode

    def say(m):
        stv.set(m[:64])
        root.update_idletasks()

    def btn(txt, cmd):
        tk.Button(row, text=txt, command=cmd, padx=5).pack(side="left")

    def hide_find():
        nonlocal mode
        mode = "go"
        find_ent.pack_forget()
        body.focus_set()

    def show_find(kind):
        nonlocal mode, find_at
        mode = kind
        findv.set("")
        find_ent.pack(side="right", padx=4, pady=2)
        find_ent.focus_set()
        if kind == "find":
            find_at = "1.0"
            say("find")
        else:
            say("search")

    def do_find(again=False):
        nonlocal find_at
        q = findv.get().strip()
        if not q:
            return
        if not again:
            find_at = "1.0"
        body.tag_remove("hit", "1.0", "end")
        idx = body.search(q, find_at, "end", nocase=True)
        if not idx:
            idx = body.search(q, "1.0", "end", nocase=True)
        if not idx:
            say("no match")
            return
        end = "%s+%dc" % (idx, len(q))
        body.tag_add("hit", idx, end)
        body.tag_config("hit", background=C["hit"], foreground="#fff")
        body.see(idx)
        find_at = end
        say("found")

    def foot_enter(e):
        q = findv.get().strip()
        if mode == "search":
            hide_find()
            if q:
                go(SEARCH % urllib.parse.quote_plus(q))
        else:
            do_find(again=True)

    def click_tag(e):
        for t in body.tag_names(body.index("@%d,%d" % (e.x, e.y))):
            if t.startswith("n") and t[1:].isdigit():
                i = int(t[1:])
                if i < len(tagged):
                    go(tagged[i])
                return

    def paint(p, splash=False):
        nonlocal page, tagged, photos, find_at
        page = p
        urlv.set(p["url"])
        host = urllib.parse.urlparse(p["url"]).netloc
        titlev.set((p["title"] or NAME)[:44])
        root.title("%s  %s" % (NAME, host))
        if splash:
            body.delete("1.0", "end")
            body.insert("1.0", "loading  " + host + "\n")
            say("loading")
            root.update_idletasks()
            return
        body.delete("1.0", "end")
        for t in list(body.tag_names()):
            if t.startswith("n"):
                body.tag_delete(t)
        body.insert("1.0", p["text"] or "(empty)")
        tagged = []
        at = "1.0"
        for i, (_lab, href) in enumerate(p["links"][:70], 1):
            idx = body.search("[%d]" % i, at, "end")
            if not idx:
                continue
            end = "%s+%dc" % (idx, len("[%d]" % i))
            tag = "n%d" % (i - 1)
            body.tag_add(tag, idx, end)
            body.tag_config(tag, foreground=C["acc"], underline=1)
            body.tag_bind(tag, "<Button-1>", click_tag)
            tagged.append(href)
            at = end
        photos = []
        if pics_on:
            for src in p["images"][:4]:
                im = thumb(src)
                if im:
                    photos.append(im)
                    body.insert("end", "\n")
                    body.image_create("end", image=im)
        lst.delete(0, "end")
        lst.urls = [h for _a, h in p["links"][:80]]
        for i, (lab, _h) in enumerate(p["links"][:80], 1):
            lst.insert("end", "%d  %s" % (i, lab[:46]))
        find_at = "1.0"
        say("%s  %d links" % ("read" if reader else "full", len(p["links"])))
        body.see("1.0")
        body.focus_set()

    def go(url=None, push=True, force=False):
        url = resolve(url if url is not None else urlv.get(), page.get("url"))
        if not url:
            return
        key = (url, reader)
        if push and page.get("url") and page["url"] != url:
            hist.append(page["url"])
        paint({"url": url, "title": "loading", "text": "", "links": [], "images": []}, splash=True)
        if not force and key in cache:
            paint(cache[key])
            return
        root.update()
        p = load_page(url, reader=reader)
        cache[key] = p
        if len(cache) > CACHE_N * 2:
            cache.pop(next(iter(cache)))
        rows = [(p["title"], p["url"])] + [r for r in read_kv(HIST) if r[1] != p["url"]]
        write_kv(HIST, rows)
        paint(p)

    def back():
        if hist:
            go(hist.pop(), push=False)

    def pick(rows, title):
        if not rows:
            say("empty")
            return
        w = tk.Toplevel(root)
        w.configure(bg=C["bg"])
        w.geometry("468x200+6+30")
        w.title(title)
        lb = tk.Listbox(w, height=9)
        lb.pack(fill="both", expand=True, padx=6, pady=6)
        for n, u in rows:
            lb.insert("end", "%s   %s" % (n[:22], u[:40]))

        def ok(_e=None):
            i = lb.curselection()
            if i:
                go(rows[i[0]][1])
                w.destroy()

        lb.bind("<Double-1>", ok)
        lb.bind("<Return>", ok)
        lb.focus_set()

    def toggle_reader():
        nonlocal reader
        reader = not reader
        go(page.get("url"), push=False, force=True)

    def toggle_pics():
        nonlocal pics_on
        pics_on = not pics_on
        paint(page)

    def key(e):
        if e.widget in (entry, find_ent):
            return
        c = e.char
        if c == "j":
            body.yview_scroll(4, "units")
        elif c == "k":
            body.yview_scroll(-4, "units")
        elif c == " ":
            body.yview_scroll(1, "pages")
        elif c == "g":
            entry.focus_set()
            entry.selection_range(0, "end")
        elif c == "b":
            back()
        elif c == "/":
            show_find("find")
        elif c == "s":
            show_find("search")
        elif c == "r":
            toggle_reader()
        elif c == "q":
            root.destroy()
        elif c.isdigit() and c != "0":
            n = int(c) - 1
            if n < len(getattr(lst, "urls", [])):
                go(lst.urls[n])

    btn("←", back)
    btn("↻", lambda: go(urlv.get(), push=False, force=True))
    entry = tk.Entry(row, textvariable=urlv, insertbackground=C["fg"])
    entry.pack(side="left", fill="x", expand=True, padx=6, ipady=3)
    entry.bind("<Return>", lambda e: go())
    btn("go", go)
    btn("read", toggle_reader)
    btn("find", lambda: show_find("find"))
    btn("ddg", lambda: show_find("search"))
    btn("★", lambda: (write_kv(BM, read_kv(BM) + [(page.get("title") or "page", urlv.get())]), say("marked")))
    btn("marks", lambda: pick(read_kv(BM) or [("ddg", HOME)], "marks"))
    btn("hist", lambda: pick(read_kv(HIST), "history"))
    btn("pic", toggle_pics)

    find_ent.bind("<Return>", foot_enter)
    find_ent.bind("<Escape>", lambda e: hide_find())
    lst.bind("<Double-1>", lambda e: lst.curselection() and go(lst.urls[lst.curselection()[0]]))
    root.bind("<Alt-Left>", lambda e: back())
    root.bind("<F5>", lambda e: go(urlv.get(), push=False, force=True))
    root.bind("<Control-l>", lambda e: (entry.focus_set(), entry.selection_range(0, "end")))
    root.bind("<Control-f>", lambda e: show_find("find"))
    root.bind("<Control-q>", lambda e: root.destroy())
    root.bind("<Key>", key)
    root.bind("<Escape>", lambda e: hide_find())

    root.after(30, lambda: go(start, push=False))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
