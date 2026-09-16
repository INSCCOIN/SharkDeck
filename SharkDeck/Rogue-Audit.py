#!/usr/bin/env python3
"""
WiFi Security Auditor + Rogue AP Detector - Advanced Edition
SharkDeck / WalnutPi - White-hat / Defensive use only
"""

import subprocess
import os
import sys
import json
import csv
import time
import datetime
from collections import defaultdict
from pathlib import Path

# ====================== PATHS ======================
BASE_DIR = Path("wifi_auditor_data")
TRUSTED_FILE = BASE_DIR / "trusted_profiles.json"
HISTORY_FILE = BASE_DIR / "history.json"
LOG_FILE = BASE_DIR / "audit.log"
REPORT_DIR = BASE_DIR / "reports"

for d in [BASE_DIR, REPORT_DIR]:
    d.mkdir(exist_ok=True)

# ====================== HELPERS ======================

def run(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 66)
    print(f"  {title}")
    print("=" * 66)

def log_event(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

def load_json(path, default=None):
    if default is None:
        default = {}
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ====================== DATA MANAGEMENT ======================

def load_trusted():
    return load_json(TRUSTED_FILE, {})

def save_trusted(data):
    save_json(TRUSTED_FILE, data)

def load_history():
    return load_json(HISTORY_FILE, {})

def save_history(data):
    save_json(HISTORY_FILE, data)

# ====================== WIFI SCAN ======================

def scan_wifi():
    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,BARS,SECURITY,RSN-FLAGS device wifi list")

    networks = []
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 8:
            continue

        networks.append({
            "in_use": parts[0] == "*",
            "ssid": parts[1] if parts[1] else "<Hidden>",
            "bssid": parts[2].upper(),
            "channel": parts[3],
            "freq": parts[4],
            "signal": int(parts[5]) if parts[5].isdigit() else 0,
            "bars": parts[6],
            "security": parts[7] if parts[7] else "Open",
            "rsn_flags": parts[8] if len(parts) > 8 else ""
        })

    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks

# ====================== SECURITY SCORING ======================

def rate_security(net):
    sec = net["security"].upper()
    rsn = net.get("rsn_flags", "").upper()
    issues = []
    score = 100

    if "OPEN" in sec or sec in ("--", "", "NONE"):
        return 0, "CRITICAL", ["Open network - no encryption"]

    if "WEP" in sec:
        return 5, "CRITICAL", ["Uses WEP (broken encryption)"]

    if "WPA1" in sec or ("WPA " in sec and "WPA2" not in sec and "WPA3" not in sec):
        score -= 40
        issues.append("Uses original WPA (outdated)")

    if "TKIP" in sec:
        score -= 25
        issues.append("Uses TKIP (weak cipher)")

    if "WPA2" in sec and "WPA3" not in sec:
        score -= 8
        issues.append("WPA2 only (WPA3 recommended)")

    # Protected Management Frames
    if "WPA2" in sec or "WPA3" in sec:
        if "MFPR" not in rsn and "MFPC" not in rsn:
            score -= 12
            issues.append("No Protected Management Frames (PMF)")

    if "WPA3" in sec:
        score = min(100, score + 5)

    if score >= 90:
        rating = "EXCELLENT"
    elif score >= 75:
        rating = "GOOD"
    elif score >= 55:
        rating = "FAIR"
    elif score >= 30:
        rating = "POOR"
    else:
        rating = "CRITICAL"

    return max(0, score), rating, issues

# ====================== ROGUE / EVIL TWIN DETECTION ======================

def detect_rogues(networks, trusted):
    ssid_groups = defaultdict(list)
    for net in networks:
        if net["ssid"] != "<Hidden>":
            ssid_groups[net["ssid"]].append(net)

    findings = []

    for ssid, aps in ssid_groups.items():
        if len(aps) < 2:
            continue

        bssids = {ap["bssid"] for ap in aps}
        trusted_bssids = set(trusted.get(ssid, {}).get("bssids", []))

        # Multiple BSSIDs
        if len(bssids) > 1:
            unknown = [ap for ap in aps if ap["bssid"] not in trusted_bssids]
            if unknown:
                findings.append({
                    "type": "Multiple BSSIDs (Possible Evil Twin)",
                    "ssid": ssid,
                    "severity": "HIGH" if not trusted_bssids else "MEDIUM",
                    "aps": aps,
                    "unknown": unknown
                })

        # Different security types for same SSID
        securities = {ap["security"] for ap in aps}
        if len(securities) > 1:
            findings.append({
                "type": "Mixed Security Types",
                "ssid": ssid,
                "severity": "HIGH",
                "aps": aps,
                "details": list(securities)
            })

        # Large signal difference
        signals = [ap["signal"] for ap in aps]
        if max(signals) - min(signals) >= 40:
            findings.append({
                "type": "Large Signal Difference",
                "ssid": ssid,
                "severity": "MEDIUM",
                "aps": aps
            })

    return findings

# ====================== HISTORY ======================

def update_history(networks):
    history = load_history()
    now = datetime.datetime.now().isoformat()

    for net in networks:
        key = f"{net['ssid']}|{net['bssid']}"
        if key not in history:
            history[key] = {
                "ssid": net["ssid"],
                "bssid": net["bssid"],
                "first_seen": now,
                "last_seen": now,
                "security": net["security"],
                "times_seen": 1
            }
        else:
            history[key]["last_seen"] = now
            history[key]["times_seen"] += 1
            history[key]["security"] = net["security"]

    save_history(history)
    return history

# ====================== FULL AUDIT ======================

def run_full_audit(show_all=True):
    clear()
    header("FULL WIFI SECURITY AUDIT")
    print("Scanning...\n")

    networks = scan_wifi()
    trusted = load_trusted()
    history = update_history(networks)

    if not networks:
        print("No networks found.")
        pause()
        return None, None

    results = []
    for net in networks:
        score, rating, issues = rate_security(net)
        results.append({**net, "score": score, "rating": rating, "issues": issues})

    # Summary
    critical = sum(1 for r in results if r["rating"] == "CRITICAL")
    poor = sum(1 for r in results if r["rating"] == "POOR")
    fair = sum(1 for r in results if r["rating"] == "FAIR")
    good = sum(1 for r in results if r["rating"] in ("GOOD", "EXCELLENT"))

    print(f"Summary: {critical} Critical | {poor} Poor | {fair} Fair | {good} Good/Excellent")
    print("-" * 66)

    if show_all:
        print(f"{'':1}{'SSID':<20} {'Sig':<7} {'Security':<16} {'Score':<6} Rating")
        print("-" * 66)
        for r in results:
            mark = "►" if r["in_use"] else " "
            print(f"{mark}{r['ssid']:<20} {r['signal']:>3}% {r['bars']:<3} {r['security']:<16} "
                  f"{r['score']:<6} {r['rating']}")

    # Rogue detection
    print("\n")
    header("ROGUE / EVIL TWIN DETECTION")
    rogues = detect_rogues(networks, trusted)

    if not rogues:
        print("No strong rogue/evil twin indicators found.")
    else:
        for r in rogues:
            print(f"\n[{r['severity']}] {r['type']}")
            print(f"   SSID: {r['ssid']}")
            for ap in r["aps"]:
                trusted_flag = " [TRUSTED]" if ap["bssid"] in trusted.get(r["ssid"], {}).get("bssids", []) else ""
                print(f"   • {ap['bssid']}  {ap['signal']}%  Ch{ap['channel']}  {ap['security']}{trusted_flag}")
            log_event(f"ROGUE DETECTED: {r['type']} on {r['ssid']}")

    # Weak networks
    weak = [r for r in results if r["score"] < 55]
    if weak:
        print("\n")
        header("WEAK / RISKY NETWORKS")
        for w in weak:
            print(f"\n{w['ssid']}  →  {w['rating']} ({w['score']})")
            for issue in w["issues"]:
                print(f"   - {issue}")

    return results, rogues

# ====================== CONTINUOUS MONITOR ======================

def continuous_monitor():
    clear()
    header("CONTINUOUS MONITORING MODE")
    print("Scanning every 20 seconds. Ctrl+C to stop.\n")
    print("Alerts will appear when new risks or rogues are detected.\n")

    known_bssids = set()
    trusted = load_trusted()

    try:
        while True:
            networks = scan_wifi()
            update_history(networks)
            rogues = detect_rogues(networks, trusted)

            current_bssids = {n["bssid"] for n in networks}
            new_bssids = current_bssids - known_bssids

            timestamp = datetime.datetime.now().strftime("%H:%M:%S")

            if new_bssids:
                print(f"[{timestamp}] New BSSID(s) detected: {len(new_bssids)}")
                for n in networks:
                    if n["bssid"] in new_bssids:
                        score, rating, _ = rate_security(n)
                        print(f"   + {n['ssid']:<18} {n['bssid']}  {rating}")
                        if rating in ("CRITICAL", "POOR"):
                            log_event(f"NEW RISKY NETWORK: {n['ssid']} ({n['bssid']}) - {rating}")

            if rogues:
                print(f"[{timestamp}] !!! ROGUE INDICATOR DETECTED !!!")
                for r in rogues:
                    print(f"   → {r['type']} on {r['ssid']}")
                    log_event(f"MONITOR ALERT: {r['type']} - {r['ssid']}")

            known_bssids.update(current_bssids)
            time.sleep(20)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        pause()

# ====================== CHANNEL ANALYZER ======================

def channel_analyzer():
    clear()
    header("CHANNEL CONGESTION + SECURITY")
    networks = scan_wifi()

    channels = defaultdict(list)
    for n in networks:
        try:
            ch = int(n["channel"])
            score, rating, _ = rate_security(n)
            channels[ch].append({**n, "score": score, "rating": rating})
        except ValueError:
            continue

    print(f"{'Ch':<5} {'Count':<7} {'Worst':<10} {'Networks'}")
    print("-" * 70)

    for ch in sorted(channels.keys()):
        nets = channels[ch]
        worst = min(n["score"] for n in nets)
        worst_rating = next(n["rating"] for n in nets if n["score"] == worst)
        names = ", ".join(n["ssid"][:10] for n in nets[:3])
        if len(nets) > 3:
            names += f" +{len(nets)-3}"
        print(f"{ch:<5} {len(nets):<7} {worst_rating:<10} {names}")

    pause()

# ====================== TRUSTED PROFILES ======================

def manage_trusted():
    while True:
        clear()
        header("TRUSTED NETWORK PROFILES")
        trusted = load_trusted()

        if not trusted:
            print("No trusted profiles yet.\n")
        else:
            for ssid, data in trusted.items():
                print(f"  {ssid}")
                print(f"     Security : {data.get('security', '?')}")
                print(f"     BSSIDs   : {', '.join(data.get('bssids', []))}")
                print()

        print("1. Add / Update trusted network")
        print("2. Remove trusted network")
        print("3. Mark currently connected as trusted")
        print("4. Back")
        choice = input("\nChoice: ").strip()

        if choice == "1":
            ssid = input("SSID: ").strip()
            bssid = input("BSSID: ").strip().upper()
            security = input("Security (e.g. WPA2): ").strip()
            if ssid and bssid:
                if ssid not in trusted:
                    trusted[ssid] = {"bssids": [], "security": security}
                if bssid not in trusted[ssid]["bssids"]:
                    trusted[ssid]["bssids"].append(bssid)
                trusted[ssid]["security"] = security or trusted[ssid].get("security", "")
                save_trusted(trusted)
                print("Saved.")
            pause()

        elif choice == "2":
            ssid = input("SSID to remove: ").strip()
            if ssid in trusted:
                del trusted[ssid]
                save_trusted(trusted)
                print("Removed.")
            pause()

        elif choice == "3":
            networks = scan_wifi()
            current = next((n for n in networks if n["in_use"]), None)
            if current:
                trusted[current["ssid"]] = {
                    "bssids": [current["bssid"]],
                    "security": current["security"]
                }
                save_trusted(trusted)
                print(f"Marked '{current['ssid']}' as trusted.")
            else:
                print("Not connected to any network.")
            pause()

        elif choice == "4":
            break

# ====================== REPORTS ======================

def save_reports(results, rogues):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # TXT
    txt_path = REPORT_DIR / f"audit_{ts}.txt"
    with open(txt_path, "w") as f:
        f.write(f"WiFi Security Audit - {datetime.datetime.now()}\n{'='*60}\n\n")
        for r in results:
            f.write(f"{r['ssid']:<22} {r['signal']}%  {r['security']:<16} {r['score']} ({r['rating']})\n")
            f.write(f"   BSSID: {r['bssid']}  Channel: {r['channel']}\n")
            for issue in r["issues"]:
                f.write(f"   ! {issue}\n")
            f.write("\n")
        f.write("\nROGUE FINDINGS\n" + "-"*40 + "\n")
        if not rogues:
            f.write("None\n")
        else:
            for r in rogues:
                f.write(f"[{r['severity']}] {r['type']} - {r['ssid']}\n")

    # JSON
    json_path = REPORT_DIR / f"audit_{ts}.json"
    save_json(json_path, {"results": results, "rogues": rogues})

    # CSV
    csv_path = REPORT_DIR / f"networks_{ts}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ssid", "bssid", "signal", "channel", "security", "score", "rating"])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in writer.fieldnames})

    print(f"\nReports saved in {REPORT_DIR}/")
    print(f"  • {txt_path.name}")
    print(f"  • {json_path.name}")
    print(f"  • {csv_path.name}")
    pause()

# ====================== MAIN MENU ======================

def main_menu():
    while True:
        clear()
        header("WiFi Security Auditor + Rogue Detector")
        print("""
  1. Run Full Audit
  2. Continuous Monitoring Mode
  3. Channel Congestion + Security View
  4. Manage Trusted Profiles
  5. Show Audit Log
  6. Exit
        """)
        choice = input("Select: ").strip()

        if choice == "1":
            results, rogues = run_full_audit()
            if results:
                if input("\nSave reports? [y/N]: ").strip().lower() == "y":
                    save_reports(results, rogues)

        elif choice == "2":
            continuous_monitor()

        elif choice == "3":
            channel_analyzer()

        elif choice == "4":
            manage_trusted()

        elif choice == "5":
            clear()
            header("AUDIT LOG")
            if LOG_FILE.exists():
                print(LOG_FILE.read_text()[-3000:] or "Log is empty.")
            else:
                print("No log yet.")
            pause()

        elif choice == "6":
            print("\nStay safe out there.")
            break

        else:
            print("Invalid choice")
            time.sleep(0.7)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nExiting.")
        sys.exit(0)
