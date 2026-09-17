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


# ---------------- curses ----------------

PANES = ("stock", "parties", "journal", "orders")


def clip(s, n):
    s = " ".join(str(s).split())
    if n <= 1:
        return ""
    return s if len(s) <= n else s[: n - 1] + "~"


def put(stdscr, y, x, text, attr=0):
    try:
        h, w = stdscr.getmaxyx()
        if y < 0 or x < 0 or y >= h or x >= w:
            return
        room = w - x - (1 if y == h - 1 else 0)
        if room <= 0:
            return
        stdscr.addnstr(y, x, clip(text, room), room, attr)
    except curses.error:
        pass


class UI:
    def __init__(self):
        ensure()
        self.pane = 0
        self.cur = 0
        self.msg = ROOT
        self.rows = []

    def reload(self):
        name = PANES[self.pane]
        if name == "stock":
            st = stock_map()
            items = load_json(ITEMS)
            skus = sorted(set(list(items) + list(st)))
            self.rows = []
            for sku in skus:
                it = items.get(sku) or {"name": sku, "price": 0, "min": 0}
                self.rows.append({
                    "key": sku,
                    "line": "%-8s %5d %7s  %s" % (
                        sku[:8], st.get(sku, 0), money(it.get("price") or 0), it.get("name", "")[:20],
                    ),
                    "detail": "sku %s\n%s\nqty %d\nprice %s\ncost %s\nmin %s" % (
                        sku, it.get("name"), st.get(sku, 0),
                        money(it.get("price") or 0), money(it.get("cost") or 0), it.get("min") or 0,
                    ),
                })
        elif name == "parties":
            parties = load_json(PARTIES)
            self.rows = []
            for n, p in sorted(parties.items()):
                self.rows.append({
                    "key": n,
                    "line": "%-16s %s" % (n[:16], p.get("kind")),
                    "detail": "%s\n%s\n%s" % (n, p.get("kind"), p.get("since", "")),
                })
        elif name == "journal":
            self.rows = []
            for r in reversed(read_j()[-80:]):
                extra = r.get("sku") or r.get("party") or ""
                self.rows.append({
                    "key": r.get("id"),
                    "line": "%s %-4s %s %s" % (str(r.get("ts", ""))[5:16], r.get("type"), extra, r.get("qty", "")),
                    "detail": json.dumps(r, indent=2),
                })
        else:
            self.rows = []
            for r in reversed([x for x in read_j() if x.get("type") == "so"][-40:]):
                self.rows.append({
                    "key": r.get("id"),
                    "line": "%s %-10s %s x%s %s" % (
                        str(r.get("id", ""))[-6:], r.get("party", "")[:10],
                        r.get("sku"), r.get("qty"), money(r.get("total") or 0),
                    ),
                    "detail": json.dumps(r, indent=2),
                })
        if self.cur >= len(self.rows):
            self.cur = max(0, len(self.rows) - 1)

    def prompt(self, stdscr, title):
        curses.echo()
        curses.curs_set(1)
        h, w = stdscr.getmaxyx()
        put(stdscr, h - 1, 0, " " * max(0, w - 1))
        put(stdscr, h - 1, 0, title + " ")
        stdscr.refresh()
        try:
            raw = stdscr.getstr(h - 1, min(w - 2, len(title) + 1), max(8, w - 12))
            text = raw.decode("utf-8", "replace").strip()
        except Exception:
            text = ""
        curses.noecho()
        curses.curs_set(0)
        return text

    def draw(self, stdscr):
        h, w = stdscr.getmaxyx()
        mid = max(18, w * 3 // 5)
        stdscr.erase()
        tabs = " ".join(
            ("[%s]" % p.upper() if i == self.pane else p) for i, p in enumerate(PANES)
        )
        put(stdscr, 0, 0, (NAME + "  " + tabs).ljust(w), curses.A_REVERSE)
        left_h = h - 2
        top = 0
        if self.cur >= top + left_h:
            top = self.cur - left_h + 1
        for i in range(left_h):
            idx = top + i
            if idx >= len(self.rows):
                break
            attr = curses.A_REVERSE if idx == self.cur else curses.A_NORMAL
            put(stdscr, 1 + i, 0, self.rows[idx]["line"].ljust(mid - 1), attr)
        det = ""
        if self.rows:
            det = self.rows[self.cur]["detail"]
        dy = 1
        for line in det.splitlines():
            if dy >= h - 1:
                break
            put(stdscr, dy, mid, line)
            dy += 1
        helpbar = "tab pane  a add  r recv  s ship  o sale  q"
        put(stdscr, h - 1, 0, (self.msg + " | " + helpbar).ljust(w), curses.A_REVERSE)
        stdscr.refresh()

    def add_item(self, stdscr):
        sku = self.prompt(stdscr, "sku")
        if not sku:
            return
        name = self.prompt(stdscr, "name") or sku
        price = self.prompt(stdscr, "price") or "0"
        item_put(sku, name=name, price=parse_money(price))
        self.msg = "item " + sku

    def add_party(self, stdscr):
        name = self.prompt(stdscr, "party")
        if not name:
            return
        kind = self.prompt(stdscr, "customer/vendor") or "customer"
        party_put(name, kind if kind in ("customer", "vendor") else "customer")
        self.msg = "party " + name

    def do_recv(self, stdscr):
        sku = self.prompt(stdscr, "recv sku")
        if not sku:
            return
        qty = self.prompt(stdscr, "qty")
        if not qty:
            return
        cmd_recv(sku, qty)
        self.msg = "recv %s x%s" % (sku, qty)

    def do_ship(self, stdscr):
        sku = self.prompt(stdscr, "ship sku")
        if not sku:
            return
        qty = self.prompt(stdscr, "qty")
        if not qty:
            return
        rc = cmd_ship(sku, qty)
        self.msg = "shipped" if rc == 0 else "not enough"

    def do_so(self, stdscr):
        party = self.prompt(stdscr, "customer")
        sku = self.prompt(stdscr, "sku")
        qty = self.prompt(stdscr, "qty")
        if party and sku and qty:
            rc = cmd_so(party, sku, qty)
            self.msg = "sale ok" if rc == 0 else "sale fail"

    def run(self, stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        self.reload()
        while True:
            self.draw(stdscr)
            k = stdscr.getch()
            if k in (ord("q"), 27):
                break
            elif k == 9:
                self.pane = (self.pane + 1) % len(PANES)
                self.cur = 0
                self.reload()
            elif k == curses.KEY_BTAB:
                self.pane = (self.pane - 1) % len(PANES)
                self.cur = 0
                self.reload()
            elif k == curses.KEY_DOWN:
                self.cur = min(len(self.rows) - 1, self.cur + 1) if self.rows else 0
            elif k == curses.KEY_UP:
                self.cur = max(0, self.cur - 1)
            elif k == ord("a"):
                if PANES[self.pane] == "parties":
                    self.add_party(stdscr)
                else:
                    self.add_item(stdscr)
                self.reload()
            elif k == ord("r"):
                self.do_recv(stdscr)
                self.reload()
            elif k == ord("s"):
                self.do_ship(stdscr)
                self.reload()
            elif k == ord("o"):
                self.do_so(stdscr)
                self.reload()
            elif k == ord("l"):
                self.pane = 2
                self.cur = 0
                self.reload()


def ui():
    if not sys.stdout.isatty():
        print("serp UI needs a tty")
        return 2
    ensure()
    curses.wrapper(lambda s: UI().run(s))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
