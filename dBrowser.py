#!/usr/bin/env python3
"""dbrowser GUI — tiny Tk front end for SharkDeck (480x320).

No WebKit. Fetches HTML and shows text + a link list.
Needs python3-tk and a display ($DISPLAY).

  dbrowser-gui
  dbrowser-gui https://example.com
"""

import html
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

NAME = "dbrowser"
GEOM = "480x304+0+0"
FONT = ("TkFixedFont", 8)
MAX_BODY = 400000
TIMEOUT = 15
BM_FILE = os.path.expanduser("~/.dbrowser.bookmarks")
UA = "dbrowser/1.0 (SharkDeck GUI)"


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
            self._href = urllib.parse.urljoin(self.base, attrs.get("href") or "")
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
            self.links.append((text, self._href))
            self.chunks.append("[%s]" % text)
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


def fetch_page(url):
    if "://" not in url:
        url = "https://" + url
    if url.startswith("file://"):
        path = urllib.parse.urlparse(url).path
        raw = open(path, "rb").read(MAX_BODY)
        return url, raw, "text/html"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.geturl(), resp.read(MAX_BODY), (resp.headers.get_content_type() or "text/html")


def parse_page(url):
    try:
        final, raw, ctype = fetch_page(url)
    except Exception as exc:
        return {"url": url, "title": "error", "text": str(exc), "links": []}
    if ctype.startswith("text/plain"):
        text = raw.decode("utf-8", errors="replace")
        return {"url": final, "title": final, "text": text, "links": []}
    p = PageParser(final)
    try:
        p.feed(raw.decode("utf-8", errors="replace"))
        p.close()
    except Exception:
        pass
    text = html.unescape("".join(p.chunks))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    title = " ".join(p.title.split()) or final
    return {"url": final, "title": title, "text": text, "links": p.links}


def read_bm():
    if not os.path.exists(BM_FILE):
        return [("example", "https://example.com"), ("docs", "https://sharkdeck.dev/docs")]
    rows = []
    for line in open(BM_FILE, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "|" in line:
            n, u = line.split("|", 1)
            rows.append((n.strip(), u.strip()))
    return rows


def write_bm(rows):
    with open(BM_FILE, "w", encoding="utf-8") as fh:
        for n, u in rows:
            fh.write("%s|%s\n" % (n, u))


def main():
    try:
        import tkinter as tk
        from tkinter import simpledialog
        from tkinter.scrolledtext import ScrolledText
    except ImportError:
        sys.stderr.write("need python3-tk:  apt install -y python3-tk\n")
        return 2
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        sys.stderr.write("no DISPLAY. start X or use: dbrowser URL\n")
        return 2

    start = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    hist = []

    root = tk.Tk()
    root.title(NAME)
    root.geometry(GEOM)
    root.resizable(True, True)

    top = tk.Frame(root)
    top.pack(fill="x")
    url_var = tk.StringVar(value=start)

    body = ScrolledText(root, font=FONT, wrap="word", height=10)
    links = tk.Listbox(root, font=FONT, height=5)

    def show(page):
        url_var.set(page["url"])
        root.title(clip := (page["title"][:40] or NAME))
        body.delete("1.0", "end")
        body.insert("1.0", page["text"] or "(empty)")
        links.delete(0, "end")
        for text, href in page["links"][:80]:
            links.insert("end", text[:60])
        links.links = page["links"][:80]
        body.see("1.0")

    def go(url=None, push=True):
        url = (url or url_var.get()).strip()
        if not url:
            return
        if push and url_var.get():
            hist.append(url_var.get())
        root.config(cursor="watch")
        root.update_idletasks()
        page = parse_page(url)
        root.config(cursor="")
        show(page)

    def back():
        if not hist:
            return
        go(hist.pop(), push=False)

    def follow(_evt=None):
        sel = links.curselection()
        if not sel:
            return
        href = links.links[sel[0]][1]
        go(href)

    def mark():
        name = simpledialog.askstring(NAME, "bookmark name", parent=root)
        if name:
            rows = read_bm()
            rows.append((name, url_var.get()))
            write_bm(rows)

    def marks():
        rows = read_bm()
        if not rows:
            return
        win = tk.Toplevel(root)
        win.title("marks")
        win.geometry("420x200")
        lb = tk.Listbox(win, font=FONT)
        lb.pack(fill="both", expand=True)
        for n, u in rows:
            lb.insert("end", "%s  %s" % (n, u))

        def pick(_e=None):
            i = lb.curselection()
            if i:
                go(rows[i[0]][1])
                win.destroy()

        lb.bind("<Double-1>", pick)
        tk.Button(win, text="open", command=pick).pack()

    tk.Button(top, text="back", command=back, font=FONT).pack(side="left")
    tk.Button(top, text="go", command=go, font=FONT).pack(side="right")
    tk.Button(top, text="mark", command=mark, font=FONT).pack(side="right")
    tk.Button(top, text="marks", command=marks, font=FONT).pack(side="right")
    entry = tk.Entry(top, textvariable=url_var, font=FONT)
    entry.pack(side="left", fill="x", expand=True, padx=2)
    entry.bind("<Return>", lambda e: go())
    body.pack(fill="both", expand=True)
    links.pack(fill="x")
    links.bind("<Double-1>", follow)

    root.after(100, lambda: go(start, push=False))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
