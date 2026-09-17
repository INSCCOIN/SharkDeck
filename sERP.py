#!/usr/bin/env python3
"""sERP — handheld ERP for SharkDeck. Dual-pane sCMD UI + CLI."""

import argparse
import csv
import curses
import curses.textpad
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta

NAME = "sERP"
ROOT = os.path.expanduser("~/.serp")
ITEMS = os.path.join(ROOT, "items.json")
PARTIES = os.path.join(ROOT, "parties.json")
JOURNAL = os.path.join(ROOT, "journal.jsonl")
BAK = os.path.join(ROOT, "bak")
CSV_OUT = os.path.join(ROOT, "export.csv")


def now():
    return datetime.now().isoformat(timespec="seconds")


def ensure():
    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(BAK, exist_ok=True)
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


def backup():
    ensure()
    dest = os.path.join(BAK, datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for src in (ITEMS, PARTIES, JOURNAL):
        if os.path.exists(src):
            shutil.copy2(src, dest)
    for name in sorted(os.listdir(BAK))[:-12]:
        shutil.rmtree(os.path.join(BAK, name), ignore_errors=True)


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


def voided_ids(rows=None):
    rows = rows if rows is not None else read_j()
    dead = set()
    for r in rows:
        if r.get("type") == "undo":
            for i in r.get("ids") or []:
                dead.add(i)
            dead.add(r.get("id"))
    return dead


def live_j():
    rows = read_j()
    dead = voided_ids(rows)
    return [r for r in rows if r.get("id") not in dead]


def new_id():
    return str(int(time.time() * 1000))


def append_j(rec):
    backup()
    rec = dict(rec)
    rec["ts"] = rec.get("ts") or now()
    rec["id"] = rec.get("id") or new_id()
    with open(JOURNAL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return rec


def money(cents):
    cents = int(cents or 0)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return "%s%d.%02d" % (sign, cents // 100, cents % 100)


def parse_money(s):
    s = str(s or "0").strip().replace("$", "")
    if not s:
        return 0
    if "." in s:
        a, b = s.split(".", 1)
        b = (b + "00")[:2]
        return int(a or "0") * 100 + int(b or "0")
    return int(s) * 100


def item_get(sku):
    return load_json(ITEMS).get(sku)


def item_put(sku, **kw):
    items = load_json(ITEMS)
    row = items.get(sku) or {
        "sku": sku, "name": sku, "price": 0, "cost": 0, "min": 0, "bin": "", "qty": 0,
    }
    row.update(kw)
    row["sku"] = sku
    items[sku] = row
    save_json(ITEMS, items)
    return row


def party_put(name, kind="customer"):
    parties = load_json(PARTIES)
    key = name.strip()
    row = parties.get(key) or {"name": key, "kind": kind, "since": now()}
    row["kind"] = kind
    parties[key] = row
    save_json(PARTIES, parties)
    return row


def stock_from_journal():
    qty, last_cost = {}, {}
    for r in live_j():
        t = r.get("type")
        if t == "so":
            for ln in r.get("lines") or []:
                sku = ln.get("sku")
                qty[sku] = qty.get(sku, 0) - int(ln.get("qty") or 0)
        elif t == "po":
            for ln in r.get("lines") or []:
                sku = ln.get("sku")
                qty[sku] = qty.get(sku, 0) + int(ln.get("qty") or 0)
                if ln.get("cost"):
                    last_cost[sku] = int(ln["cost"])
        elif t in ("recv", "ship", "adj"):
            sku = r.get("sku")
            q = int(r.get("qty") or 0)
            if t == "ship":
                q = -q
            qty[sku] = qty.get(sku, 0) + q
            if t == "recv" and r.get("cost"):
                last_cost[sku] = int(r["cost"])
    return qty, last_cost


def stock_map():
    return stock_from_journal()[0]


def sync_qty_cache():
    qty, costs = stock_from_journal()
    items = load_json(ITEMS)
    for sku, q in qty.items():
        row = items.get(sku) or {
            "sku": sku, "name": sku, "price": 0, "cost": 0, "min": 0, "bin": "", "qty": 0,
        }
        row["qty"] = q
        if sku in costs:
            row["cost"] = costs[sku]
        items[sku] = row
    save_json(ITEMS, items)
    return qty


def sales_since(since_dt):
    n = tot = 0
    for r in live_j():
        if r.get("type") != "so":
            continue
        try:
            ts = datetime.fromisoformat(r.get("ts", ""))
        except ValueError:
            continue
        if ts >= since_dt:
            n += 1
            tot += int(r.get("total") or 0)
    return n, tot


def party_sales(name):
    n = tot = 0
    for r in live_j():
        if r.get("type") == "so" and r.get("party") == name:
            n += 1
            tot += int(r.get("total") or 0)
    return n, tot


def cmd_item_add(sku, name, price="0"):
    row = item_put(sku, name=name, price=parse_money(price))
    print("%s  %s  %s" % (row["sku"], row["name"], money(row["price"])))


def cmd_item_ls():
    qty, costs = stock_from_journal()
    items = load_json(ITEMS)
    print("%-10s %5s %8s %8s  %s" % ("SKU", "QTY", "PRICE", "COST", "NAME"))
    for sku in sorted(set(list(items) + list(qty))):
        it = items.get(sku) or {"name": sku, "price": 0}
        print("%-10s %5d %8s %8s  %s" % (
            sku, qty.get(sku, 0), money(it.get("price") or 0),
            money(costs.get(sku, it.get("cost") or 0)), it.get("name") or "",
        ))


def cmd_recv(sku, qty, cost=None):
    if not item_get(sku):
        item_put(sku, name=sku)
    rec = {"type": "recv", "sku": sku, "qty": int(qty)}
    if cost is not None:
        rec["cost"] = parse_money(cost)
        item_put(sku, cost=rec["cost"])
    append_j(rec)
    sync_qty_cache()
    print("recv %s x%s  on-hand %d" % (sku, qty, stock_map().get(sku, 0)))


def cmd_ship(sku, qty):
    have = stock_map().get(sku, 0)
    q = int(qty)
    if q > have:
        print("only %d on hand" % have)
        return 1
    append_j({"type": "ship", "sku": sku, "qty": q})
    sync_qty_cache()
    print("ship %s x%s  on-hand %d" % (sku, q, stock_map().get(sku, 0)))
    return 0


def cmd_adj(sku, qty):
    if not item_get(sku):
        item_put(sku, name=sku)
    append_j({"type": "adj", "sku": sku, "qty": int(qty)})
    sync_qty_cache()
    print("adj %s %+d  on-hand %d" % (sku, int(qty), stock_map().get(sku, 0)))


def post_doc(kind, party, lines):
    if not lines:
        print("empty document")
        return 1
    qty_now = stock_map()
    if kind == "so":
        for ln in lines:
            if int(ln["qty"]) > qty_now.get(ln["sku"], 0):
                print("need %s x%s have %d" % (ln["sku"], ln["qty"], qty_now.get(ln["sku"], 0)))
                return 1
        total = sum(int(ln["qty"]) * int(ln.get("price") or 0) for ln in lines)
        rec = append_j({"type": "so", "party": party, "lines": lines, "total": total})
    else:
        total = sum(int(ln["qty"]) * int(ln.get("cost") or 0) for ln in lines)
        rec = append_j({"type": "po", "party": party, "lines": lines, "total": total})
        for ln in lines:
            if ln.get("cost"):
                item_put(ln["sku"], cost=int(ln["cost"]))
    sync_qty_cache()
    print("%s %s  %d lines  %s" % (kind.upper(), rec["id"][-6:], len(lines), money(total)))
    return 0


def cmd_so(party, sku, qty):
    if party not in load_json(PARTIES):
        party_put(party, "customer")
    it = item_get(sku)
    if not it:
        print("unknown sku", sku)
        return 1
    return post_doc("so", party, [{"sku": sku, "qty": int(qty), "price": int(it.get("price") or 0)}])


def cmd_po(vendor, sku, qty, cost=None):
    if vendor not in load_json(PARTIES):
        party_put(vendor, "vendor")
    if not item_get(sku):
        item_put(sku, name=sku)
    c = parse_money(cost) if cost is not None else int((item_get(sku) or {}).get("cost") or 0)
    return post_doc("po", vendor, [{"sku": sku, "qty": int(qty), "cost": c}])


def cmd_undo():
    rows = read_j()
    dead = voided_ids(rows)
    last = None
    for r in reversed(rows):
        if r.get("id") not in dead and r.get("type") != "undo":
            last = r
            break
    if not last:
        print("nothing to undo")
        return 1
    append_j({"type": "undo", "ids": [last["id"]], "note": last.get("type")})
    sync_qty_cache()
    print("undid", last.get("type"), last.get("id")[-6:])
    return 0


def cmd_check():
    qty, _costs = stock_from_journal()
    items = load_json(ITEMS)
    bad = 0
    for sku in sorted(set(list(items) + list(qty))):
        cached = int((items.get(sku) or {}).get("qty") or 0)
        real = qty.get(sku, 0)
        mark = "OK" if cached == real else "DRIFT"
        if cached != real:
            bad += 1
        print("%-10s cache %5d  jrnl %5d  %s" % (sku, cached, real, mark))
    sync_qty_cache()
    print("rebuilt cache. drift was", bad)
    return 0 if bad == 0 else 1


def cmd_buy():
    qty, _ = stock_from_journal()
    items = load_json(ITEMS)
    hit = False
    print("%-10s %5s %5s %5s  %s" % ("SKU", "HAVE", "MIN", "BUY", "NAME"))
    for sku, it in sorted(items.items()):
        have = qty.get(sku, 0)
        mn = int(it.get("min") or 0)
        if have <= mn:
            need = max(mn * 2 - have, mn - have, 1) if mn else 1
            print("%-10s %5d %5d %5d  %s" % (sku, have, mn, need, it.get("name")))
            hit = True
    if not hit:
        print("nothing to buy")


def cmd_value():
    qty, costs = stock_from_journal()
    items = load_json(ITEMS)
    total = 0
    for sku, q in qty.items():
        c = costs.get(sku, int((items.get(sku) or {}).get("cost") or 0))
        total += c * max(q, 0)
    print("on-hand cost", money(total))


def cmd_sales():
    day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week0 = day0 - timedelta(days=day0.weekday())
    dn, dt = sales_since(day0)
    wn, wt = sales_since(week0)
    an, at = sales_since(datetime(1970, 1, 1))
    print("today %d %s" % (dn, money(dt)))
    print("week  %d %s" % (wn, money(wt)))
    print("all   %d %s" % (an, money(at)))


def cmd_log(n=20):
    dead = voided_ids()
    rows = [r for r in read_j() if r.get("id") not in dead][-int(n):]
    for r in rows:
        extra = r.get("sku") or r.get("party") or ""
        nlines = len(r.get("lines") or [])
        print("%s  %-4s  %s  %s%s" % (
            str(r.get("ts", ""))[5:16], r.get("type"), extra,
            r.get("qty", ""), (" %dln" % nlines) if nlines else "",
        ))


def cmd_csv(path=None):
    path = path or CSV_OUT
    qty, costs = stock_from_journal()
    items = load_json(ITEMS)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "name", "qty", "price", "cost", "min", "bin"])
        for sku in sorted(set(list(items) + list(qty))):
            it = items.get(sku) or {}
            w.writerow([
                sku, it.get("name") or sku, qty.get(sku, 0),
                money(it.get("price") or 0), money(costs.get(sku, it.get("cost") or 0)),
                it.get("min") or 0, it.get("bin") or "",
            ])
    print("wrote", path)


def cmd_party_add(name, kind="customer"):
    print("%s (%s)" % (party_put(name, kind)["name"], kind))


def cmd_party_ls():
    for n, p in sorted(load_json(PARTIES).items()):
        ns, tot = party_sales(n)
        print("%-16s %-8s %s" % (n, p.get("kind"), money(tot) if ns else ""))


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
        self.filter = ""
        self.rows = []

    def reload(self, cart=None):
        self.rows = []
        fl = self.filter.lower()
        if self.kind == "cart":
            for ln in cart or []:
                ext = int(ln["qty"]) * int(ln.get("price") or ln.get("cost") or 0)
                self.rows.append({
                    "sku": ln["sku"],
                    "line": "%-8s x%-3s %s" % (ln["sku"][:8], ln["qty"], money(ext)),
                    "kind": "cart",
                })
        elif self.kind == "stock":
            qty, costs = stock_from_journal()
            items = load_json(ITEMS)
            for sku in sorted(set(list(items) + list(qty))):
                it = items.get(sku) or {"name": sku, "price": 0, "min": 0, "cost": 0}
                q = qty.get(sku, 0)
                low = q <= int(it.get("min") or 0)
                cost = costs.get(sku, int(it.get("cost") or 0))
                line = "%s%-6s %4d %6s %s" % (
                    "!" if low else " ", sku[:6], q, money(cost), (it.get("name") or "")[:8],
                )
                blob = (sku + " " + str(it.get("name")) + " " + str(it.get("bin"))).lower()
                if fl and fl not in blob:
                    continue
                self.rows.append({"sku": sku, "line": line, "kind": "item", "low": low})
        elif self.kind == "parties":
            for n, p in sorted(load_json(PARTIES).items()):
                if fl and fl not in n.lower():
                    continue
                _ns, tot = party_sales(n)
                self.rows.append({
                    "sku": n,
                    "line": "%-10s %s" % (n[:10], money(tot) if p.get("kind") == "customer" else p.get("kind")),
                    "kind": "party",
                })
        elif self.kind == "journal":
            for r in reversed(live_j()[-100:]):
                extra = r.get("sku") or r.get("party") or ""
                nln = len(r.get("lines") or [])
                line = "%s %-3s %s%s" % (
                    str(r.get("ts", ""))[5:16], r.get("type"), extra[:8],
                    ("*%d" % nln) if nln else "",
                )
                if fl and fl not in line.lower():
                    continue
                self.rows.append({"sku": extra, "line": line, "kind": r.get("type")})
        else:
            for r in reversed([x for x in live_j() if x.get("type") in ("so", "po")][-50:]):
                line = "%s %s %-8s %s" % (
                    str(r.get("id", ""))[-4:], r.get("type"), str(r.get("party", ""))[:8],
                    money(r.get("total") or 0),
                )
                if fl and fl not in line.lower():
                    continue
                self.rows.append({"sku": r.get("party"), "line": line, "kind": r.get("type")})
        if self.cursor >= len(self.rows):
            self.cursor = max(0, len(self.rows) - 1)

    def move(self, d):
        if self.rows:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + d))

    def current(self):
        return self.rows[self.cursor] if self.rows else {}


class App:
    def __init__(self, stdscr):
        self.scr = stdscr
        self.left = Pane("stock")
        self.right = Pane("journal")
        self.active = 0
        self.msg = "F7 sale cart  F9 buy cart  Enter adds SKU"
        self.err = False
        self.mode = "ok"
        self.cart = []
        self.party = ""

    @property
    def pane(self):
        return self.left if self.active == 0 else self.right

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

    def reload(self):
        self.left.reload()
        if self.mode in ("sale", "po"):
            self.right.kind = "cart"
            self.right.reload(self.cart)
        else:
            if self.right.kind == "cart":
                self.right.kind = "journal"
            self.right.reload()

    def say(self, t, err=False):
        self.msg, self.err = t, err

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
            sub.addstr(0, 0, str(default)[: pw - 4])
        except curses.error:
            pass
        curses.curs_set(1)
        try:
            raw = curses.textpad.Textbox(sub).edit().strip()
        except KeyboardInterrupt:
            raw = ""
        curses.curs_set(0)
        return raw or None

    def confirm(self, title):
        a = self.prompt(title + "  y/n", "n")
        return bool(a) and a.lower().startswith("y")

    def header(self):
        day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week0 = day0 - timedelta(days=day0.weekday())
        _dn, dt = sales_since(day0)
        _wn, wt = sales_since(week0)
        qty, costs = stock_from_journal()
        items = load_json(ITEMS)
        val = sum(costs.get(s, int((items.get(s) or {}).get("cost") or 0)) * max(q, 0) for s, q in qty.items())
        return "sERP  td %s  wk %s  stk %s  %s" % (
            money(dt), money(wt), money(val), datetime.now().strftime("%H:%M"),
        )

    def detail(self):
        if self.mode == "sale":
            tot = sum(int(l["qty"]) * int(l.get("price") or 0) for l in self.cart)
            return "SALE %s  %d ln  %s  Enter add  F7 post  Esc cancel" % (self.party, len(self.cart), money(tot))
        if self.mode == "po":
            tot = sum(int(l["qty"]) * int(l.get("cost") or 0) for l in self.cart)
            return "BUY %s  %d ln  %s  Enter add  F9 post  Esc cancel" % (self.party, len(self.cart), money(tot))
        cur = self.pane.current()
        sku = cur.get("sku")
        if not sku:
            return "F7 sale   F9 buy   U undo   / filter"
        it = item_get(sku) or {}
        q = stock_map().get(sku, 0)
        return "%s  %s  qty %d  sell %s  last %s  min %s  %s" % (
            sku, it.get("name") or "", q, money(it.get("price") or 0),
            money(it.get("cost") or 0), it.get("min") or 0, it.get("bin") or "",
        )

    def draw(self):
        scr = self.scr
        h, w = scr.getmaxyx()
        mid = max(16, w // 2)
        list_h = max(1, h - 5)
        scr.erase()
        put(scr, 0, 0, self.header().ljust(w), curses.color_pair(4) | curses.A_BOLD)
        for pi, pane in enumerate((self.left, self.right)):
            x0 = 0 if pi == 0 else mid + 1
            pw = mid if pi == 0 else max(1, w - mid - 1)
            title = "%s %d%s" % (pane.kind.upper(), len(pane.rows),
                                 " /" + pane.filter if pane.filter else "")
            bar = curses.color_pair(2) if pi == self.active else curses.color_pair(4)
            put(scr, 1, x0, title.ljust(pw), bar)
            vis = max(1, list_h - 1)
            if pane.cursor < pane.scroll:
                pane.scroll = pane.cursor
            if pane.cursor >= pane.scroll + vis:
                pane.scroll = pane.cursor - vis + 1
            if not pane.rows:
                put(scr, 2, x0, "(empty)", curses.color_pair(3))
            for i in range(vis):
                idx = pane.scroll + i
                if idx >= len(pane.rows):
                    break
                row = pane.rows[idx]
                attr = curses.A_NORMAL
                if row.get("low"):
                    attr = curses.color_pair(6)
                if row.get("kind") == "so":
                    attr = curses.color_pair(7)
                if idx == pane.cursor and pi == self.active:
                    attr = curses.color_pair(2) | curses.A_BOLD
                put(scr, 2 + i, x0, row["line"].ljust(pw), attr)
        if 0 < mid < w:
            for y in range(1, list_h + 2):
                try:
                    scr.addch(y, mid, curses.ACS_VLINE)
                except curses.error:
                    pass
        put(scr, h - 3, 0, self.detail().ljust(w), curses.color_pair(4))
        put(scr, h - 2, 0, (self.msg or NAME).ljust(w), curses.color_pair(5) if self.err else curses.color_pair(8))
        put(scr, h - 1, 0, "1? 2Itm 3Pty 4Ed 5Scan 6Ship 7Sale 8Adj 9Buy Uundo 10", curses.A_REVERSE)
        scr.refresh()

    def help_screen(self):
        lines = [
            "Tab other pane   Enter add SKU to cart",
            "F5 scan/recv (qty defaults 1)",
            "F6 ship   F7 sale cart / post",
            "F9 buy cart / post   Esc cancel cart",
            "F2 item  F3 party  F4 edit  F8 adj",
            "U undo last document (backs up first)",
            "/ filter  t cycle right  v value  e csv  c check",
        ]
        h, w = self.scr.getmaxyx()
        while True:
            self.scr.erase()
            put(self.scr, 0, 0, "help".ljust(w), curses.A_REVERSE)
            for i, line in enumerate(lines):
                put(self.scr, i + 1, 0, line)
            put(self.scr, h - 1, 0, "q back", curses.A_REVERSE)
            self.scr.refresh()
            if self.scr.getch() in (ord("q"), 27, curses.KEY_F1, curses.KEY_F10):
                break

    def add_item(self):
        sku = self.prompt("SKU")
        if not sku:
            return
        item_put(sku, name=self.prompt("name", sku) or sku,
                 price=parse_money(self.prompt("price", "0") or "0"),
                 min=int(self.prompt("min", "0") or "0"),
                 bin=self.prompt("bin", "") or "")
        self.say("item " + sku)

    def edit_item(self):
        sku = self.pane.current().get("sku") or self.prompt("SKU")
        if not sku:
            return
        it = item_get(sku) or {"name": sku, "price": 0, "min": 0, "bin": ""}
        item_put(sku, name=self.prompt("name", it.get("name") or sku) or sku,
                 price=parse_money(self.prompt("price", money(it.get("price") or 0)) or "0"),
                 min=int(self.prompt("min", str(it.get("min") or 0)) or "0"),
                 bin=self.prompt("bin", it.get("bin") or "") or "")
        self.say("edited " + sku)

    def add_party(self):
        name = self.prompt("party")
        if not name:
            return
        kind = self.prompt("customer or vendor", "customer") or "customer"
        party_put(name, kind if kind in ("customer", "vendor") else "customer")
        self.say("party " + name)

    def scan_recv(self):
        sku = self.prompt("scan SKU")
        if not sku:
            return
        qty = self.prompt("qty", "1") or "1"
        cost = self.prompt("cost empty=skip", "")
        cmd_recv(sku, qty, cost or None)
        self.say("recv %s x%s" % (sku, qty))

    def do_ship(self):
        sku = self.prompt("ship SKU", self.pane.current().get("sku") or "")
        if not sku:
            return
        qty = self.prompt("qty", "1") or "1"
        if not self.confirm("ship %s x%s" % (sku, qty)):
            return
        rc = cmd_ship(sku, qty)
        self.say("shipped" if rc == 0 else "not enough", err=rc != 0)

    def do_adj(self):
        sku = self.prompt("adj SKU", self.pane.current().get("sku") or "")
        if not sku:
            return
        qty = self.prompt("delta +/-")
        if not qty or not self.confirm("adjust %s by %s" % (sku, qty)):
            return
        cmd_adj(sku, qty)
        self.say("adj %s %+s" % (sku, qty))

    def start_sale(self):
        if self.mode == "sale":
            self.post_cart()
            return
        party = self.prompt("customer")
        if not party:
            return
        if party not in load_json(PARTIES):
            party_put(party, "customer")
        self.mode, self.party, self.cart, self.active = "sale", party, [], 0
        self.say("sale %s — Enter adds SKU" % party)

    def start_po(self):
        if self.mode == "po":
            self.post_cart()
            return
        vendor = self.prompt("vendor")
        if not vendor:
            return
        if vendor not in load_json(PARTIES):
            party_put(vendor, "vendor")
        self.mode, self.party, self.cart, self.active = "po", vendor, [], 0
        self.say("buy %s — Enter adds SKU" % vendor)

    def add_to_cart(self):
        if self.mode not in ("sale", "po"):
            return
        sku = self.left.current().get("sku") or self.prompt("SKU")
        if not sku:
            return
        if not item_get(sku):
            item_put(sku, name=sku)
        qty = self.prompt("qty", "1") or "1"
        try:
            q = int(qty)
        except ValueError:
            self.say("bad qty", True)
            return
        it = item_get(sku) or {}
        if self.mode == "sale":
            self.cart.append({"sku": sku, "qty": q, "price": int(it.get("price") or 0)})
        else:
            c = self.prompt("cost", money(it.get("cost") or 0))
            self.cart.append({"sku": sku, "qty": q, "cost": parse_money(c or "0")})
        self.say("cart %d" % len(self.cart))

    def post_cart(self):
        if not self.cart:
            self.say("empty cart", True)
            return
        if not self.confirm("post %d lines to %s" % (len(self.cart), self.party)):
            return
        rc = post_doc("so" if self.mode == "sale" else "po", self.party, self.cart)
        self.say("posted" if rc == 0 else "post fail", err=rc != 0)
        self.mode, self.cart, self.party = "ok", [], ""

    def cancel_cart(self):
        self.mode, self.cart, self.party = "ok", [], ""
        self.say("cart cleared")

    def do_undo(self):
        if not self.confirm("undo last document"):
            return
        rc = cmd_undo()
        self.say("undone" if rc == 0 else "nothing", err=rc != 0)

    def run(self):
        curses.curs_set(0)
        self.colors()
        while True:
            self.reload()
            self.draw()
            k = self.scr.getch()
            self.err = False
            if k in (ord("q"), curses.KEY_F10):
                if self.mode != "ok":
                    self.cancel_cart()
                    continue
                break
            if k == 27:
                if self.mode != "ok":
                    self.cancel_cart()
                continue
            if k == 9:
                self.active = 1 - self.active
            elif k == curses.KEY_UP:
                self.pane.move(-1)
            elif k == curses.KEY_DOWN:
                self.pane.move(1)
            elif k == curses.KEY_PPAGE:
                self.pane.move(-8)
            elif k == curses.KEY_NPAGE:
                self.pane.move(8)
            elif k in (10, 13, curses.KEY_ENTER):
                self.add_to_cart()
            elif k == ord("/"):
                raw = self.prompt("filter", self.pane.filter)
                self.pane.filter = raw or ""
                self.pane.cursor = 0
            elif k == ord("t") and self.mode == "ok":
                cycle = ("journal", "parties", "orders", "stock")
                i = cycle.index(self.right.kind) if self.right.kind in cycle else 0
                self.right.kind = cycle[(i + 1) % len(cycle)]
            elif k == ord("v"):
                qty, costs = stock_from_journal()
                items = load_json(ITEMS)
                tot = sum(costs.get(s, int((items.get(s) or {}).get("cost") or 0)) * max(q, 0) for s, q in qty.items())
                self.say("stock " + money(tot))
            elif k == ord("c"):
                cmd_check()
                self.say("check done")
            elif k == ord("e"):
                cmd_csv()
                self.say("csv " + CSV_OUT)
            elif k in (ord("u"), ord("U")):
                self.do_undo()
            elif k in (curses.KEY_F1, ord("?")):
                self.help_screen()
            elif k == curses.KEY_F2:
                self.add_item()
            elif k == curses.KEY_F3:
                self.add_party()
            elif k == curses.KEY_F4:
                self.edit_item()
            elif k == curses.KEY_F5:
                self.scan_recv()
            elif k == curses.KEY_F6:
                self.do_ship()
            elif k == curses.KEY_F7:
                self.start_sale()
            elif k == curses.KEY_F8:
                self.do_adj()
            elif k == curses.KEY_F9:
                self.start_po()


def ui():
    if not sys.stdout.isatty():
        print("sERP UI needs a tty")
        return 2
    ensure()
    curses.wrapper(lambda s: App(s).run())
    return 0


def main(argv=None):
    ensure()
    p = argparse.ArgumentParser(prog="sERP")
    sub = p.add_subparsers(dest="cmd")
    for name in ("ui", "stock", "low", "buy", "value", "log", "sales", "check", "csv", "undo"):
        sub.add_parser(name)
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
        cmd_item_ls()
    elif args.cmd in ("low", "buy"):
        cmd_buy()
    elif args.cmd == "value":
        cmd_value()
    elif args.cmd == "log":
        cmd_log()
    elif args.cmd == "sales":
        cmd_sales()
    elif args.cmd == "check":
        return cmd_check()
    elif args.cmd == "csv":
        cmd_csv()
    elif args.cmd == "undo":
        return cmd_undo()
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
        return cmd_po(args.vendor, args.sku, args.qty, args.cost) or 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
