#!/usr/bin/env python3
"""
WiFi Security Auditor + Rogue AP Detector
For SharkDeck / WalnutPi (white-hat / defensive use only)
"""

import subprocess
import os
import sys
import json
import datetime
from collections import defaultdict

# ====================== CONFIG ======================

TRUSTED_FILE = "trusted_networks.json"
REPORT_DIR = "wifi_reports"

# ====================== HELPERS ======================

def run(cmd, timeout=15):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return ""

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)

def load_trusted():
    if os.path.exists(TRUSTED_FILE):
        try:
            with open(TRUSTED_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_trusted(data):
    with open(TRUSTED_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ====================== WIFI SCAN ======================

def scan_wifi():
    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,BARS,SECURITY,RSN-FLAGS device wifi list")

    networks = []
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 8:
            continue

        in_use = parts[0] == "*"
        ssid = parts[1] if parts[1] else "<Hidden>"
        bssid = parts[2].upper()
        channel = parts[3]
        freq = parts[4]
        signal = int(parts[5]) if parts[5].isdigit() else 0
        bars = parts[6]
        security = parts[7] if parts[7] else "Open"
        rsn_flags = parts[8] if len(parts) > 8 else ""

        networks.append({
            "in_use": in_use,
            "ssid": ssid,
            "bssid": bssid,
            "channel": channel,
            "freq": freq,
            "signal": signal,
            "bars": bars,
            "security": security,
            "rsn_flags": rsn_flags
        })

    # Sort by signal strength
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks

# ====================== SECURITY RATING ======================

def rate_security(net):
    """
    Returns (score 0-100, rating text, issues list, color hint)
    """
    sec = net["security"].upper()
    rsn = net["rsn_flags"].upper()
    issues = []
    score = 100

    # Open network
    if "OPEN" in sec or sec == "--" or sec == "":
        score = 0
        issues.append("Open network (no encryption)")
        return score, "CRITICAL", issues

    # WEP
    if "WEP" in sec:
        score = 5
        issues.append("Uses WEP (completely broken)")
        return score, "CRITICAL", issues

    # WPA (original)
    if "WPA1" in sec or ("WPA" in sec and "WPA2" not in sec and "WPA3" not in sec):
        score -= 45
        issues.append("Uses original WPA (outdated)")

    # TKIP
    if "TKIP" in sec:
        score -= 30
        issues.append("Uses TKIP (weak cipher)")

    # WPA2 only (still acceptable but not best)
    if "WPA2" in sec and "WPA3" not in sec:
        score -= 10
        issues.append("WPA2 only (consider WPA3)")

    # No Management Frame Protection (PMF / 802.11w)
    if "WPA2" in sec or "WPA3" in sec:
        if "MFPR" not in rsn and "MFPC" not in rsn:
            score -= 15
            issues.append("No Protected Management Frames (PMF)")

    # WPA3 is best
    if "WPA3" in sec:
        score += 5  # small bonus
        if score > 100:
            score = 100

    # Final rating
    if score >= 90:
        rating = "EXCELLENT"
    elif score >= 75:
        rating = "GOOD"
    elif score >= 50:
        rating = "FAIR"
    elif score >= 25:
        rating = "POOR"
    else:
        rating = "CRITICAL"

    return score, rating, issues

# ====================== ROGUE / EVIL TWIN DETECTION ======================

def detect_rogues(networks, trusted):
    """
    Detect possible rogue / evil twin access points
    """
    ssid_map = defaultdict(list)
    for net in networks:
        if net["ssid"] != "<Hidden>":
            ssid_map[net["ssid"]].append(net)

    findings = []

    for ssid, aps in ssid_map.items():
        if len(aps) < 2:
            continue

        # Multiple BSSIDs for same SSID
        bssids = set(ap["bssid"] for ap in aps)
        if len(bssids) > 1:
            # Check against trusted
            trusted_bssids = set()
            if ssid in trusted:
                trusted_bssids = set(trusted[ssid])

            unknown = [ap for ap in aps if ap["bssid"] not in trusted_bssids]

            if unknown:
                findings.append({
                    "type": "Multiple BSSIDs",
                    "ssid": ssid,
                    "count": len(bssids),
                    "aps": aps,
                    "unknown": unknown,
                    "severity": "HIGH" if not trusted_bssids else "MEDIUM"
                })

        # Signal anomaly (very strong signal claiming to be far network - basic heuristic)
        signals = [ap["signal"] for ap in aps]
        if max(signals) - min(signals) > 45 and len(aps) >= 2:
            findings.append({
                "type": "Signal Anomaly",
                "ssid": ssid,
                "aps": aps,
                "severity": "MEDIUM"
            })

    return findings

# ====================== MAIN AUDIT ======================

def run_audit():
    clear()
    header("WIFI SECURITY AUDIT + ROGUE AP DETECTOR")
    print("Scanning networks...\n")

    networks = scan_wifi()
    trusted = load_trusted()

    if not networks:
        print("No networks found.")
        pause()
        return

    print(f"{'SSID':<22} {'Signal':<8} {'Security':<18} {'Score':<7} {'Rating'}")
    print("-" * 75)

    results = []
    for net in networks:
        score, rating, issues = rate_security(net)
        results.append({**net, "score": score, "rating": rating, "issues": issues})

        marker = "►" if net["in_use"] else " "
        print(f"{marker} {net['ssid']:<20} {net['signal']:>3}% {net['bars']:<4} "
              f"{net['security']:<18} {score:<7} {rating}")

    # Rogue detection
    print("\n")
    header("ROGUE / EVIL TWIN DETECTION")
    rogues = detect_rogues(networks, trusted)

    if not rogues:
        print("No obvious rogue / evil twin indicators found.")
    else:
        for r in rogues:
            print(f"\n[{r['severity']}] {r['type']} detected for SSID: {r['ssid']}")
            for ap in r["aps"]:
                trusted_flag = " (TRUSTED)" if r["ssid"] in trusted and ap["bssid"] in trusted.get(r["ssid"], []) else ""
                print(f"   BSSID: {ap['bssid']}  Signal: {ap['signal']}%  Ch: {ap['channel']}{trusted_flag}")

    # Summary of weak networks
    print("\n")
    header("WEAK / RISKY NETWORKS")
    weak = [r for r in results if r["score"] < 60]
    if not weak:
        print("No critically weak networks detected.")
    else:
        for w in weak:
            print(f"\n  {w['ssid']}  ({w['rating']} - Score {w['score']})")
            for issue in w["issues"]:
                print(f"     - {issue}")

    pause()
    return results, rogues

# ====================== TRUSTED NETWORKS MANAGEMENT ======================

def manage_trusted():
    while True:
        clear()
        header("TRUSTED NETWORKS (Whitelist)")
        trusted = load_trusted()

        if not trusted:
            print("No trusted networks saved yet.\n")
        else:
            for ssid, bssids in trusted.items():
                print(f"  {ssid}")
                for b in bssids:
                    print(f"     └─ {b}")
                print()

        print("1. Add trusted network")
        print("2. Remove trusted network")
        print("3. Back")
        choice = input("\nChoice: ").strip()

        if choice == "1":
            ssid = input("SSID: ").strip()
            bssid = input("BSSID (MAC): ").strip().upper()
            if ssid and bssid:
                if ssid not in trusted:
                    trusted[ssid] = []
                if bssid not in trusted[ssid]:
                    trusted[ssid].append(bssid)
                    save_trusted(trusted)
                    print("Added.")
                else:
                    print("Already trusted.")
            pause()

        elif choice == "2":
            ssid = input("SSID to remove: ").strip()
            if ssid in trusted:
                del trusted[ssid]
                save_trusted(trusted)
                print("Removed.")
            else:
                print("Not found.")
            pause()

        elif choice == "3":
            break

# ====================== REPORT ======================

def save_report(results, rogues):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(REPORT_DIR, f"wifi_audit_{ts}.txt")

    with open(filename, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("  WiFi Security Audit Report\n")
        f.write(f"  Generated: {datetime.datetime.now()}\n")
        f.write("=" * 70 + "\n\n")

        f.write("NETWORKS\n" + "-" * 40 + "\n")
        for r in results:
            f.write(f"{r['ssid']:<22} Signal:{r['signal']}%  {r['security']:<18} "
                    f"Score:{r['score']} ({r['rating']})\n")
            f.write(f"   BSSID: {r['bssid']}  Channel: {r['channel']}\n")
            if r["issues"]:
                for issue in r["issues"]:
                    f.write(f"   ! {issue}\n")
            f.write("\n")

        f.write("\nROGUE / EVIL TWIN FINDINGS\n" + "-" * 40 + "\n")
        if not rogues:
            f.write("None detected.\n")
        else:
            for r in rogues:
                f.write(f"[{r['severity']}] {r['type']} - SSID: {r['ssid']}\n")
                for ap in r["aps"]:
                    f.write(f"   {ap['bssid']}  Signal:{ap['signal']}%  Ch:{ap['channel']}\n")
                f.write("\n")

    print(f"\nReport saved → {filename}")
    pause()

# ====================== MAIN MENU ======================

def main():
    while True:
        clear()
        header("WiFi Security Auditor + Rogue AP Detector")
        print("""
  1. Run Full Audit
  2. Manage Trusted Networks (Whitelist)
  3. Exit
        """)
        choice = input("Select: ").strip()

        if choice == "1":
            results, rogues = run_audit()
            save = input("\nSave report? [y/N]: ").strip().lower()
            if save == "y":
                save_report(results, rogues)

        elif choice == "2":
            manage_trusted()

        elif choice == "3":
            print("\nStay safe.")
            break

        else:
            print("Invalid choice")
            time.sleep(0.8)

if __name__ == "__main__":
    try:
        import time
        main()
    except KeyboardInterrupt:
        print("\n\nExiting.")
        sys.exit(0)
