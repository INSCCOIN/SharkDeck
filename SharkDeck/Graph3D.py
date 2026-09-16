#!/usr/bin/env python3
"""
Graph3D - 3D Graphing Calculator for SharkDeck
Port of Picoware Graph3D.py (z = f(x, y))
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import math
import os

# ====================== SAFE MATH ENVIRONMENT ======================

SAFE = {
    "abs": abs, "min": min, "max": max, "pow": pow, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "log": math.log, "log10": math.log10, "exp": math.exp, "sqrt": math.sqrt,
    "pi": math.pi, "e": math.e, "floor": math.floor, "ceil": math.ceil,
    "math": math,
}

PRESETS = [
    ("Wave",          "0.6*sin(x)*cos(y)"),
    ("Paraboloid",    "0.12*(x**2 + y**2)"),
    ("Saddle",        "0.12*(x**2 - y**2)"),
    ("Ripple",        "sin(sqrt(x**2 + y**2))"),
    ("Sombrero",      "sin(sqrt(x**2+y**2)+0.001)/(sqrt(x**2+y**2)+0.4)"),
    ("Hyperbolic",    "0.18*x*y"),
    ("Gaussian",      "1.6*exp(-(x**2+y**2)/3)"),
    ("Twin Peaks",    "1.4*(exp(-((x-2)**2+y**2)/2) + exp(-((x+2)**2+y**2)/2))"),
    ("Bowl",          "-0.1*(x**2 + y**2)"),
    ("Checker",       "0.5*sin(2*x)*sin(2*y)"),
    ("Helix Bowl",    "0.15*(x**2+y**2) + 0.4*sin(3*atan2(y,x))"),
    ("Volcano",       "1.2*exp(-(x**2+y**2)/4) - 0.6*exp(-(x**2+y**2)/0.6)"),
]

# ====================== CORE ======================

def clean_expr(expr: str) -> str:
    expr = (expr or "").strip()
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
    low = expr.lower()
    if low.startswith("z=") or low.startswith("f="):
        expr = expr[2:]
    return expr.strip()

def evaluate_surface(expr: str, range_val: float = 4.0, grid_n: int = 40):
    expr = clean_expr(expr)
    if not expr:
        raise ValueError("Empty expression")

    try:
        code = compile(expr, "<expr>", "eval")
    except Exception as e:
        raise ValueError(f"Syntax error: {e}")

    x = np.linspace(-range_val, range_val, grid_n)
    y = np.linspace(-range_val, range_val, grid_n)
    X, Y = np.meshgrid(x, y)
    Z = np.zeros_like(X)

    env = dict(SAFE)
    for i in range(grid_n):
        for j in range(grid_n):
            env["x"] = float(X[i, j])
            env["y"] = float(Y[i, j])
            env["r"] = math.sqrt(env["x"]**2 + env["y"]**2)
            try:
                val = eval(code, {"__builtins__": {}}, env)
                if isinstance(val, (int, float)) and math.isfinite(val):
                    Z[i, j] = val
                else:
                    Z[i, j] = np.nan
            except Exception:
                Z[i, j] = np.nan

    return X, Y, Z

def plot_surface(expr1: str, expr2: str = "", range_val: float = 4.0, grid_n: int = 40):
    X, Y, Z1 = evaluate_surface(expr1, range_val, grid_n)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")

    # Main surface
    surf1 = ax.plot_surface(X, Y, Z1, cmap="viridis", edgecolor="none", alpha=0.9, label="f(x,y)")

    # Optional second surface
    if clean_expr(expr2):
        try:
            _, _, Z2 = evaluate_surface(expr2, range_val, grid_n)
            ax.plot_surface(X, Y, Z2, cmap="plasma", edgecolor="none", alpha=0.6)
        except Exception as e:
            print(f"Second equation error: {e}")

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.set_title(f"z = {clean_expr(expr1)}" + (f"  |  g = {clean_expr(expr2)}" if clean_expr(expr2) else ""))

    # Nice defaults
    ax.view_init(elev=28, azim=-60)
    fig.colorbar(surf1, ax=ax, shrink=0.6, label="Height")

    plt.tight_layout()
    plt.show()

# ====================== MENU ======================

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def main_menu():
    expr1 = "0.6*sin(x)*cos(y)"
    expr2 = ""
    range_val = 4.0
    grid_n = 40

    while True:
        clear()
        print("=" * 55)
        print("          Graph3D - SharkDeck Edition")
        print("     3D Surface Plotter  (z = f(x, y))")
        print("=" * 55)
        print(f"\n  Current f(x,y) : {expr1}")
        print(f"  Current g(x,y) : {expr2 or '(none)'}")
        print(f"  Range         : ±{range_val}")
        print(f"  Grid size     : {grid_n} × {grid_n}")
        print("""
  1. Plot current equation(s)
  2. Enter / edit f(x,y)
  3. Enter / edit g(x,y)   (optional second surface)
  4. Presets
  5. Change range
  6. Change grid resolution
  7. Help
  0. Exit
        """)
        choice = input("Select: ").strip()

        if choice == "1":
            try:
                print("\nGenerating 3D plot...")
                plot_surface(expr1, expr2, range_val, grid_n)
            except Exception as e:
                print(f"\nError: {e}")
                input("\nPress Enter...")

        elif choice == "2":
            print("\nEnter equation for z = f(x, y)")
            print("Examples: sin(x)*cos(y)   |   x**2 - y**2   |   exp(-(x**2+y**2))")
            new = input("f(x,y) = ").strip()
            if new:
                expr1 = new

        elif choice == "3":
            print("\nOptional second surface g(x, y)  (leave empty to clear)")
            new = input("g(x,y) = ").strip()
            expr2 = new

        elif choice == "4":
            clear()
            print("Presets:\n")
            for i, (name, eq) in enumerate(PRESETS, 1):
                print(f"  {i:2}. {name:<15} → {eq}")
            print()
            sel = input("Choose preset number (or Enter to cancel): ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(PRESETS):
                expr1 = PRESETS[int(sel)-1][1]
                expr2 = ""

        elif choice == "5":
            try:
                val = float(input(f"New range (current ±{range_val}): ").strip())
                if val > 0.1:
                    range_val = val
            except ValueError:
                pass

        elif choice == "6":
            try:
                val = int(input(f"Grid size (current {grid_n}): ").strip())
                if 8 <= val <= 120:
                    grid_n = val
            except ValueError:
                pass

        elif choice == "7":
            clear()
            print("""
Graph3D Help
------------
• Write any expression using x and y
• Available functions:
  sin cos tan asin acos atan atan2
  sinh cosh tanh
  log log10 exp sqrt abs floor ceil
  pi  e

• Use ** for powers   (x**2)
• You can plot two surfaces at once (f and g)

• In the plot window:
  - Left mouse  = rotate
  - Right mouse = zoom
  - Middle      = pan
            """)
            input("\nPress Enter to return...")

        elif choice == "0":
            print("\nGoodbye!")
            break

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nExiting.")
