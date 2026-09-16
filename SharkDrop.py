#!/usr/bin/env python3
# SharkDrop — one-shot LAN file drop for SharkDeck.

# Stdlib only. Serves one directory over HTTP until you hit Ctrl-C.

#  python3 sharkdrop.py init
#  python3 sharkdrop.py ls
#  python3 sharkdrop.py start
#  python3 sharkdrop.py start /tmp --port 8000
#  python3 sharkdrop.py ip

# Version 1.0

from __future__ import annotations

import argparse
import http.server
import os
import socket
import sys
from functools import partial
from socketserver import ThreadingTCPServer

NAME = "SharkDrop"
WIDTH = 48
SEP = "-" * WIDTH

SCRIPT_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
HOME = os.environ.get("SHARKDROP_HOME", SCRIPT_DIR)
DROPBOX = os.path.join(HOME, "dropbox")
DEFAULT_PORT = 8000


class DropError(Exception):
    pass


def wrap_print(*parts: str) -> None:
    sys.stdout.write(" ".join(parts) + "\n")


def local_ips() -> list[str]:
    found: list[str] = []
    # route trick — works offline if a default iface exists
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            found.append(ip)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith("127."):
                found.append(ip)
    except OSError:
        pass
    return found or ["127.0.0.1"]


def count_files(root: str) -> tuple[int, int]:
    n = 0
    size = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            n += 1
            try:
                size += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return n, size


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / (1024 * 1024):.1f}M"


def resolve_dir(path: str | None) -> str:
    raw = path or DROPBOX
    raw = os.path.expanduser(raw)
    if not os.path.isabs(raw):
        raw = os.path.abspath(raw)
    if not os.path.isdir(raw):
        raise DropError(f"not a directory: {raw}")
    return raw


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def list_directory(self, path: str):
        return super().list_directory(path)


def cmd_init(_args: argparse.Namespace) -> int:
    os.makedirs(DROPBOX, exist_ok=True)
    readme = os.path.join(DROPBOX, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write("Put files in this folder, then run:\n")
            fh.write("  python3 sharkdrop.py start\n")
            fh.write("On another device open the printed URL.\n")
            fh.write("Ctrl-C stops the server.\n")
    wrap_print(f"{NAME} dropbox")
    wrap_print(DROPBOX)
    return 0


def cmd_ip(_args: argparse.Namespace) -> int:
    for ip in local_ips():
        wrap_print(ip)
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    root = resolve_dir(args.dir)
    n, size = count_files(root)
    wrap_print(root)
    wrap_print(f"{n} files  {fmt_size(size)}")
    wrap_print(SEP)
    shown = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            try:
                sz = os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                sz = 0
            line = f"{fmt_size(sz):>7}  {rel}"
            wrap_print(line[:WIDTH])
            shown += 1
            if shown >= 40:
                wrap_print("...")
                return 0
    if shown == 0:
        wrap_print("(empty)")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    root = resolve_dir(args.dir)
    port = args.port
    bind = args.bind
    n, size = count_files(root)
    handler = partial(QuietHandler, directory=root)
    ThreadingTCPServer.allow_reuse_address = True
    try:
        httpd = ThreadingTCPServer((bind, port), handler)
    except OSError as exc:
        raise DropError(f"cannot bind {bind}:{port} ({exc})") from exc

    real_port = httpd.server_address[1]
    ips = local_ips() if bind in {"0.0.0.0", ""} else [bind]
    wrap_print(NAME)
    wrap_print(f"dir   {root}"[:WIDTH])
    wrap_print(f"files {n}  {fmt_size(size)}")
    wrap_print(SEP)
    for ip in ips:
        wrap_print(f"http://{ip}:{real_port}/")
    wrap_print(SEP)
    wrap_print("Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        wrap_print("stopped")
    finally:
        httpd.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sharkdrop", description=f"{NAME} LAN file drop")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create dropbox folder")
    sub.add_parser("ip", help="print LAN addresses")
    lp = sub.add_parser("ls", help="list files that would be served")
    lp.add_argument("dir", nargs="?", default=None)
    sp = sub.add_parser("start", help="serve until Ctrl-C")
    sp.add_argument("dir", nargs="?", default=None, help="directory (default: ./dropbox)")
    sp.add_argument("--port", type=int, default=DEFAULT_PORT)
    sp.add_argument("--bind", default="0.0.0.0", help="0.0.0.0 = all interfaces")
    return p


HANDLERS = {
    "init": cmd_init,
    "ip": cmd_ip,
    "ls": cmd_ls,
    "start": cmd_start,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return HANDLERS[args.cmd](args)
    except DropError as exc:
        sys.stderr.write(f"{NAME}: {exc}\n")
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
