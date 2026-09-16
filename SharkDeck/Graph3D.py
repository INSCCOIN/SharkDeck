#!/usr/bin/env python3
# PILLOW REWRITE
# THIS TOOK 15 FUCKING HOURS

import math
import os
import sys
from math import sin, cos, sqrt, exp, log, log10, tan, pi, e, floor, ceil
from math import asin, acos, atan, atan2, sinh, cosh, tanh

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is not installed.")
    print("Run:  sudo apt install python3-pil")
    sys.exit(1)

# ====================== CONFIG ======================

WIDTH = 480
HEIGHT = 320
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
    ("Twin Peaks",    "1.4*(exp(-((x-2)**2+y**2)/2)+exp(-((x+2)**2+y**2)/2))"),
    ("Bowl",          "-0.1*(x**2 + y**2)"),
    ("Checker",       "0.5*sin(2*x)*sin(2*y)"),
    ("Volcano",       "1.2*exp(-(x**2+y**2)/4)-0.6*exp(-(x**2+y**2)/0.6)"),
]

# ====================== HELPERS ======================

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def clean_expr(expr):
    expr = (expr or "").strip().replace("^", "**")
    if expr.lower().startswith(("z=", "f=")):
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
        return None
    return None

def heat_color(t):
    """Height → color (blue → cyan → green → yellow → red)"""
    t = max(0.0, min(1.0, t))
    if t < 0.25:
        u = t / 0.25
        r, g, b = 0, int(100 + 155*u), 255
    elif t < 0.5:
        u = (t - 0.25) / 0.25
        r, g, b = 0, 255, int(255*(1-u))
    elif t < 0.75:
        u = (t - 0.5) / 0.25
        r, g, b = int(255*u), 255, 0
    else:
        u = (t - 0.75) / 0.25
        r, g, b = 255, int(255*(1-u)), 0
    return (r, g, b)

# ====================== RENDERER ======================

def render_surface(expr, range_val=4.0, grid_n=45, pitch=0.55, yaw=0.75):
    expr = clean_expr(expr)
    if not expr:
        raise ValueError("Empty expression")

    # Sample the surface
    zs = []
    zmin, zmax = 1e9, -1e9
    for j in range(grid_n):
        row = []
        y = -range_val + (2*range_val) * j / (grid_n-1)
        for i in range(grid_n):
            x = -range_val + (2*range_val) * i / (grid_n-1)
            z = evaluate(expr, x, y)
            row.append(z)
            if z is not None:
                zmin = min(zmin, z)
                zmax = max(zmax, z)
        zs.append(row)

    if zmax - zmin < 1e-9:
        zmax = zmin + 1.0

    # Create image
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 12, 28))
    draw = ImageDraw.Draw(img)

    # Projection settings
    cx, cy = WIDTH // 2, HEIGHT // 2 - 10
    focal = 220.0
    cam_dist = 9.0
    scale = 1.15

    def project(x, y, z):
        # Yaw
        cyaw, syaw = cos(yaw), sin(yaw)
        x1 = x * cyaw - y * syaw
        z1 = x * syaw + y * cyaw
        # Pitch
        cp, sp = cos(pitch), sin(pitch)
        y2 = z * cp - z1 * sp
        z2 = z * sp + z1 * cp

        zc = cam_dist - z2
        if zc < 0.4:
            return None
        s = (focal * scale) / zc
        sx = int(cx + x1 * s)
        sy = int(cy - y2 * s)
        return sx, sy, zc

    # Draw points with depth sorting (painter style)
    points = []
    for j in range(grid_n):
        for i in range(grid_n):
            z = zs[j][i]
            if z is None:
                continue
            x = -range_val + (2*range_val) * i / (grid_n-1)
            y = -range_val + (2*range_val) * j / (grid_n-1)
            p = project(x, y, z * 0.75)
            if p:
                sx, sy, depth = p
                t = (z - zmin) / (zmax - zmin)
                color = heat_color(t)
                points.append((depth, sx, sy, color))

    # Sort far → near
    points.sort(reverse=True)

    for depth, sx, sy, color in points:
        if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
            # Draw a small square for better visibility
            draw.rectangle([sx-1, sy-1, sx+1, sy+1], fill=color)

    # Title bar
    draw.rectangle([0, 0, WIDTH, 26], fill=(20, 24, 48))
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    title = f"z = {expr[:50]}"
    draw.text((8, 6), title, fill=(200, 220, 255), font=font)
    draw.text((8, HEIGHT-18), f"Range ±{range_val}   {grid_n}x{grid_n}", fill=(140, 160, 200), font=font)

    # Save
    filename = "graph3d_plot.png"
    img.save(filename)
    return filename

# ====================== MENU ======================

def main():
    expr = "0.6*sin(x)*cos(y)"
    range_val = 4.0
    grid_n = 42
    pitch = 0.55
    yaw = 0.75

    while True:
        clear()
        print("=" * 52)
        print("          Graph3D - SharkDeck (Pillow)")
        print("=" * 52)
        print(f"\n  Equation : z = {expr}")
        print(f"  Range    : ±{range_val}")
        print(f"  Grid     : {grid_n} × {grid_n}")
        print("""
  1. Plot (saves graph3d_plot.png)
  2. Enter new equation
  3. Presets
  4. Change range
  5. Change grid resolution
  6. Rotate view
  0. Exit
        """)
        choice = input("Select: ").strip()

        if choice == "1":
            try:
                print("\nRendering... please wait")
                fname = render_surface(expr, range_val, grid_n, pitch, yaw)
                print(f"Saved → {fname}")
                print("You can view it with any image viewer.")
            except Exception as e:
                print(f"Error: {e}")
            input("\nPress Enter...")

        elif choice == "2":
            print("\nEnter equation (use x and y)")
            new = input("z = ").strip()
            if new:
                expr = new

        elif choice == "3":
            clear()
            for i, (name, eq) in enumerate(PRESETS, 1):
                print(f"  {i:2}. {name:<12} → {eq}")
            sel = input("\nNumber: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(PRESETS):
                expr = PRESETS[int(sel)-1][1]

        elif choice == "4":
            try:
                val = float(input(f"New range (current ±{range_val}): "))
                if val > 0.3:
                    range_val = val
            except ValueError:
                pass

        elif choice == "5":
            try:
                val = int(input(f"Grid size 20-80 (current {grid_n}): "))
                if 20 <= val <= 80:
                    grid_n = val
            except ValueError:
                pass

        elif choice == "6":
            try:
                print(f"Current  yaw={yaw:.2f}  pitch={pitch:.2f}")
                yaw = float(input("yaw   : ") or yaw)
                pitch = float(input("pitch : ") or pitch)
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

