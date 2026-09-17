#!/usr/bin/env python3
"""dbrowser GUI — 480x320 Tk browser for SharkDeck. No WebKit."""

import html
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

NAME = "dbrowser"
GEOM = "480x320+0+0"
FONT = ("TkFixedFont", 8)
MAX_BODY = 500000
TIMEOUT = 15
HOME = "https://example.com"
SEARCH = "https://lite.duckduckgo.com/lite/?q=%s"
BM_FILE = os.path.expanduser("~/.dbrowser.bookmarks")
HIST_FILE = os.path.expanduser("~/.dbrowser.history")
UA = "dbrowser/1.1 (SharkDeck GUI)"


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.skip = 0
        self.chunks = []
        self.links = []
        self.images = []
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
        if tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "section"):
            self.chunks.append("\n")
        if tag == "li":
            self.chunks.append(" * ")
        if tag == "img":
            src = attrs.get("src") or attrs.get("data-src") or ""
            if src and not src.startswith("data:"):
                self.images.append(urllib.parse.urljoin(self.base, src))
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
        if " " in url or "." not in url:
            url = SEARCH % urllib.parse.quote_plus(url)
        else:
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
        return {"url": url, "title": "error", "text": str(exc), "links": [], "images": []}
    if ctype.startswith("text/plain"):
        text = raw.decode("utf-8", errors="replace")
        return {"url": final, "title": final, "text": text, "links": [], "images": []}
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
    imgs = []
    seen = set()
    for src in p.images:
        if src not in seen:
            seen.add(src)
            imgs.append(src)
    return {
        "url": final,
        "title": title,
        "text": text,
        "links": p.links,
        "images": imgs[:8],
    }


def read_lines(path, fallback=None):
    if not os.path.exists(path):
        return list(fallback or [])
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "|" in line:
            a, b = line.split("|", 1)
            rows.append((a.strip(), b.strip()))
    return rows


def fetch_thumb(url, max_px=72, max_bytes=25000):
    """Tiny image for the text widget. Prefer Pillow; GIF/PNG via Tk."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read(max_bytes + 1)
            ctype = (resp.headers.get_content_type() or "").lower()
        if len(data) > max_bytes:
            return None
    except Exception:
        return None
    tmp = "/tmp/dbrowser-thumb"
    try:
        from PIL import Image, ImageTk
        import io
        im = Image.open(io.BytesIO(data))
        im.thumbnail((max_px, max_px))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        return ImageTk.PhotoImage(im)
    except Exception:
        pass
    if "gif" in ctype or "png" in ctype or url.lower().endswith((".gif", ".png")):
        try:
            import tkinter as tk
            ext = ".gif" if "gif" in ctype or url.lower().endswith(".gif") else ".png"
            path = tmp + ext
            open(path, "wb").write(data)
            img = tk.PhotoImage(file=path)
            factor = max(1, int(max(img.width(), img.height()) / float(max_px)))
            if factor > 1:
                img = img.subsample(factor, factor)
            return img
        except Exception:
            return None
    return None


def write_lines(path, rows, cap=80):
    with open(path, "w", encoding="utf-8") as fh:
        for a, b in rows[:cap]:
            fh.write("%s|%s\n" % (a, b))


def main():
    try:
        import tkinter as tk
        from tkinter import simpledialog, filedialog
        from tkinter.scrolledtext import ScrolledText
    except ImportError:
        sys.stderr.write("apt install -y python3-tk\n")
        return 2

    start = sys.argv[1] if len(sys.argv) > 1 else HOME
    hist = []
    page = {"url": start, "title": NAME, "text": "", "links": [], "images": []}
    find_pos = "1.0"
    thumbs = []
    body_links = []

    root = tk.Tk()
    root.title(NAME)
    root.geometry(GEOM)
    root.minsize(480, 280)

    url_var = tk.StringVar(value=start)
    status = tk.StringVar(value="ready")

    top = tk.Frame(root)
    top.pack(fill="x")
    mid = tk.Frame(root)
    mid.pack(fill="x")
    body = ScrolledText(root, font=FONT, wrap="word", height=9)
    body.pack(fill="both", expand=True)
    links = tk.Listbox(root, font=FONT, height=4)
    links.pack(fill="x")
    tk.Label(root, textvariable=status, font=FONT, anchor="w").pack(fill="x")

    def set_status(msg):
        status.set(msg[:70])
        root.update_idletasks()

    def click_body_link(event):
        idx = body.index("@%d,%d" % (event.x, event.y))
        tags = body.tag_names(idx)
        for t in tags:
            if t.startswith("lnk"):
                i = int(t[3:])
                if 0 <= i < len(body_links):
                    go(body_links[i])
                return

    def show(p):
        nonlocal page, find_pos, thumbs, body_links
        page = p
        url_var.set(p["url"])
        root.title((p["title"] or NAME)[:48])
        for t in list(body.tag_names()):
            if t.startswith("lnk"):
                body.tag_delete(t)
        body.delete("1.0", "end")
        text = p.get("text") or "(empty)"
        body.insert("1.0", text)
        body_links = []
        search_from = "1.0"
        for lab, href in (p.get("links") or [])[:80]:
            needle = "[" + lab + "]"
            idx = body.search(needle, search_from, "end")
            if not idx:
                continue
            end = "%s+%dc" % (idx, len(needle))
            tag = "lnk%d" % len(body_links)
            body.tag_add(tag, idx, end)
            body.tag_config(tag, foreground="blue", underline=1)
            body.tag_bind(tag, "<Button-1>", click_body_link)
            body_links.append(href)
            search_from = end
        thumbs = []
        imgs = p.get("images") or []
        if imgs:
            body.insert("end", "\n\n")
            set_status("thumbs %d..." % len(imgs))
            root.update_idletasks()
            for src in imgs[:5]:
                im = fetch_thumb(src)
                if im is None:
                    continue
                thumbs.append(im)
                body.image_create("end", image=im)
                body.insert("end", " ")
        links.delete(0, "end")
        links.links = p.get("links") or []
        links.links = links.links[:100]
        for i, (text_l, href) in enumerate(links.links, 1):
            links.insert("end", "%d %s" % (i, text_l[:50]))
        find_pos = "1.0"
        set_status("%d links  %d imgs" % (len(p.get("links") or []), len(thumbs)))
        body.see("1.0")

    def remember(url, title):
        rows = read_lines(HIST_FILE, [])
        rows = [(title or url, url)] + [r for r in rows if r[1] != url]
        write_lines(HIST_FILE, rows, 60)

    def go(url=None, push=True):
        url = (url if url is not None else url_var.get()).strip()
        if not url:
            return
        if push and page.get("url"):
            hist.append(page["url"])
        set_status("loading...")
        root.config(cursor="watch")
        root.update()
        p = parse_page(url)
        root.config(cursor="")
        show(p)
        remember(p["url"], p["title"])

    def back():
        if hist:
            go(hist.pop(), push=False)

    def home():
        go(HOME)

    def reload_page():
        go(url_var.get(), push=False)

    def search():
        q = simpledialog.askstring(NAME, "search", parent=root)
        if q:
            go(SEARCH % urllib.parse.quote_plus(q))

    def follow(_e=None):
        sel = links.curselection()
        if sel:
            go(links.links[sel[0]][1])

    def mark():
        name = simpledialog.askstring(NAME, "bookmark name", parent=root, initialvalue=page.get("title") or "")
        if name:
            rows = read_lines(BM_FILE, [("example", "https://example.com")])
            rows.append((name, url_var.get()))
            write_lines(BM_FILE, rows)

    def pick_list(title, rows):
        if not rows:
            set_status("empty")
            return
        win = tk.Toplevel(root)
        win.title(title)
        win.geometry("460x220+0+20")
        lb = tk.Listbox(win, font=FONT)
        lb.pack(fill="both", expand=True)
        for n, u in rows:
            lb.insert("end", "%s  %s" % (n[:24], u[:40]))

        def pick(_e=None):
            i = lb.curselection()
            if i:
                go(rows[i[0]][1])
                win.destroy()

        lb.bind("<Double-1>", pick)
        lb.bind("<Return>", pick)
        tk.Button(win, text="open", command=pick, font=FONT).pack()

    def marks():
        pick_list("marks", read_lines(BM_FILE, [("example", HOME)]))

    def history():
        pick_list("history", read_lines(HIST_FILE, []))

    def copy_url():
        root.clipboard_clear()
        root.clipboard_append(url_var.get())
        set_status("copied")

    def save_txt():
        path = filedialog.asksaveasfilename(parent=root, defaultextension=".txt", initialfile="page.txt")
        if path:
            open(path, "w", encoding="utf-8").write(page.get("text") or "")
            set_status("saved " + path)

    def find():
        nonlocal find_pos
        q = simpledialog.askstring(NAME, "find", parent=root)
        if not q:
            return
        body.tag_remove("hit", "1.0", "end")
        idx = body.search(q, find_pos, "end", nocase=True)
        if not idx:
            idx = body.search(q, "1.0", "end", nocase=True)
        if not idx:
            set_status("no match")
            return
        end = "%s+%dc" % (idx, len(q))
        body.tag_add("hit", idx, end)
        body.tag_config("hit", background="yellow")
        body.see(idx)
        find_pos = end
        set_status("found")

    def bigger():
        size = FONT[1] + 1
        body.configure(font=(FONT[0], size))

    def smaller():
        size = max(6, FONT[1] - 1)
        body.configure(font=(FONT[0], size))

    def btn(parent, label, cmd):
        tk.Button(parent, text=label, command=cmd, font=FONT, padx=2).pack(side="left")

    btn(top, "back", back)
    btn(top, "home", home)
    btn(top, "rel", reload_page)
    entry = tk.Entry(top, textvariable=url_var, font=FONT)
    entry.pack(side="left", fill="x", expand=True, padx=2)
    entry.bind("<Return>", lambda e: go())
    btn(top, "go", go)

    btn(mid, "find", find)
    btn(mid, "search", search)
    btn(mid, "mark", mark)
    btn(mid, "marks", marks)
    btn(mid, "hist", history)
    btn(mid, "copy", copy_url)
    btn(mid, "save", save_txt)
    btn(mid, "a+", bigger)
    btn(mid, "a-", smaller)
    btn(mid, "quit", root.destroy)

    links.bind("<Double-1>", follow)
    links.bind("<Return>", follow)
    root.bind("<Alt-Left>", lambda e: back())
    root.bind("<F5>", lambda e: reload_page())
    root.bind("<Control-f>", lambda e: find())
    root.bind("<Control-l>", lambda e: (entry.focus_set(), entry.selection_range(0, "end")))
    root.bind("<Control-s>", lambda e: save_txt())
    root.bind("<Control-q>", lambda e: root.destroy())

    root.after(80, lambda: go(start, push=False))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
