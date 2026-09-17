#!/usr/bin/env python3
"""dBrowser — compact text+thumb browser for SharkDeck 480x320."""

import html
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

NAME = "dBrowser"
HOME = "https://example.com"
SEARCH = "https://lite.duckduckgo.com/lite/?q=%s"
BM = os.path.expanduser("~/.dbrowser.bookmarks")
HIST = os.path.expanduser("~/.dbrowser.history")
UA = "dBrowser/2 (SharkDeck)"
MAX_BODY = 350000
CACHE_N = 6
THUMB_N = 4
THUMB_PX = 64
THUMB_B = 20000

OPENER = urllib.request.build_opener()
OPENER.addheaders = [("User-Agent", UA)]


class PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.skip = 0
        self.buf = []
        self.links = []
        self.images = []
        self.title = ""
        self._title = False
        self._href = None
        self._ltxt = []

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag in self.SKIP:
                self.skip += 1
            return
        if tag in self.SKIP:
            self.skip = 1
            return
        ad = dict(attrs)
        if tag == "title":
            self._title = True
        elif tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "section", "blockquote"):
            self.buf.append("\n")
            if tag == "li":
                self.buf.append("* ")
        elif tag == "img":
            src = ad.get("src") or ad.get("data-src") or ""
            if src and not src.startswith("data:"):
                self.images.append(urllib.parse.urljoin(self.base, src))
        elif tag == "a":
            self._href = urllib.parse.urljoin(self.base, ad.get("href") or "")
            self._ltxt = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "title":
            self._title = False
        elif tag == "a" and self._href:
            lab = " ".join("".join(self._ltxt).split()) or self._href
            self.links.append((lab, self._href))
            self.buf.append("<%s>" % lab)
            self._href = None

    def handle_data(self, data):
        if self.skip:
            return
        if self._title:
            self.title += data
        elif self._href is not None:
            self._ltxt.append(data)
        else:
            self.buf.append(data)


def resolve(raw, current=""):
    raw = (raw or "").strip()
    if not raw:
        return current
    if "://" in raw or raw.startswith("file:"):
        return raw
    if " " in raw or "." not in raw:
        return SEARCH % urllib.parse.quote_plus(raw)
    return "https://" + raw


def http_get(url, limit=MAX_BODY, timeout=12):
    if url.startswith("file://"):
        data = open(urllib.parse.urlparse(url).path, "rb").read(limit)
        return url, data, "text/html"
    resp = OPENER.open(url, timeout=timeout)
    try:
        return resp.geturl(), resp.read(limit), (resp.headers.get_content_type() or "text/html")
    finally:
        resp.close()


def load_page(url):
    try:
        final, raw, ctype = http_get(url)
    except Exception as exc:
        return {"url": url, "title": "error", "text": str(exc), "links": [], "images": []}
    if ctype.startswith("text/plain"):
        return {
            "url": final, "title": final,
            "text": raw.decode("utf-8", "replace"), "links": [], "images": [],
        }
    p = PageParser(final)
    try:
        p.feed(raw.decode("utf-8", "replace"))
        p.close()
    except Exception:
        pass
    text = html.unescape("".join(p.buf))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    seen, imgs = set(), []
    for src in p.images:
        if src not in seen:
            seen.add(src)
            imgs.append(src)
    return {
        "url": final,
        "title": " ".join(p.title.split()) or final,
        "text": text,
        "links": p.links,
        "images": imgs[:8],
    }


def read_kv(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and "|" in line and not line.startswith("#"):
                a, b = line.split("|", 1)
                out.append((a.strip(), b.strip()))
    return out


def write_kv(path, rows, cap=50):
    with open(path, "w", encoding="utf-8") as fh:
        for a, b in rows[:cap]:
            fh.write("%s|%s\n" % (a, b))


def thumb(url):
    try:
        _u, data, ctype = http_get(url, limit=THUMB_B, timeout=5)
    except Exception:
        return None
    if len(data) >= THUMB_B:
        return None
    try:
        from PIL import Image, ImageTk
        import io
        im = Image.open(io.BytesIO(data))
        im.thumbnail((THUMB_PX, THUMB_PX))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        return ImageTk.PhotoImage(im)
    except Exception:
        pass
    if "png" not in ctype and "gif" not in ctype:
        return None
    try:
        import tkinter as tk
        path = "/tmp/dbr" + (".gif" if "gif" in ctype else ".png")
        open(path, "wb").write(data)
        img = tk.PhotoImage(file=path)
        f = max(1, max(img.width(), img.height()) // THUMB_PX)
        return img.subsample(f, f) if f > 1 else img
    except Exception:
        return None


def main():
    try:
        import tkinter as tk
        from tkinter import simpledialog, filedialog
    except ImportError:
        sys.stderr.write("apt install -y python3-tk\n")
        return 2

    start = resolve(sys.argv[1] if len(sys.argv) > 1 else HOME)
    cache = {}
    order = []
    hist = []
    page = {"url": start, "title": NAME, "text": "", "links": [], "images": []}
    photos = []
    tagged = []
    find_at = "1.0"
    show_pics = False

    BG, FG, ACC, BAR = "#111111", "#e6e6e6", "#7ad", "#1c1c1c"
    root = tk.Tk()
    root.title(NAME)
    root.geometry("480x320+0+0")
    root.configure(bg=BG)
    root.option_add("*Font", "TkFixedFont 9")
    root.option_add("*Background", BG)
    root.option_add("*Foreground", FG)
    root.option_add("*Entry.Background", "#000000")
    root.option_add("*Entry.Foreground", FG)
    root.option_add("*Text.Background", "#000000")
    root.option_add("*Text.Foreground", FG)
    root.option_add("*Listbox.Background", "#000000")
    root.option_add("*Listbox.Foreground", FG)
    root.option_add("*Button.Background", BAR)
    root.option_add("*Button.Foreground", ACC)
    root.option_add("*Button.Relief", "flat")
    root.option_add("*Button.BorderWidth", 0)
    root.option_add("*HighlightThickness", 0)

    urlv = tk.StringVar(value=start)
    stv = tk.StringVar(value="")

    bar = tk.Frame(root, bg=BAR)
    bar.pack(fill="x")
    body = tk.Text(root, wrap="word", bd=0, highlightthickness=0, undo=False, height=12)
    body.pack(fill="both", expand=True)
    yscroll = tk.Scrollbar(body, command=body.yview, bg=BAR, troughcolor=BG, width=8)
    body.configure(yscrollcommand=yscroll.set)
    yscroll.pack(side="right", fill="y")
    lst = tk.Listbox(root, height=3, bd=0, highlightthickness=0, activestyle="none")
    lst.pack(fill="x")
    tk.Label(root, textvariable=stv, bg=BAR, fg="#888888", anchor="w").pack(fill="x")

    def say(msg):
        stv.set(msg[:72])
        root.update_idletasks()

    def b(txt, cmd):
        w = tk.Button(bar, text=txt, command=cmd, padx=4, pady=1)
        w.pack(side="left")
        return w

    def put_cache(p):
        cache[p["url"]] = p
        if p["url"] in order:
            order.remove(p["url"])
        order.append(p["url"])
        while len(order) > CACHE_N:
            cache.pop(order.pop(0), None)

    def click_tag(e):
        names = body.tag_names(body.index("@%d,%d" % (e.x, e.y)))
        for t in names:
            if t.startswith("a") and t[1:].isdigit():
                i = int(t[1:])
                if i < len(tagged):
                    go(tagged[i])
                return

    def paint(p):
        nonlocal page, tagged, photos, find_at
        page = p
        urlv.set(p["url"])
        root.title((p["title"] or NAME)[:48])
        body.delete("1.0", "end")
        for t in body.tag_names():
            if t.startswith("a"):
                body.tag_delete(t)
        text = p["text"] or "(empty)"
        body.insert("1.0", text)
        tagged = []
        at = "1.0"
        for lab, href in p["links"][:60]:
            needle = "<%s>" % lab
            idx = body.search(needle, at, "end")
            if not idx:
                continue
            end = "%s+%dc" % (idx, len(needle))
            tag = "a%d" % len(tagged)
            body.tag_add(tag, idx, end)
            body.tag_config(tag, foreground=ACC, underline=1)
            body.tag_bind(tag, "<Button-1>", click_tag)
            tagged.append(href)
            at = end
        photos = []
        if show_pics:
            for src in p["images"][:THUMB_N]:
                im = thumb(src)
                if im:
                    photos.append(im)
                    body.insert("end", "\n")
                    body.image_create("end", image=im)
        lst.delete(0, "end")
        lst.urls = [h for _l, h in p["links"][:80]]
        for i, (lab, _h) in enumerate(p["links"][:80], 1):
            lst.insert("end", "%d %s" % (i, lab[:44]))
        find_at = "1.0"
        say("%d links   j/k scroll  1-9 open  / find  g url" % len(p["links"]))
        body.see("1.0")
        body.focus_set()

    def go(url=None, push=True):
        url = resolve(url if url is not None else urlv.get(), page.get("url"))
        if not url:
            return
        if push and page.get("url") and page["url"] != url:
            hist.append(page["url"])
        if url in cache:
            paint(cache[url])
            return
        say("...")
        root.config(cursor="watch")
        root.update()
        p = load_page(url)
        root.config(cursor="")
        put_cache(p)
        rows = read_kv(HIST)
        rows = [(p["title"], p["url"])] + [r for r in rows if r[1] != p["url"]]
        write_kv(HIST, rows)
        paint(p)

    def back():
        if hist:
            go(hist.pop(), push=False)

    def ask(title):
        return simpledialog.askstring(NAME, title, parent=root)

    def search():
        q = ask("search")
        if q:
            go(SEARCH % urllib.parse.quote_plus(q))

    def find():
        nonlocal find_at
        q = ask("find")
        if not q:
            return
        body.tag_remove("hit", "1.0", "end")
        idx = body.search(q, find_at, "end", nocase=True) or body.search(q, "1.0", "end", nocase=True)
        if not idx:
            say("no match")
            return
        end = "%s+%dc" % (idx, len(q))
        body.tag_add("hit", idx, end)
        body.tag_config("hit", background="#444400", foreground="#ffffff")
        body.see(idx)
        find_at = end

    def pick(rows, title):
        if not rows:
            say("empty")
            return
        w = tk.Toplevel(root)
        w.configure(bg=BG)
        w.geometry("460x200+8+24")
        w.title(title)
        lb = tk.Listbox(w, height=8)
        lb.pack(fill="both", expand=True)
        for n, u in rows:
            lb.insert("end", "%s  %s" % (n[:20], u[:36]))

        def ok(_e=None):
            i = lb.curselection()
            if i:
                go(rows[i[0]][1])
                w.destroy()

        lb.bind("<Double-1>", ok)
        lb.bind("<Return>", ok)
        lb.focus_set()

    def mark():
        name = ask("name") or page.get("title")
        if name:
            write_kv(BM, read_kv(BM) + [(name, urlv.get())])
            say("marked")

    def pics():
        nonlocal show_pics
        show_pics = not show_pics
        paint(page)

    def copyu():
        root.clipboard_clear()
        root.clipboard_append(urlv.get())
        say("copied")

    def save():
        path = filedialog.asksaveasfilename(parent=root, defaultextension=".txt")
        if path:
            open(path, "w", encoding="utf-8").write(page.get("text") or "")
            say("saved")

    def open_list(_e=None):
        i = lst.curselection()
        if i:
            go(lst.urls[i[0]])

    def key(e):
        if e.widget == entry:
            return
        ch = e.char
        if ch == "j":
            body.yview_scroll(3, "units")
        elif ch == "k":
            body.yview_scroll(-3, "units")
        elif ch == "g":
            entry.focus_set()
            entry.selection_range(0, "end")
        elif ch == "b":
            back()
        elif ch == "/":
            find()
        elif ch == "s":
            search()
        elif ch == "q":
            root.destroy()
        elif ch.isdigit() and ch != "0":
            n = int(ch) - 1
            if n < len(getattr(lst, "urls", [])):
                go(lst.urls[n])

    b("<-", back)
    entry = tk.Entry(bar, textvariable=urlv, relief="flat", insertbackground=FG)
    entry.pack(side="left", fill="x", expand=True, padx=4, ipady=2)
    entry.bind("<Return>", lambda e: go())
    b("go", go)
    b("find", find)
    b("ddg", search)
    b("*", mark)
    b("marks", lambda: pick(read_kv(BM) or [("ex", HOME)], "marks"))
    b("hist", lambda: pick(read_kv(HIST), "hist"))
    b("pic", pics)
    b("copy", copyu)

    lst.bind("<Double-1>", open_list)
    lst.bind("<Return>", open_list)
    root.bind("<Alt-Left>", lambda e: back())
    root.bind("<F5>", lambda e: go(urlv.get(), push=False))
    root.bind("<Control-l>", lambda e: (entry.focus_set(), entry.selection_range(0, "end")))
    root.bind("<Control-f>", lambda e: find())
    root.bind("<Control-q>", lambda e: root.destroy())
    root.bind("<Key>", key)

    root.after(50, lambda: go(start, push=False))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
