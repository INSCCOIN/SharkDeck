#!/usr/bin/env python3
"""SharkLedger — pocket CLI ledger for SharkDeck.

Single file. Stdlib only. Amounts stored as integer cents.
Default data dir: directory containing this script
  (intended: /home/working/SharkDeck/SharkDeck/led).

  sharkledger init
  sharkledger account add cash
  sharkledger add 12.50 food --payee Meijer --note milk
  sharkledger in 800.00 pay --acct bank --payee work
  sharkledger log
  sharkledger bal
  sharkledger month
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import random
import string
import sys
import textwrap
from datetime import date, datetime
from typing import Any

NAME = "SharkLedger"
WIDTH = 48
SEP = "-" * WIDTH

# Data lives beside the script unless SHARKLEDGER_HOME is set.
SCRIPT_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
HOME = os.environ.get("SHARKLEDGER_HOME", SCRIPT_DIR)
JOURNAL = os.path.join(HOME, "journal.jsonl")
ACCOUNTS = os.path.join(HOME, "accounts.json")
CATEGORIES = os.path.join(HOME, "categories.txt")
LOCKFILE = os.path.join(HOME, ".lock")

DEFAULT_ACCOUNT = "cash"


# ---------------------------------------------------------------------------
# money
# ---------------------------------------------------------------------------

class LedgerError(Exception):
    pass


def dollars_to_cents(raw: str) -> int:
    s = str(raw).strip().replace(",", "").replace("$", "")
    if not s or s in {".", "-", "+"}:
        raise LedgerError("amount looks empty")
    sign = 1
    if s[0] == "+":
        s = s[1:]
    elif s[0] == "-":
        sign = -1
        s = s[1:]
    if "." in s:
        whole, frac = s.split(".", 1)
        if whole == "":
            whole = "0"
        if not whole.isdigit() or not frac.isdigit():
            raise LedgerError("amount must be digits, like 12.50")
        if len(frac) > 2:
            raise LedgerError("max two decimal places")
        frac = (frac + "00")[:2]
        cents = int(whole) * 100 + int(frac)
    else:
        if not s.isdigit():
            raise LedgerError("amount must be digits, like 12.50")
        cents = int(s) * 100
    return sign * cents


def cents_to_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    n = abs(int(cents))
    return f"{sign}{n // 100}.{n % 100:02d}"


def pad_money(cents: int) -> str:
    return f"{cents_to_dollars(cents):>10}"


# ---------------------------------------------------------------------------
# ids / dates
# ---------------------------------------------------------------------------

def now_local() -> datetime:
    return datetime.now().astimezone()


def today_iso() -> str:
    return date.today().isoformat()


def parse_date(raw: str) -> str:
    raw = raw.strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise LedgerError("date must be YYYY-MM-DD") from exc


def parse_month(raw: str) -> str:
    raw = raw.strip()
    try:
        return datetime.strptime(raw, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise LedgerError("month must be YYYY-MM") from exc


def new_id(when: datetime | None = None) -> str:
    dt = when or now_local()
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return dt.strftime("%Y%m%d-%H%M%S") + "-" + suffix


def slug(name: str) -> str:
    s = name.strip().lower().replace(" ", "_")
    out = []
    for ch in s:
        if ch.isalnum() or ch in {"_", "-"}:
            out.append(ch)
    s = "".join(out).strip("_-")
    if not s:
        raise LedgerError("name is empty")
    return s


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def ensure_home() -> None:
    os.makedirs(HOME, exist_ok=True)


def _lock_exclusive():
    ensure_home()
    fd = os.open(LOCKFILE, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def load_accounts() -> dict[str, dict[str, Any]]:
    if not os.path.exists(ACCOUNTS):
        return {}
    with open(ACCOUNTS, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise LedgerError("accounts.json is corrupt")
    return data


def save_accounts(data: dict[str, dict[str, Any]]) -> None:
    ensure_home()
    tmp = ACCOUNTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ACCOUNTS)
    os.chmod(ACCOUNTS, 0o600)


def load_categories() -> list[str]:
    if not os.path.exists(CATEGORIES):
        return []
    with open(CATEGORIES, "r", encoding="utf-8") as fh:
        names = []
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(slug(line))
        return names


def save_categories(names: list[str]) -> None:
    ensure_home()
    tmp = CATEGORIES + ".tmp"
    uniq = sorted(set(names))
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# SharkLedger categories\n")
        for n in uniq:
            fh.write(n + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, CATEGORIES)
    os.chmod(CATEGORIES, 0o600)


def append_journal(record: dict[str, Any]) -> None:
    ensure_home()
    record = dict(record)
    record.setdefault("written", now_local().isoformat(timespec="seconds"))
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(JOURNAL, flags, 0o600)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def read_journal() -> list[dict[str, Any]]:
    if not os.path.exists(JOURNAL):
        return []
    rows = []
    with open(JOURNAL, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"journal.jsonl line {lineno} is corrupt") from exc
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

def replay() -> dict[str, dict[str, Any]]:
    """Active transactions keyed by id. Voids drop an id. Edits replace fields."""
    active: dict[str, dict[str, Any]] = {}
    for rec in read_journal():
        kind = rec.get("type")
        if kind == "txn":
            active[rec["id"]] = dict(rec)
        elif kind == "void":
            target = rec.get("void_of")
            if target in active:
                del active[target]
        elif kind == "edit":
            target = rec.get("void_of")
            if target in active:
                merged = dict(active[target])
                for key in ("date", "amount", "account", "category", "payee", "note"):
                    if key in rec and rec[key] is not None:
                        merged[key] = rec[key]
                merged["id"] = target
                merged["type"] = "txn"
                active[target] = merged
    return active


def txns_sorted(active: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = list((active or replay()).values())
    rows.sort(key=lambda r: (r.get("date", ""), r.get("id", "")), reverse=True)
    return rows


def require_init() -> None:
    if not os.path.exists(ACCOUNTS):
        raise LedgerError(f"not initialized. run: {prog()} init")


def require_account(name: str, accounts: dict[str, dict[str, Any]]) -> str:
    name = slug(name)
    if name not in accounts:
        raise LedgerError(f"unknown account '{name}'. add it first")
    return name


def require_category(name: str, create: bool = False) -> str:
    name = slug(name)
    cats = load_categories()
    if name not in cats:
        if create or not cats:
            cats.append(name)
            save_categories(cats)
        else:
            raise LedgerError(
                f"unknown category '{name}'. led cat add {name}  (or add any while list is empty)"
            )
    return name


# ---------------------------------------------------------------------------
# print
# ---------------------------------------------------------------------------

def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(
        text,
        width=WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def print_lines(lines: list[str]) -> None:
    sys.stdout.write("\n".join(lines) + "\n")


def fmt_txn(row: dict[str, Any]) -> list[str]:
    head = f"{row.get('date', '?')}  {row.get('account', '?')}    {row.get('category', '?')}"
    money = pad_money(int(row.get("amount", 0)))
    payee = row.get("payee") or ""
    mid = f"{money}  {payee}".rstrip()
    out = [head[:WIDTH], mid[:WIDTH]]
    note = (row.get("note") or "").strip()
    if note:
        out.append(wrap(note)[:WIDTH])
    out.append(f"id {row.get('id', '')}"[:WIDTH])
    out.append(SEP)
    return out


def prog() -> str:
    return os.path.basename(sys.argv[0])


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_init(_args: argparse.Namespace) -> int:
    ensure_home()
    accounts = load_accounts()
    created = False
    if DEFAULT_ACCOUNT not in accounts:
        accounts[DEFAULT_ACCOUNT] = {
            "name": DEFAULT_ACCOUNT,
            "open_cents": 0,
            "open_date": today_iso(),
        }
        created = True
    save_accounts(accounts)
    if not os.path.exists(CATEGORIES):
        save_categories(
            ["food", "fuel", "tools", "pay", "rent", "home", "xfer", "other"]
        )
    if not os.path.exists(JOURNAL):
        open(JOURNAL, "a", encoding="utf-8").close()
        os.chmod(JOURNAL, 0o600)
    print(f"{NAME} ready")
    print(f"home  {HOME}")
    if created:
        print(f"account '{DEFAULT_ACCOUNT}' created (opening 0.00)")
    return 0


def cmd_account(args: argparse.Namespace) -> int:
    require_init()
    accounts = load_accounts()
    if args.account_cmd == "add":
        name = slug(args.name)
        if name in accounts:
            raise LedgerError(f"account '{name}' already exists")
        open_cents = dollars_to_cents(args.open) if args.open is not None else 0
        if open_cents < 0:
            raise LedgerError("opening balance cannot be negative")
        accounts[name] = {
            "name": name,
            "open_cents": open_cents,
            "open_date": parse_date(args.date) if args.date else today_iso(),
        }
        save_accounts(accounts)
        print(f"account {name}  open {cents_to_dollars(open_cents)}")
        return 0
    # list
    if not accounts:
        print("no accounts. led account add cash")
        return 0
    lines = []
    for name in sorted(accounts):
        ac = accounts[name]
        lines.append(
            f"{name:<16} open {pad_money(int(ac.get('open_cents', 0)))}  "
            f"{ac.get('open_date', '')}"
        )
    print_lines(lines)
    return 0


def cmd_cat(args: argparse.Namespace) -> int:
    require_init()
    cats = load_categories()
    if args.cat_cmd == "add":
        name = slug(args.name)
        if name in cats:
            raise LedgerError(f"category '{name}' already exists")
        cats.append(name)
        save_categories(cats)
        print(f"category {name}")
        return 0
    if not cats:
        print("no categories")
        return 0
    print_lines(sorted(cats))
    return 0


def _add_txn(amount_cents: int, args: argparse.Namespace) -> int:
    require_init()
    accounts = load_accounts()
    acct = require_account(args.acct or DEFAULT_ACCOUNT, accounts)
    cats = load_categories()
    cat = require_category(args.category, create=(len(cats) == 0))
    when = parse_date(args.date) if args.date else today_iso()
    rec = {
        "type": "txn",
        "id": new_id(),
        "date": when,
        "amount": int(amount_cents),
        "account": acct,
        "category": cat,
        "payee": (args.payee or "").strip(),
        "note": (args.note or "").strip(),
    }
    append_journal(rec)
    print_lines(fmt_txn(rec)[:-1])
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    cents = dollars_to_cents(args.amount)
    if cents == 0:
        raise LedgerError("amount cannot be 0")
    # expenses stored negative
    if cents > 0:
        cents = -cents
    return _add_txn(cents, args)


def cmd_in(args: argparse.Namespace) -> int:
    cents = dollars_to_cents(args.amount)
    if cents == 0:
        raise LedgerError("amount cannot be 0")
    if cents < 0:
        cents = -cents
    return _add_txn(cents, args)


def _filter_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    out = rows
    if getattr(args, "acct", None):
        name = slug(args.acct)
        out = [r for r in out if r.get("account") == name]
    if getattr(args, "cat", None):
        name = slug(args.cat)
        out = [r for r in out if r.get("category") == name]
    if getattr(args, "since", None):
        since = parse_date(args.since)
        out = [r for r in out if r.get("date", "") >= since]
    if getattr(args, "until", None):
        until = parse_date(args.until)
        out = [r for r in out if r.get("date", "") <= until]
    return out


def cmd_log(args: argparse.Namespace) -> int:
    require_init()
    rows = _filter_rows(txns_sorted(), args)
    limit = args.n if args.n is not None else 20
    if limit <= 0:
        raise LedgerError("--n must be > 0")
    rows = rows[:limit]
    if not rows:
        print("no transactions")
        return 0
    lines: list[str] = []
    for row in rows:
        lines.extend(fmt_txn(row))
    if lines and lines[-1] == SEP:
        lines.pop()
    print_lines(lines)
    return 0


def balances() -> dict[str, int]:
    accounts = load_accounts()
    bal = {name: int(ac.get("open_cents", 0)) for name, ac in accounts.items()}
    for row in replay().values():
        acct = row.get("account")
        if acct not in bal:
            bal[acct] = 0
        bal[acct] += int(row.get("amount", 0))
    return bal


def cmd_bal(args: argparse.Namespace) -> int:
    require_init()
    bal = balances()
    if args.account:
        name = slug(args.account)
        if name not in bal:
            raise LedgerError(f"unknown account '{name}'")
        print(f"{name:<12} {pad_money(bal[name])}")
        return 0
    if not bal:
        print("no accounts")
        return 0
    lines = []
    net = 0
    for name in sorted(bal):
        lines.append(f"{name:<12} {pad_money(bal[name])}")
        net += bal[name]
    lines.append(SEP)
    lines.append(f"{'net':<12} {pad_money(net)}")
    print_lines(lines)
    return 0


def cmd_month(args: argparse.Namespace) -> int:
    require_init()
    month = parse_month(args.month) if args.month else date.today().strftime("%Y-%m")
    rows = [r for r in replay().values() if str(r.get("date", "")).startswith(month)]
    by_cat: dict[str, int] = {}
    total = 0
    for r in rows:
        cat = r.get("category") or "other"
        by_cat[cat] = by_cat.get(cat, 0) + int(r.get("amount", 0))
        total += int(r.get("amount", 0))
    lines = [month]
    if not by_cat:
        lines.append("no transactions")
        print_lines(lines)
        return 0
    for cat in sorted(by_cat):
        lines.append(f"{cat:<12} {pad_money(by_cat[cat])}")
    lines.append(SEP)
    lines.append(f"{'net':<12} {pad_money(total)}")
    print_lines(lines)
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    require_init()
    q = args.query.strip().lower()
    if not q:
        raise LedgerError("empty query")
    hits = []
    for row in txns_sorted():
        blob = " ".join(
            str(row.get(k, ""))
            for k in ("id", "date", "account", "category", "payee", "note")
        ).lower()
        blob += " " + cents_to_dollars(int(row.get("amount", 0)))
        if q in blob:
            hits.append(row)
    if not hits:
        print("no match")
        return 0
    lines: list[str] = []
    for row in hits[:50]:
        lines.extend(fmt_txn(row))
    if lines and lines[-1] == SEP:
        lines.pop()
    print_lines(lines)
    return 0


def lookup(prefix: str) -> dict[str, Any]:
    active = replay()
    if prefix in active:
        return active[prefix]
    hits = [row for tid, row in active.items() if tid.startswith(prefix)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise LedgerError(f"no transaction {prefix}")
    raise LedgerError(f"id '{prefix}' is ambiguous ({len(hits)} matches)")


def cmd_show(args: argparse.Namespace) -> int:
    require_init()
    print_lines(fmt_txn(lookup(args.id))[:-1])
    return 0


def cmd_void(args: argparse.Namespace) -> int:
    require_init()
    row = lookup(args.id)
    rec = {"type": "void", "id": new_id(), "void_of": row["id"]}
    append_journal(rec)
    print(f"voided {row['id']}")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    require_init()
    row = lookup(args.id)
    patch: dict[str, Any] = {
        "type": "edit",
        "id": new_id(),
        "void_of": row["id"],
    }
    changed = False
    if args.date:
        patch["date"] = parse_date(args.date)
        changed = True
    if args.amount:
        cents = dollars_to_cents(args.amount)
        # keep sign unless they passed an explicit sign; treat as replacement value
        patch["amount"] = cents
        changed = True
    if args.acct:
        accounts = load_accounts()
        patch["account"] = require_account(args.acct, accounts)
        changed = True
    if args.cat:
        patch["category"] = require_category(args.cat, create=True)
        changed = True
    if args.payee is not None:
        patch["payee"] = args.payee.strip()
        changed = True
    if args.note is not None:
        patch["note"] = args.note.strip()
        changed = True
    if not changed:
        raise LedgerError("nothing to edit")
    append_journal(patch)
    print_lines(fmt_txn(lookup(row["id"]))[:-1])
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    require_init()
    rows = read_journal()
    active = replay()
    voids = sum(1 for r in rows if r.get("type") == "void")
    edits = sum(1 for r in rows if r.get("type") == "edit")
    txns = sum(1 for r in rows if r.get("type") == "txn")
    print(f"home     {HOME}")
    print(f"journal  {txns} txn  {voids} void  {edits} edit")
    print(f"active   {len(active)}")
    print(f"accounts {len(load_accounts())}")
    print(f"cats     {len(load_categories())}")
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sharkledger",
        description=f"{NAME} — CLI pocket ledger",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create ledger files")

    ap = sub.add_parser("account", help="accounts")
    asub = ap.add_subparsers(dest="account_cmd", required=True)
    adda = asub.add_parser("add", help="create an account")
    adda.add_argument("name")
    adda.add_argument("--open", default="0", help="opening balance in dollars")
    adda.add_argument("--date", help="opening date YYYY-MM-DD")
    asub.add_parser("list", help="list accounts")

    cp = sub.add_parser("cat", help="categories")
    csub = cp.add_subparsers(dest="cat_cmd", required=True)
    addc = csub.add_parser("add")
    addc.add_argument("name")
    csub.add_parser("list")

    def txn_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("amount", help="dollars, e.g. 12.50")
        sp.add_argument("category")
        sp.add_argument("--acct", default=None, help=f"account (default {DEFAULT_ACCOUNT})")
        sp.add_argument("--payee", default="")
        sp.add_argument("--note", default="")
        sp.add_argument("--date", help="YYYY-MM-DD (default today)")

    addp = sub.add_parser("add", help="record a spend (stored negative)")
    txn_flags(addp)
    inp = sub.add_parser("in", help="record income (stored positive)")
    txn_flags(inp)

    lp = sub.add_parser("log", help="recent transactions")
    lp.add_argument("--acct")
    lp.add_argument("--cat")
    lp.add_argument("--since", help="YYYY-MM-DD")
    lp.add_argument("--until", help="YYYY-MM-DD")
    lp.add_argument("-n", type=int, default=20, help="how many (default 20)")

    bp = sub.add_parser("bal", help="balances")
    bp.add_argument("account", nargs="?", default=None)

    mp = sub.add_parser("month", help="this month by category")
    mp.add_argument("month", nargs="?", help="YYYY-MM")

    fp = sub.add_parser("find", help="search payee/note/id")
    fp.add_argument("query")

    sp = sub.add_parser("show", help="one transaction")
    sp.add_argument("id")

    vp = sub.add_parser("void", help="soft-delete a transaction")
    vp.add_argument("id")

    ep = sub.add_parser("edit", help="change fields (journaled)")
    ep.add_argument("id")
    ep.add_argument("--date")
    ep.add_argument("--amount", help="new amount in dollars (signed)")
    ep.add_argument("--acct")
    ep.add_argument("--cat")
    ep.add_argument("--payee")
    ep.add_argument("--note")

    sub.add_parser("check", help="journal health")
    return p


HANDLERS = {
    "init": cmd_init,
    "account": cmd_account,
    "cat": cmd_cat,
    "add": cmd_add,
    "in": cmd_in,
    "log": cmd_log,
    "bal": cmd_bal,
    "month": cmd_month,
    "find": cmd_find,
    "show": cmd_show,
    "void": cmd_void,
    "edit": cmd_edit,
    "check": cmd_check,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    fd = None
    try:
        if args.cmd != "init":
            fd = _lock_exclusive()
        return HANDLERS[args.cmd](args)
    except LedgerError as exc:
        sys.stderr.write(f"{NAME}: {exc}\n")
        return 2
    except BrokenPipeError:
        return 0
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
