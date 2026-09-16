#!/usr/bin/env python3
"""
Graph3D - Pure Python 3D Surface Plotter for SharkDeck
No external modules. Terminal ASCII rendering.
"""

import math
import os
import sys
from math import sin, cos, sqrt, exp, log, log10, tan, pi, e, floor, ceil
from math import asin, acos, atan, atan2, sinh, cosh, tanh

# ====================== SAFE FUNCTIONS ======================

SAFE = {
    "abs": abs, "min": min, "max": max, "pow": pow, "round": round,
    "sin": sin, "cos": cos, "tan": tan,
    "asin": asin, "acos": acos, "atan": atan, "atan2": atan2,
    "sinh": sinh, "cosh": cosh, "tanh": tanh,
    "log": log, "log10": log10, "exp": exp, "sqrt": sqrt,
    "pi": pi, "e": e, "floor": floor, "ceil": ceil,
}

PRESETS = [
    ("Wave",          "0.6*sin(x)*cos(y)"),
    ("Paraboloid",    "0.12*(x**2 + y**2)"),
    ("Saddle",        "0.12*(x**2 - y**2)"),
    ("Ripple",        "sin(sqrt(x**2 + y**2))"),
    ("Sombrero",      "sin(sqrt(x**2+y**2)+0.001)/(sqrt(x**2+y**2)+0.4)"),
    ("Hyperbolic",    "0.18*x*y"),
    ("Gaussian",      "1.6*exp(-(x**2+y**2)/3)"),
    ("Twin Peaks",    "1.4*(exp(-((x-2)**2 + y**2)/2) + exp(-((x+2)**2 + y**2)/2))"),
    ("Bowl",          "-0.1*(x**2 + y**2)"),
    ("Checker",       "0.5*sin(2*x)*sin(2*y)"),
    ("Volcano",       "1.2*exp(-(x**2+y**2)/4) - 0.6*exp(-(x**2+y**2)/0.6)"),
]

# ====================== HELPERS ======================

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def clean_expr(expr):
    expr = (expr or "").strip()
    expr = expr.replace("^", "**")
    low = expr.lower()
    if low.startswith("z=") or low.startswith("f="):
        expr = expr[2:]
    return expr.strip()

def evaluate(expr, x, y):
    env = dict(SAFE)
    env["x"] = x
    env["y"] = y
    env["r"] = sqrt(x*x + y*y)
    try:
        code = compile(expr, "<expr>", "eval")
        val = eval(code, {"__builtins__": {}}, env)
        if isinstance(val, (int, float)) and math.isfinite(val):
            return float(val)
    except Exception:
        pass
    return None

# ====================== ASCII 3D RENDERER ======================

def render_surface(expr, range_val=4.0, width=70, height=28, pitch=0.5, yaw=0.7):
    expr = clean_expr(expr)
    if not expr:
        print("No equation.")
        return

    # Sample grid
    grid_n = 28
    zs = []
    zmin, zmax = 1e9, -1e9

    for j in range(grid_n):
        row = []
        y = -range_val + (2 * range_val) * j / (grid_n - 1)
        for i in range(grid_n):
            x = -range_val + (2 * range_val) * i / (grid_n - 1)
            z = evaluate(expr, x, y)
            row.append(z)
            if z is not None:
                zmin = min(zmin, z)
                zmax = max(zmax, z)
        zs.append(row)

    if zmax - zmin < 1e-9:
        zmax = zmin + 1.0

    # Projection parameters
    cx, cy = width // 2, height // 2
    focal = 18.0
    cam = 9.0
    scale = 1.0

    # Characters from low to high
    chars = " .:-=+*#%@"

    # Create empty screen
    screen = [[" " for _ in range(width)] for _ in range(height)]
    zbuf = [[-1e9 for _ in range(width)] for _ in range(height)]

    def project(x, y, z):
        # Simple rotation
        cyaw, syaw = cos(yaw), sin(yaw)
        cpitch, spitch = cos(pitch), sin(pitch)

        x1 = x * cyaw - y * syaw
        z1 = x * syaw + y * cyaw
        y1 = z

        y2 = y1 * cpitch - z1 * spitch
        z2 = y1 * spitch + z1 * cpitch

        zc = cam - z2
        if zc < 0.5:
            return None
        s = (focal * scale) / zc
        sx = int(cx + x1 * s * 3.2)
        sy = int(cy - y2 * s * 1.6)
        return sx, sy, zc

    # Draw points
    for j in range(grid_n):
        for i in range(grid_n):
            z = zs[j][i]
            if z is None:
                continue
            x = -range_val + (2 * range_val) * i / (grid_n - 1)
            y = -range_val + (2 * range_val) * j / (grid_n - 1)

            # Normalize height for character
            t = (z - zmin) / (zmax - zmin)
            ch = chars[int(t * (len(chars) - 1))]

            p = project(x, y, z * 0.7)
            if p is None:
                continue
            sx, sy, depth = p
            if 0 <= sx < width and 0 <= sy < height:
                if depth > zbuf[sy][sx]:
                    zbuf[sy][sx] = depth
                    screen[sy][sx] = ch

    # Print
    print("+" + "-" * width + "+")
    for row in screen:
        print("|" + "".join(row) + "|")
    print("+" + "-" * width + "+")
    print(f"z = {expr}")
    print(f"Range ±{range_val}   Height: {zmin:.2f} → {zmax:.2f}")

# ====================== MAIN MENU ======================

def main():
    expr = "0.6*sin(x)*cos(y)"
    range_val = 4.0
    pitch = 0.55
    yaw = 0.70

    while True:
        clear()
        print("=" * 50)
        print("       Graph3D - SharkDeck (Pure Python)")
        print("=" * 50)
        print(f"\n  Current equation : z = {expr}")
        print(f"  Range            : ±{range_val}")
        print("""
  1. Plot
  2. Enter new equation
  3. Presets
  4. Change range
  5. Rotate view (yaw/pitch)
  0. Exit
        """)
        choice = input("Select: ").strip()

        if choice == "1":
            clear()
            try:
                render_surface(expr, range_val, pitch=pitch, yaw=yaw)
            except Exception as e:
                print(f"Error: {e}")
            input("\nPress Enter to return...")

        elif choice == "2":
            print("\nEnter equation using x and y")
            print("Example: sin(x)*cos(y)   or   x**2 - y**2")
            new = input("z = ").strip()
            if new:
                expr = new

        elif choice == "3":
            clear()
            print("Presets:\n")
            for i, (name, eq) in enumerate(PRESETS, 1):
                print(f"  {i:2}. {name:<12} → {eq}")
            sel = input("\nChoose number: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(PRESETS):
                expr = PRESETS[int(sel)-1][1]

        elif choice == "4":
            try:
                val = float(input(f"New range (current ±{range_val}): "))
                if val > 0.2:
                    range_val = val
            except ValueError:
                pass

        elif choice == "5":
            try:
                print(f"Current yaw={yaw:.2f}, pitch={pitch:.2f}")
                yaw = float(input("New yaw   (e.g. 0.7): ") or yaw)
                pitch = float(input("New pitch (e.g. 0.5): ") or pitch)
            except ValueError:
                pass

        elif choice == "0":
            print("\nGoodbye!")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExited.")
