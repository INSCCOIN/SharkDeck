#!/usr/bin/env python3
"""dbrowser — 48-col text browser for SharkDeck.

Stdlib only. No JS, no CSS layout.

  dbrowser
  dbrowser https://example.com
  dbrowser file:///home/working/index.html
"""

import curses
import html
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

NAME = "dbrowser"
COLS_SOFT = 48
MAX_BODY = 400000
TIMEOUT = 15
BM_FILE = os.path.expanduser("~/.dbrowser.bookmarks")
UA = "dbrowser/1.0 (SharkDeck; +https://sharkdeck.dev/docs)"


def clip(s, n):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "~"


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.skip = 0
        self.chunks = []
        self.links = []
        self.title = ""
        self._intitle = False
        self._href = None
        self._link_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "title":
            self._intitle = True
        if tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"):
            self.chunks.append("\n")
        if tag == "li":
            self.chunks.append(" * ")
        if tag == "a":
            href = attrs.get("href") or ""
            self._href = urllib.parse.urljoin(self.base, href)
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "title":
            self._intitle = False
        if tag == "a" and self._href:
            text = " ".join("".join(self._link_text).split()) or self._href
            n = len(self.links) + 1
            self.links.append((n, text, self._href))
            self.chunks.append("[%d %s]" % (n, text))
            self._href = None
            self._link_text = []

    def handle_data(self, data):
        if self.skip:
            return
        if self._intitle:
            self.title += data
            return
        if self._href is not None:
            self._link_text.append(data)
            return
        self.chunks.append(data)


def fetch(url):
    if url.startswith("file://"):
        path = urllib.parse.urlparse(url).path
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BODY)
        return raw, "text/html"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        ctype = resp.headers.get_content_type() or "text/html"
        raw = resp.read(MAX_BODY)
        final = resp.geturl()
    return raw, ctype, final


def load(url):
    raw = ctype = final = None
    try:
        got = fetch(url)
        if len(got) == 2:
            raw, ctype = got
            final = url
        else:
            raw, ctype, final = got
    except Exception as exc:
        return {"url": url, "title": "error", "lines": [str(exc)], "links": []}
    if ctype and ctype.startswith("text/plain"):
        text = raw.decode("utf-8", errors="replace")
        return {"url": final, "title": final, "lines": wrap(text), "links": []}
    html_text = raw.decode("utf-8", errors="replace")
    p = PageParser(final)
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    text = html.unescape("".join(p.chunks))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    title = " ".join(p.title.split()) or final
    return {"url": final, "title": title, "lines": wrap(text.strip()), "links": p.links}


def wrap(text, width=COLS_SOFT):
    lines = []
    for para in text.splitlines() or [""]:
        para = para.rstrip()
        if not para:
            lines.append("")
            continue
        while para:
            if len(para) <= width:
                lines.append(para)
                break
            cut = para.rfind(" ", 0, width)
            if cut < 8:
                cut = width
            lines.append(para[:cut])
            para = para[cut:].lstrip()
    return lines or [""]


def read_bm():
    if not os.path.exists(BM_FILE):
        return [
            ("example", "https://example.com"),
            ("sharkdeck docs", "https://sharkdeck.dev/docs"),
        ]
    out = []
    with open(BM_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, url = line.split("|", 1)
            out.append((name.strip(), url.strip()))
    return out


def write_bm(rows):
    with open(BM_FILE, "w", encoding="utf-8") as fh:
        for name, url in rows:
            fh.write("%s|%s\n" % (name, url))


class App:
    def __init__(self, start):
        self.stack = []
        self.fwd = []
        self.page = load(start)
        self.scroll = 0
        self.msg = self.page["url"]

    def go(self, url, push=True):
        if not url:
            return
        if "://" not in url:
            if self.page.get("url"):
                url = urllib.parse.urljoin(self.page["url"], url)
            else:
                url = "https://" + url
        if push and self.page:
            self.stack.append(self.page)
            self.fwd.clear()
        self.page = load(url)
        self.scroll = 0
        self.msg = self.page["url"]

    def back(self):
        if not self.stack:
            self.msg = "no back"
            return
        self.fwd.append(self.page)
        self.page = self.stack.pop()
        self.scroll = 0
        self.msg = self.page["url"]

    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        title = clip(self.page.get("title") or NAME, w)
        try:
            stdscr.addnstr(0, 0, title.ljust(w)[:w], w, curses.A_REVERSE)
        except curses.error:
            pass
        body_h = max(1, h - 3)
        lines = self.page.get("lines") or [""]
        if self.scroll > max(0, len(lines) - body_h):
            self.scroll = max(0, len(lines) - body_h)
        for i in range(body_h):
            li = self.scroll + i
            if li >= len(lines):
                break
            try:
                stdscr.addnstr(1 + i, 0, lines[li][:w], w)
            except curses.error:
                pass
        bar = "g go  # link  b back  m mark  B marks  q"
        try:
            stdscr.addnstr(h - 2, 0, clip(self.msg, w).ljust(w)[:w], w, curses.A_REVERSE)
            stdscr.addnstr(h - 1, 0, bar[:w].ljust(w)[:w], w)
        except curses.error:
            pass
        stdscr.refresh()

    def prompt(self, stdscr, title, default=""):
        curses.echo()
        curses.curs_set(1)
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(h - 1, 0, " " * w, w)
        stdscr.addnstr(h - 1, 0, (title + " ")[:w], w)
        stdscr.refresh()
        try:
            raw = stdscr.getstr(h - 1, min(w - 1, len(title) + 1), max(8, w - 12))
            text = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            text = ""
        curses.noecho()
        curses.curs_set(0)
        return text or None

    def pick(self, stdscr, title, rows):
        if not rows:
            self.msg = "empty"
            return None
        h, w = stdscr.getmaxyx()
        cur = 0
        while True:
            stdscr.erase()
            stdscr.addnstr(0, 0, title[:w], w, curses.A_REVERSE)
            vis = h - 2
            top = max(0, min(cur - vis + 1, max(0, len(rows) - vis)))
            for i in range(vis):
                idx = top + i
                if idx >= len(rows):
                    break
                attr = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                stdscr.addnstr(1 + i, 0, rows[idx][:w], w, attr)
            stdscr.refresh()
            k = stdscr.getch()
            if k in (27, ord("q")):
                return None
            if k == curses.KEY_UP:
                cur = max(0, cur - 1)
            elif k == curses.KEY_DOWN:
                cur = min(len(rows) - 1, cur + 1)
            elif k in (10, 13):
                return cur

    def run(self, stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        while True:
            self.draw(stdscr)
            k = stdscr.getch()
            if k in (ord("q"), 27):
                break
            elif k == curses.KEY_DOWN:
                self.scroll += 1
            elif k == curses.KEY_UP:
                self.scroll = max(0, self.scroll - 1)
            elif k == curses.KEY_NPAGE:
                self.scroll += 8
            elif k == curses.KEY_PPAGE:
                self.scroll = max(0, self.scroll - 8)
            elif k == ord("b"):
                self.back()
            elif k == ord("g"):
                url = self.prompt(stdscr, "url", self.page.get("url") or "")
                if url:
                    self.go(url)
            elif k == ord("m"):
                name = self.prompt(stdscr, "mark name", self.page.get("title") or "page")
                if name:
                    rows = read_bm()
                    rows.append((name, self.page.get("url") or ""))
                    write_bm(rows)
                    self.msg = "marked"
            elif k == ord("B"):
                rows = read_bm()
                labels = ["%s  %s" % (n, u) for n, u in rows]
                idx = self.pick(stdscr, "bookmarks", labels)
                if idx is not None:
                    self.go(rows[idx][1])
            elif k in (ord("l"), ord("#")):
                if not self.page.get("links"):
                    self.msg = "no links"
                    continue
                labels = ["%d %s" % (n, clip(t, 40)) for n, t, _u in self.page["links"]]
                idx = self.pick(stdscr, "links", labels)
                if idx is not None:
                    self.go(self.page["links"][idx][2])
            elif ord("1") <= k <= ord("9"):
                n = k - ord("0")
                hits = [u for num, _t, u in self.page.get("links") or [] if num == n]
                if hits:
                    self.go(hits[0])
                else:
                    self.msg = "no [%d]" % n


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    if not sys.stdout.isatty():
        page = load(start)
        print(page["title"])
        print(page["url"])
        print()
        print("\n".join(page["lines"][:40]))
        return 0
    curses.wrapper(lambda s: App(start).run(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
