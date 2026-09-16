#!/usr/bin/env python3
"""sChess — terminal chess for SharkDeck. Stdlib only.

  schess
  Moves: e2e4   e4   Nf3   O-O   O-O-O
  Commands: help  legal  undo  new  fen  q
"""

import random
import sys

NAME = "sChess"
PIECE = {
    "K": "K", "Q": "Q", "R": "R", "B": "B", "N": "N", "P": "P",
    "k": "k", "q": "q", "r": "r", "b": "b", "n": "n", "p": "p",
}
VAL = {"K": 10000, "Q": 900, "R": 500, "B": 330, "N": 320, "P": 100}
START = "rnbqkbnrpppppppp" + "." * 32 + "PPPPPPPPRNBQKBNR"

N, S, E, W = -8, 8, 1, -1
DIRS = {
    "N": (N + W, N + E, S + W, S + E, N + N + W, N + N + E, S + S + W, S + S + E),
    "B": (N + W, N + E, S + W, S + E),
    "R": (N, S, E, W),
    "Q": (N, S, E, W, N + W, N + E, S + W, S + E),
    "K": (N, S, E, W, N + W, N + E, S + W, S + E),
}


def on_board(i):
    return 0 <= i < 64


def file_of(i):
    return i % 8


def rank_of(i):
    return i // 8


def sq_name(i):
    return "abcdefgh"[file_of(i)] + "12345678"[7 - rank_of(i)]


def parse_sq(s):
    s = s.strip().lower()
    if len(s) != 2 or s[0] not in "abcdefgh" or s[1] not in "12345678":
        return None
    return (8 - int(s[1])) * 8 + (ord(s[0]) - 97)


def is_white(p):
    return p.isupper()


def enemy(p, white):
    return p != "." and is_white(p) != white


class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        self.b = list(START)
        self.white = True
        self.wk = True
        self.wq = True
        self.bk = True
        self.bq = True
        self.ep = None
        self.hist = []
        self.half = 0

    def king(self, white):
        t = "K" if white else "k"
        return self.b.index(t)

    def copy(self):
        g = Game.__new__(Game)
        g.b = self.b[:]
        g.white = self.white
        g.wk, g.wq, g.bk, g.bq = self.wk, self.wq, self.bk, self.bq
        g.ep = self.ep
        g.hist = []
        g.half = self.half
        return g

    def attacked(self, sq, by_white):
        b = self.b
        # pawns
        if by_white:
            for d in (S + W, S + E):
                j = sq + d
                if on_board(j) and abs(file_of(j) - file_of(sq)) == 1 and b[j] == "P":
                    return True
        else:
            for d in (N + W, N + E):
                j = sq + d
                if on_board(j) and abs(file_of(j) - file_of(sq)) == 1 and b[j] == "p":
                    return True
        for d in DIRS["N"]:
            j = sq + d
            if on_board(j) and abs(file_of(j) - file_of(sq)) <= 2 and b[j] in ("N" if by_white else "n",):
                if abs(file_of(j) - file_of(sq)) in (1, 2):
                    return True
        for d in DIRS["K"]:
            j = sq + d
            if on_board(j) and abs(file_of(j) - file_of(sq)) <= 1 and b[j] == ("K" if by_white else "k"):
                return True
        for sliders, pieces in (
            (DIRS["B"], "BQ" if by_white else "bq"),
            (DIRS["R"], "RQ" if by_white else "rq"),
        ):
            for d in sliders:
                j = sq + d
                while on_board(j) and abs(file_of(j) - file_of(j - d)) <= 1:
                    p = b[j]
                    if p != ".":
                        if p in pieces:
                            return True
                        break
                    j += d
        return False

    def in_check(self, white):
        return self.attacked(self.king(white), not white)

    def raw_moves(self, white):
        b = self.b
        out = []
        for i, p in enumerate(b):
            if p == "." or is_white(p) != white:
                continue
            kind = p.upper()
            if kind == "P":
                step = N if white else S
                start = 6 if white else 1
                j = i + step
                if on_board(j) and b[j] == ".":
                    out.append((i, j, None))
                    j2 = i + step * 2
                    if rank_of(i) == start and b[j2] == ".":
                        out.append((i, j2, None))
                for d in (step + W, step + E):
                    j = i + d
                    if not on_board(j) or abs(file_of(j) - file_of(i)) != 1:
                        continue
                    if enemy(b[j], white) or j == self.ep:
                        out.append((i, j, None))
            elif kind == "N":
                for d in DIRS["N"]:
                    j = i + d
                    if not on_board(j):
                        continue
                    df = abs(file_of(j) - file_of(i))
                    dr = abs(rank_of(j) - rank_of(i))
                    if sorted((df, dr)) != [1, 2]:
                        continue
                    if b[j] == "." or enemy(b[j], white):
                        out.append((i, j, None))
            elif kind == "K":
                for d in DIRS["K"]:
                    j = i + d
                    if not on_board(j) or abs(file_of(j) - file_of(i)) > 1:
                        continue
                    if b[j] == "." or enemy(b[j], white):
                        out.append((i, j, None))
                # castle
                if white and i == 60:
                    if self.wk and b[61] == b[62] == "." and not self.attacked(60, False) and not self.attacked(61, False) and not self.attacked(62, False):
                        out.append((60, 62, "K"))
                    if self.wq and b[59] == b[58] == b[57] == "." and not self.attacked(60, False) and not self.attacked(59, False) and not self.attacked(58, False):
                        out.append((60, 58, "Q"))
                if (not white) and i == 4:
                    if self.bk and b[5] == b[6] == "." and not self.attacked(4, True) and not self.attacked(5, True) and not self.attacked(6, True):
                        out.append((4, 6, "k"))
                    if self.bq and b[3] == b[2] == b[1] == "." and not self.attacked(4, True) and not self.attacked(3, True) and not self.attacked(2, True):
                        out.append((4, 2, "q"))
            else:
                rays = DIRS[kind]
                slide = kind != "K"
                for d in rays:
                    j = i + d
                    while on_board(j) and abs(file_of(j) - file_of(j - d)) <= 1:
                        if b[j] == ".":
                            out.append((i, j, None))
                        elif enemy(b[j], white):
                            out.append((i, j, None))
                            break
                        else:
                            break
                        if not slide:
                            break
                        j += d
        return out

    def apply(self, mv):
        a, c, flag = mv
        p = self.b[a]
        cap = self.b[c]
        ep_cap = None
        if p.upper() == "P" and c == self.ep and cap == ".":
            ep_cap = c + (S if is_white(p) else N)
            cap = self.b[ep_cap]
            self.b[ep_cap] = "."
        self.b[c] = p
        self.b[a] = "."
        if p == "P" and rank_of(c) == 0:
            self.b[c] = "Q"
        if p == "p" and rank_of(c) == 7:
            self.b[c] = "q"
        if flag == "K":
            self.b[63], self.b[61] = ".", "R"
        if flag == "Q":
            self.b[56], self.b[59] = ".", "R"
        if flag == "k":
            self.b[7], self.b[5] = ".", "r"
        if flag == "q":
            self.b[0], self.b[3] = ".", "r"
        self.wk = self.wk and a != 60 and a != 63 and c != 63
        self.wq = self.wq and a != 60 and a != 56 and c != 56
        self.bk = self.bk and a != 4 and a != 7 and c != 7
        self.bq = self.bq and a != 4 and a != 0 and c != 0
        self.ep = None
        if p.upper() == "P" and abs(c - a) == 16:
            self.ep = (a + c) // 2
        self.white = not self.white
        return (a, c, flag, p, cap, ep_cap)

    def legal(self):
        good = []
        side = self.white
        for mv in self.raw_moves(side):
            g = self.copy()
            g.apply(mv)
            if not g.in_check(side):
                good.append(mv)
        return good

    def score(self):
        t = 0
        for i, p in enumerate(self.b):
            if p == ".":
                continue
            v = VAL[p.upper()]
            # nudge pieces toward center
            f, r = file_of(i), rank_of(i)
            center = 3 - abs(3.5 - f) - abs(3.5 - r)
            v += int(center * 4)
            t += v if is_white(p) else -v
        if self.in_check(True):
            t -= 40
        if self.in_check(False):
            t += 40
        return t

    def search(self, depth, alpha, beta):
        moves = self.legal()
        if not moves:
            if self.in_check(self.white):
                return (-99999 if self.white else 99999, None)
            return (0, None)
        if depth == 0:
            return (self.score(), None)
        best = None
        random.shuffle(moves)
        if self.white:
            val = -10**9
            for mv in moves:
                g = self.copy()
                g.apply(mv)
                sc, _ = g.search(depth - 1, alpha, beta)
                if sc > val:
                    val, best = sc, mv
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            return val, best
        val = 10**9
        for mv in moves:
            g = self.copy()
            g.apply(mv)
            sc, _ = g.search(depth - 1, alpha, beta)
            if sc < val:
                val, best = sc, mv
            beta = min(beta, val)
            if beta <= alpha:
                break
        return val, best


def render(g):
    lines = [NAME + "  you=white  CPU=black", "  a b c d e f g h"]
    for r in range(8):
        row = str(8 - r) + " "
        for f in range(8):
            p = g.b[r * 8 + f]
            dark = (r + f) % 2
            ch = p if p != "." else ("." if dark else " ")
            row += ch + " "
        row += str(8 - r)
        lines.append(row)
    lines.append("  a b c d e f g h")
    if g.in_check(g.white):
        lines.append("check")
    return "\n".join(lines)


def san_candidates(g, text):
    text = text.strip().replace("-", "").replace(" ", "")
    moves = g.legal()
    if text.lower() in ("oo", "00", "castle"):
        return [m for m in moves if m[2] in ("K", "k")]
    if text.lower() in ("ooo", "000"):
        return [m for m in moves if m[2] in ("Q", "q")]
    # e2e4
    if len(text) == 4 and parse_sq(text[:2]) is not None and parse_sq(text[2:]) is not None:
        a, c = parse_sq(text[:2]), parse_sq(text[2:])
        return [m for m in moves if m[0] == a and m[1] == c]
    # e4
    if len(text) == 2 and parse_sq(text) is not None:
        c = parse_sq(text)
        pawns = [m for m in moves if m[1] == c and g.b[m[0]].upper() == "P"]
        return pawns
    # Nf3 / Nb1c3 / Bxc6
    t = text.replace("x", "")
    if t and t[0] in "NBRQKnbrqk":
        kind = t[0].upper()
        dest = parse_sq(t[-2:])
        if dest is None:
            return []
        hint = t[1:-2]
        hits = []
        for m in moves:
            if m[1] != dest:
                continue
            if g.b[m[0]].upper() != kind:
                continue
            if hint:
                if hint in sq_name(m[0]) or sq_name(m[0]).startswith(hint) or hint in sq_name(m[0]):
                    hits.append(m)
            else:
                hits.append(m)
        return hits
    return []


def play():
    g = Game()
    print(render(g))
    print("move like e2e4 or e4 or Nf3.  help  legal  undo  new  q")
    while True:
        if not g.white:
            print("CPU...")
            _, mv = g.search(2, -10**9, 10**9)
            if mv is None:
                print("you win" if g.in_check(False) else "draw")
                return
            print("CPU", sq_name(mv[0]) + sq_name(mv[1]))
            snap = (g.b[:], g.white, g.wk, g.wq, g.bk, g.bq, g.ep)
            g.hist.append(snap)
            g.apply(mv)
            print(render(g))
            if not g.legal():
                print("checkmate" if g.in_check(True) else "stalemate")
                return
            continue
        try:
            raw = input("white> ").strip()
        except EOFError:
            return
        if not raw:
            continue
        cmd = raw.lower()
        if cmd in ("q", "quit", "exit"):
            return
        if cmd == "help":
            print("e2e4  e4  Nf3  O-O  O-O-O  legal  undo  new  fen")
            continue
        if cmd == "new":
            g.reset()
            print(render(g))
            continue
        if cmd == "undo":
            if len(g.hist) >= 2:
                g.b, g.white, g.wk, g.wq, g.bk, g.bq, g.ep = g.hist[-2]
                g.hist = g.hist[:-2]
            elif g.hist:
                g.b, g.white, g.wk, g.wq, g.bk, g.bq, g.ep = g.hist.pop()
            print(render(g))
            continue
        if cmd == "legal":
            print(" ".join(sorted(sq_name(m[0]) + sq_name(m[1]) for m in g.legal())))
            continue
        if cmd == "fen":
            print("".join(g.b))
            continue
        hits = san_candidates(g, raw)
        if len(hits) != 1:
            print("no move" if not hits else "ambiguous: " + " ".join(sq_name(m[0]) + sq_name(m[1]) for m in hits))
            continue
        mv = hits[0]
        snap = (g.b[:], g.white, g.wk, g.wq, g.bk, g.bq, g.ep)
        g.hist.append(snap)
        g.apply(mv)
        print(render(g))
        if not g.legal() and not g.white:
            print("you win" if g.in_check(False) else "draw")
            return


if __name__ == "__main__":
    try:
        play()
    except KeyboardInterrupt:
        print()
        sys.exit(0)