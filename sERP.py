#!/usr/bin/env python3
"""sERP — handheld ERP for SharkDeck.

CLI + sCMD-style curses UI. Money in integer cents.
Data: ~/.serp/

  serp
  serp stock
  serp recv SKU QTY
  serp ship SKU QTY
  serp item add SKU NAME [price]
  serp party add NAME customer|vendor
  serp so PARTY SKU QTY
"""

import argparse
import curses
import curses.textpad
import json
import os
import sys
import time
from datetime import datetime

NAME = "sERP"
ROOT = os.path.expanduser("~/.serp")
ITEMS = os.path.join(ROOT, "items.json")
PARTIES = os.path.join(ROOT, "parties.json")
JOURNAL = os.path.join(ROOT, "journal.jsonl")


def now():
    return datetime.now().isoformat(timespec="seconds")


def ensure():
    os.makedirs(ROOT, exist_ok=True)
    if not os.path.exists(ITEMS):
        save_json(ITEMS, {})
    if not os.path.exists(PARTIES):
        save_json(PARTIES, {})
    if not os.path.exists(JOURNAL):
        open(JOURNAL, "a").close()


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def append_j(rec):
    rec = dict(rec)
    rec["ts"] = rec.get("ts") or now()
    rec["id"] = rec.get("id") or str(int(time.time() * 1000))
    with open(JOURNAL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return rec


def read_j():
    rows = []
    if not os.path.exists(JOURNAL):
        return rows
    with open(JOURNAL, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def money(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return "%s%d.%02d" % (sign, cents // 100, cents % 100)


def parse_money(s):
    s = str(s).strip().replace("$", "")
    if not s:
        return 0
    if "." in s:
        a, b = s.split(".", 1)
        b = (b + "00")[:2]
        return int(a or "0") * 100 + int(b)
    return int(s) * 100


def stock_map():
    qty = {}
    for r in read_j():
        if r.get("type") not in ("recv", "ship", "adj"):
            continue
        sku = r.get("sku")
        if not sku:
            continue
        q = int(r.get("qty") or 0)
        if r["type"] == "ship":
            q = -q
        qty[sku] = qty.get(sku, 0) + q
    return qty


def item_get(sku):
    return load_json(ITEMS).get(sku)


def item_put(sku, **kw):
    items = load_json(ITEMS)
    row = items.get(sku) or {"sku": sku, "name": sku, "price": 0, "cost": 0, "min": 0}
    row.update(kw)
    row["sku"] = sku
    items[sku] = row
    save_json(ITEMS, items)
    return row


def party_put(name, kind="customer"):
    parties = load_json(PARTIES)
    key = name.strip()
    parties[key] = {"name": key, "kind": kind, "since": now()}
    save_json(PARTIES, parties)
    return parties[key]


def cmd_item_add(sku, name, price="0"):
    row = item_put(sku, name=name, price=parse_money(price))
    print("%s  %s  %s" % (row["sku"], row["name"], money(row["price"])))


def cmd_item_ls():
    st = stock_map()
    items = load_json(ITEMS)
    if not items:
        print("(no items)")
        return
    print("%-10s %5s %8s  %s" % ("SKU", "QTY", "PRICE", "NAME"))
    for sku in sorted(items):
        it = items[sku]
        print("%-10s %5d %8s  %s" % (sku, st.get(sku, 0), money(it.get("price") or 0), it.get("name") or ""))


def cmd_stock():
    cmd_item_ls()


def cmd_recv(sku, qty, cost=None):
    if not item_get(sku):
        item_put(sku, name=sku)
    rec = {"type": "recv", "sku": sku, "qty": int(qty)}
    if cost is not None:
        rec["cost"] = parse_money(cost)
        item_put(sku, cost=rec["cost"])
    append_j(rec)
    print("recv %s x%s  on-hand %d" % (sku, qty, stock_map().get(sku, 0)))


def cmd_ship(sku, qty):
    have = stock_map().get(sku, 0)
    q = int(qty)
    if q > have:
        print("only %d on hand" % have)
        return 1
    append_j({"type": "ship", "sku": sku, "qty": q})
    print("ship %s x%s  on-hand %d" % (sku, qty, stock_map().get(sku, 0)))
    return 0


def cmd_so(party, sku, qty):
    parties = load_json(PARTIES)
    if party not in parties:
        party_put(party, "customer")
    if not item_get(sku):
        print("unknown sku", sku)
        return 1
    q = int(qty)
    if cmd_ship(sku, q):
        return 1
    it = item_get(sku)
    price = int(it.get("price") or 0)
    rec = append_j({
        "type": "so",
        "party": party,
        "sku": sku,
        "qty": q,
        "price": price,
        "total": price * q,
    })
    print("SO %s  %s x%s  %s" % (rec["id"][-6:], sku, q, money(rec["total"])))
    return 0


def cmd_party_add(name, kind="customer"):
    row = party_put(name, kind)
    print("%s (%s)" % (row["name"], row["kind"]))


def cmd_party_ls():
    parties = load_json(PARTIES)
    if not parties:
        print("(no parties)")
        return
    for n, p in sorted(parties.items()):
        print("%-16s %s" % (n, p.get("kind")))


def cmd_log(n=20):
    rows = read_j()[-int(n):]
    for r in rows:
        extra = r.get("sku") or r.get("party") or ""
        print("%s  %-4s  %s  %s" % (r.get("ts", "")[5:16], r.get("type"), extra, r.get("qty", "")))


def cmd_low():
    st = stock_map()
    items = load_json(ITEMS)
    hit = False
    for sku, it in sorted(items.items()):
        q = st.get(sku, 0)
        mn = int(it.get("min") or 0)
        if q <= mn:
            print("%-10s %5d  min %d  %s" % (sku, q, mn, it.get("name")))
            hit = True
    if not hit:
        print("none low")


def cmd_value():
    st = stock_map()
    items = load_json(ITEMS)
    total = 0
    for sku, q in st.items():
        cost = int((items.get(sku) or {}).get("cost") or 0)
        total += cost * max(q, 0)
    print("on-hand cost", money(total))


def cmd_adj(sku, qty):
    if not item_get(sku):
        item_put(sku, name=sku)
    q = int(qty)
    append_j({"type": "adj", "sku": sku, "qty": q})
    print("adj %s %+d  on-hand %d" % (sku, q, stock_map().get(sku, 0)))


def cmd_po(vendor, sku, qty, cost=None):
    parties = load_json(PARTIES)
    if vendor not in parties:
        party_put(vendor, "vendor")
    if not item_get(sku):
        item_put(sku, name=sku)
    if cost is not None:
        item_put(sku, cost=parse_money(cost))
    cmd_recv(sku, qty, cost)
    rec = append_j({
        "type": "po",
        "party": vendor,
        "sku": sku,
        "qty": int(qty),
        "cost": parse_money(cost) if cost is not None else int((item_get(sku) or {}).get("cost") or 0),
    })
    print("PO %s  %s x%s" % (rec["id"][-6:], sku, qty))


def cmd_sales():
    total = 0
    n = 0
    for r in read_j():
        if r.get("type") == "so":
            total += int(r.get("total") or 0)
            n += 1
    print("%d sales  %s" % (n, money(total)))


def party_sales(name):
    t = 0
    n = 0
    for r in read_j():
        if r.get("type") == "so" and r.get("party") == name:
            t += int(r.get("total") or 0)
            n += 1
    return n, t


# ---------------- curses ----------------

def clip(s, n):
    s = " ".join(str(s).split())
    if n <= 1:
        return ""
    return s if len(s) <= n else s[: n - 1] + "~"


def put(scr, y, x, text, attr=0):
    try:
        h, w = scr.getmaxyx()
        if y < 0 or x < 0 or y >= h or x >= w:
            return
        room = w - x - (1 if y == h - 1 else 0)
        if room <= 0:
            return
        scr.addnstr(y, x, clip(str(text), room), room, attr)
    except curses.error:
        pass


class Pane:
    def __init__(self, kind):
        self.kind = kind
        self.cursor = 0
        self.scroll = 0
        self.rows = []
        self.filter = ""

    def reload(self):
        self.rows = []
        fl = self.filter.lower()
        if self.kind == "stock":
            st = stock_map()
            items = load_json(ITEMS)
            for sku in sorted(set(list(items) + list(st))):
                it = items.get(sku) or {"name": sku, "price": 0, "min": 0, "bin": ""}
                q = st.get(sku, 0)
                flag = "!" if q <= int(it.get("min") or 0) else " "
                line = "%s%-7s %4d %7s %s" % (
                    flag, sku[:7], q, money(it.get("price") or 0), (it.get("name") or "")[:12],
                )
                blob = (sku + " " + str(it.get("name")) + " " + str(it.get("bin"))).lower()
                if fl and fl not in blob:
                    continue
                self.rows.append({"sku": sku, "line": line, "kind": "item", "low": flag == "!"})
        elif self.kind == "parties":
            for n, p in sorted(load_json(PARTIES).items()):
                if fl and fl not in n.lower() and fl not in p.get("kind", ""):
                    continue
                ns, tot = party_sales(n)
                extra = money(tot) if p.get("kind") == "customer" else p.get("kind")
                self.rows.append({"sku": n, "line": "%-12s %s" % (n[:12], extra), "kind": "party"})
        elif self.kind == "journal":
            for r in reversed(read_j()[-120:]):
                extra = r.get("sku") or r.get("party") or ""
                line = "%s %-4s %s %s" % (
                    str(r.get("ts", ""))[5:16], r.get("type"), extra[:8], r.get("qty", ""),
                )
                if fl and fl not in line.lower():
                    continue
                self.rows.append({"sku": extra, "line": line, "kind": "j"})
        else:
            for r in reversed([x for x in read_j() if x.get("type") in ("so", "po")][-60:]):
                line = "%s %-2s %-8s %sx%s" % (
                    str(r.get("id", ""))[-4:], r.get("type"), str(r.get("party", ""))[:8],
                    r.get("sku"), r.get("qty"),
                )
                if fl and fl not in line.lower():
                    continue
                self.rows.append({"sku": r.get("sku"), "line": line, "kind": "ord"})
        if self.cursor >= len(self.rows):
            self.cursor = max(0, len(self.rows) - 1)

    def move(self, d):
        if not self.rows:
            return
        self.cursor = max(0, min(len(self.rows) - 1, self.cursor + d))

    def current(self):
        if not self.rows:
            return {}
        return self.rows[self.cursor]


class App:
    KINDS = ("stock", "journal", "parties", "orders")

    def __init__(self, stdscr):
        self.scr = stdscr
        self.panes = [Pane("stock"), Pane("journal")]
        self.active = 0
        self.msg = "sERP"
        self.err = False

    @property
    def pane(self):
        return self.panes[self.active]

    def colors(self):
        if not curses.has_colors():
            return
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(6, curses.COLOR_RED, -1)
        curses.init_pair(7, curses.COLOR_GREEN, -1)
        curses.init_pair(8, curses.COLOR_CYAN, -1)
        curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_WHITE)

    def reload(self):
        for p in self.panes:
            p.reload()

    def say(self, t, err=False):
        self.msg = t
        self.err = err

    def prompt(self, title, default=""):
        h, w = self.scr.getmaxyx()
        ph, pw = 5, min(w - 2, 48)
        y, x = max(0, h // 2 - 2), max(0, (w - pw) // 2)
        win = curses.newwin(ph, pw, y, x)
        try:
            win.bkgd(" ", curses.color_pair(4))
        except curses.error:
            pass
        win.box()
        put(win, 1, 2, title)
        win.refresh()
        sub = win.derwin(1, max(8, pw - 4), 3, 2)
        try:
            sub.addstr(0, 0, default[: pw - 4])
        except curses.error:
            pass
        curses.curs_set(1)
        try:
            raw = curses.textpad.Textbox(sub).edit().strip()
        except KeyboardInterrupt:
            raw = ""
        curses.curs_set(0)
        return raw or None

    def cycle_kind(self, pane):
        i = self.KINDS.index(pane.kind) if pane.kind in self.KINDS else 0
        pane.kind = self.KINDS[(i + 1) % len(self.KINDS)]
        pane.cursor = 0
        pane.reload()

    def hdr(self, kind):
        return {
            "stock": "SKU     QTY   PRICE NAME",
            "journal": "WHEN      TYPE WHAT",
            "parties": "NAME         SALES/KIND",
            "orders": "ID   TY PARTY    LINE",
        }.get(kind, "")

    def detail(self):
        cur = self.pane.current()
        sku = cur.get("sku")
        if not sku:
            return "no selection"
        if self.pane.kind == "stock" or cur.get("kind") == "item":
            it = item_get(sku) or {}
            q = stock_map().get(sku, 0)
            return "%s  %s  qty %d  $%s  min %s  bin %s" % (
                sku, it.get("name") or "", q, money(it.get("price") or 0),
                it.get("min") or 0, it.get("bin") or "-",
            )
        if self.pane.kind == "parties":
            n, tot = party_sales(sku)
            p = load_json(PARTIES).get(sku) or {}
            return "%s  %s  %d so  %s" % (sku, p.get("kind"), n, money(tot))
        return cur.get("line") or sku

    def totals(self):
        st = stock_map()
        items = load_json(ITEMS)
        val = sum(int((items.get(s) or {}).get("cost") or 0) * max(q, 0) for s, q in st.items())
        skus = sum(1 for q in st.values() if q)
        return "%d sku  onhand %s" % (skus, money(val))

    def draw(self):
        scr = self.scr
        h, w = scr.getmaxyx()
        mid = max(16, w // 2)
        list_h = max(1, h - 5)
        scr.erase()
        clock = datetime.now().strftime("%H:%M")
        put(scr, 0, 0, ("sERP  " + self.totals() + "  " + clock).ljust(w), curses.color_pair(4) | curses.A_BOLD)
        for pi, pane in enumerate(self.panes):
            x0 = 0 if pi == 0 else mid + 1
            pw = mid if pi == 0 else max(1, w - mid - 1)
            active = pi == self.active
            tag = pane.kind.upper()
            n = len(pane.rows)
            title = "%s %d%s" % (tag, n, " /" + pane.filter if pane.filter else "")
            bar = curses.color_pair(2) if active else curses.color_pair(4)
            put(scr, 1, x0, title.ljust(pw), bar)
            put(scr, 2, x0, self.hdr(pane.kind).ljust(pw), curses.color_pair(9))
            vis = max(1, list_h - 1)
            if pane.cursor < pane.scroll:
                pane.scroll = pane.cursor
            if pane.cursor >= pane.scroll + vis:
                pane.scroll = pane.cursor - vis + 1
            if not pane.rows:
                put(scr, 3, x0, "(empty)", curses.color_pair(3))
            for i in range(vis):
                idx = pane.scroll + i
                if idx >= len(pane.rows):
                    break
                row = pane.rows[idx]
                attr = curses.A_NORMAL
                if row.get("low"):
                    attr = curses.color_pair(6)
                if pane.kind == "journal" and " so " in (" " + row["line"].lower() + " "):
                    attr = curses.color_pair(7)
                if idx == pane.cursor and active:
                    attr = curses.color_pair(2) | curses.A_BOLD
                put(scr, 3 + i, x0, row["line"].ljust(pw), attr)
        if 0 < mid < w:
            for y in range(1, list_h + 3):
                try:
                    scr.addch(y, mid, curses.ACS_VLINE)
                except curses.error:
                    pass
        put(scr, h - 3, 0, self.detail().ljust(w), curses.color_pair(4))
        put(scr, h - 2, 0, (self.msg or NAME).ljust(w), curses.color_pair(5) if self.err else curses.color_pair(8))
        put(scr, h - 1, 0, "1Help 2Item 3Party 4Edit 5In 6Out 7Sale 8Adj 9Buy 10Quit", curses.A_REVERSE)
        scr.refresh()

    def help_screen(self):
        lines = [
            "sERP  commander keys",
            "Tab        other pane",
            "t          stock / journal / parties / orders",
            "/          filter this pane",
            "F1         this help",
            "F2         new item",
            "F3         new customer/vendor",
            "F4         edit item (name price min bin)",
            "F5         receive stock",
            "F6         ship stock",
            "F7         sale (customer + sku + qty)",
            "F8         adjust qty (+/-)",
            "F9         purchase from vendor",
            "v          on-hand value",
            "l          low stock",
            "F10 / q    quit",
            "",
            "! in stock list = at or below min",
        ]
        h, w = self.scr.getmaxyx()
        top = 0
        while True:
            self.scr.erase()
            put(self.scr, 0, 0, "help".ljust(w), curses.A_REVERSE)
            for i in range(1, h - 1):
                li = top + i - 1
                if li < len(lines):
                    put(self.scr, i, 0, lines[li])
            put(self.scr, h - 1, 0, "q back", curses.A_REVERSE)
            self.scr.refresh()
            k = self.scr.getch()
            if k in (ord("q"), 27, curses.KEY_F10, curses.KEY_F1):
                break

    def add_item(self):
        sku = self.prompt("SKU")
        if not sku:
            return
        name = self.prompt("name", sku) or sku
        price = self.prompt("price", "0") or "0"
        mn = self.prompt("min qty", "0") or "0"
        bin_ = self.prompt("bin", "") or ""
        item_put(sku, name=name, price=parse_money(price), min=int(mn or 0), bin=bin_)
        self.say("item " + sku)

    def edit_item(self):
        sku = self.pane.current().get("sku") or self.prompt("edit SKU")
        if not sku:
            return
        it = item_get(sku) or {"name": sku, "price": 0, "min": 0, "bin": ""}
        name = self.prompt("name", str(it.get("name") or sku)) or sku
        price = self.prompt("price", money(it.get("price") or 0)) or "0"
        mn = self.prompt("min", str(it.get("min") or 0)) or "0"
        bin_ = self.prompt("bin", str(it.get("bin") or "")) or ""
        item_put(sku, name=name, price=parse_money(price), min=int(mn or 0), bin=bin_)
        self.say("edited " + sku)

    def add_party(self):
        name = self.prompt("party")
        if not name:
            return
        kind = self.prompt("customer or vendor", "customer") or "customer"
        party_put(name, kind if kind in ("customer", "vendor") else "customer")
        self.say("party " + name)

    def do_recv(self):
        sku = self.prompt("recv SKU", self.pane.current().get("sku") or "")
        if not sku:
            return
        qty = self.prompt("qty")
        if not qty:
            return
        cmd_recv(sku, qty)
        self.say("recv %s x%s" % (sku, qty))

    def do_ship(self):
        sku = self.prompt("ship SKU", self.pane.current().get("sku") or "")
        if not sku:
            return
        qty = self.prompt("qty")
        if not qty:
            return
        rc = cmd_ship(sku, qty)
        self.say("shipped" if rc == 0 else "not enough", err=rc != 0)

    def do_so(self):
        party = self.prompt("customer")
        sku = self.prompt("SKU", self.pane.current().get("sku") or "")
        qty = self.prompt("qty")
        if party and sku and qty:
            rc = cmd_so(party, sku, qty)
            self.say("sale ok" if rc == 0 else "sale fail", err=rc != 0)

    def do_adj(self):
        sku = self.prompt("adj SKU", self.pane.current().get("sku") or "")
        if not sku:
            return
        qty = self.prompt("delta (+/-)")
        if not qty:
            return
        cmd_adj(sku, qty)
        self.say("adj %s %+s" % (sku, qty))

    def do_po(self):
        vendor = self.prompt("vendor")
        sku = self.prompt("SKU", self.pane.current().get("sku") or "")
        qty = self.prompt("qty")
        cost = self.prompt("unit cost", "")
        if vendor and sku and qty:
            cmd_po(vendor, sku, qty, cost or None)
            self.say("PO " + vendor)

    def set_filter(self):
        raw = self.prompt("filter (empty clears)", self.pane.filter)
        self.pane.filter = raw or ""
        self.pane.cursor = 0
        self.pane.reload()
        self.say("filter " + (self.pane.filter or "off"))

    def run(self):
        curses.curs_set(0)
        self.colors()
        self.reload()
        while True:
            self.draw()
            k = self.scr.getch()
            self.err = False
            if k in (ord("q"), curses.KEY_F10, 27):
                break
            elif k == 9:
                self.active = 1 - self.active
            elif k == curses.KEY_UP:
                self.pane.move(-1)
            elif k == curses.KEY_DOWN:
                self.pane.move(1)
            elif k == curses.KEY_PPAGE:
                self.pane.move(-8)
            elif k == curses.KEY_NPAGE:
                self.pane.move(8)
            elif k in (ord("t"), ord("T")):
                self.cycle_kind(self.pane)
            elif k == ord("/"):
                self.set_filter()
            elif k in (ord("v"), ord("V")):
                st = stock_map()
                items = load_json(ITEMS)
                total = sum(int((items.get(s) or {}).get("cost") or 0) * max(q, 0) for s, q in st.items())
                self.say("on-hand cost " + money(total))
            elif k in (ord("l"), ord("L")):
                self.pane.kind = "stock"
                lows = []
                st = stock_map()
                for sku, it in load_json(ITEMS).items():
                    if st.get(sku, 0) <= int(it.get("min") or 0):
                        lows.append(sku)
                self.say("low: " + (", ".join(lows) if lows else "none"))
                self.pane.reload()
            elif k in (curses.KEY_F1, ord("?")):
                self.help_screen()
            elif k == curses.KEY_F2:
                self.add_item()
                self.reload()
            elif k == curses.KEY_F3:
                self.add_party()
                self.reload()
            elif k == curses.KEY_F4:
                self.edit_item()
                self.reload()
            elif k == curses.KEY_F5:
                self.do_recv()
                self.reload()
            elif k == curses.KEY_F6:
                self.do_ship()
                self.reload()
            elif k == curses.KEY_F7:
                self.do_so()
                self.reload()
            elif k == curses.KEY_F8:
                self.do_adj()
                self.reload()
            elif k == curses.KEY_F9:
                self.do_po()
                self.reload()


def ui():
    if not sys.stdout.isatty():
        print("sERP UI needs a tty")
        return 2
    ensure()
    curses.wrapper(lambda s: App(s).run())
    return 0



def main(argv=None):
    ensure()
    p = argparse.ArgumentParser(prog="serp")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("ui")
    sub.add_parser("stock")
    sub.add_parser("low")
    sub.add_parser("value")
    sub.add_parser("log")
    sub.add_parser("sales")
    a = sub.add_parser("item")
    a.add_argument("op", choices=("add", "ls"))
    a.add_argument("sku", nargs="?")
    a.add_argument("name", nargs="?")
    a.add_argument("price", nargs="?")
    b = sub.add_parser("party")
    b.add_argument("op", choices=("add", "ls"))
    b.add_argument("name", nargs="?")
    b.add_argument("kind", nargs="?", default="customer")
    c = sub.add_parser("recv")
    c.add_argument("sku")
    c.add_argument("qty")
    c.add_argument("cost", nargs="?")
    d = sub.add_parser("ship")
    d.add_argument("sku")
    d.add_argument("qty")
    e = sub.add_parser("so")
    e.add_argument("party")
    e.add_argument("sku")
    e.add_argument("qty")
    f = sub.add_parser("adj")
    f.add_argument("sku")
    f.add_argument("qty")
    g = sub.add_parser("po")
    g.add_argument("vendor")
    g.add_argument("sku")
    g.add_argument("qty")
    g.add_argument("cost", nargs="?")
    args = p.parse_args(argv)
    if args.cmd in (None, "ui"):
        return ui()
    if args.cmd == "stock":
        cmd_stock()
    elif args.cmd == "low":
        cmd_low()
    elif args.cmd == "value":
        cmd_value()
    elif args.cmd == "log":
        cmd_log()
    elif args.cmd == "sales":
        cmd_sales()
    elif args.cmd == "item":
        if args.op == "ls" or not args.sku:
            cmd_item_ls()
        else:
            cmd_item_add(args.sku, args.name or args.sku, args.price or "0")
    elif args.cmd == "party":
        if args.op == "ls" or not args.name:
            cmd_party_ls()
        else:
            cmd_party_add(args.name, args.kind)
    elif args.cmd == "recv":
        cmd_recv(args.sku, args.qty, args.cost)
    elif args.cmd == "ship":
        return cmd_ship(args.sku, args.qty) or 0
    elif args.cmd == "so":
        return cmd_so(args.party, args.sku, args.qty) or 0
    elif args.cmd == "adj":
        cmd_adj(args.sku, args.qty)
    elif args.cmd == "po":
        cmd_po(args.vendor, args.sku, args.qty, args.cost)
    return 0


if __name__ == "__main__":
    sys.exit(main())
