#!/usr/bin/env python3
"""
WiFi Network Scanner for SharkDeck / WalnutPi Zero (walnutOS)
Scans all available networks and saves detailed info to a .txt file.
"""

import subprocess
import datetime
import os
import sys

def run_cmd(cmd):
    """Run a shell command and return stdout as string."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def scan_networks():
    """Scan WiFi networks using nmcli and return structured data."""
    # Force a rescan first
    run_cmd("nmcli device wifi rescan")

    # Get detailed list (tab-separated for easy parsing)
    raw = run_cmd(
        "nmcli -t -f IN-USE,SSID,BSSID,MODE,CHAN,FREQ,RATE,SIGNAL,BARS,SECURITY "
        "device wifi list"
    )

    if not raw or raw.startswith("Error"):
        return None, raw

    networks = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 10:
            continue

        in_use, ssid, bssid, mode, chan, freq, rate, signal, bars, security = parts[:10]

        # Clean up empty SSIDs (hidden networks)
        if not ssid:
            ssid = "<Hidden Network>"

        networks.append({
            "in_use": "*" if in_use == "*" else " ",
            "ssid": ssid,
            "bssid": bssid,
            "mode": mode,
            "channel": chan,
            "frequency": freq,
            "rate": rate,
            "signal": int(signal) if signal.isdigit() else 0,
            "bars": bars,
            "security": security if security else "Open"
        })

    # Sort by signal strength (strongest first)
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks, None

def save_report(networks, filename):
    """Write a nice readable report to a text file."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  SharkDeck WiFi Network Scan Report\n")
        f.write(f"  Generated: {now}\n")
        f.write("=" * 70 + "\n\n")

        if not networks:
            f.write("No networks found.\n")
            return

        f.write(f"Found {len(networks)} network(s):\n\n")

        # Header
        f.write(f"{'In Use':<8} {'SSID':<32} {'Signal':<8} {'Ch':<5} "
                f"{'Freq':<10} {'Security':<18} {'BSSID'}\n")
        f.write("-" * 110 + "\n")

        for net in networks:
            f.write(
                f"{net['in_use']:<8} "
                f"{net['ssid']:<32} "
                f"{net['signal']:>3}% {net['bars']:<4} "
                f"{net['channel']:<5} "
                f"{net['frequency']:<10} "
                f"{net['security']:<18} "
                f"{net['bssid']}\n"
            )

        f.write("\n" + "=" * 70 + "\n")
        f.write("Legend:\n")
        f.write("  In Use   : * = currently connected\n")
        f.write("  Signal   : Higher % / more bars = stronger signal\n")
        f.write("  Security : Open / WPA2 / WPA3 / etc.\n")
        f.write("=" * 70 + "\n")

def main():
    print("Scanning for WiFi networks...")
    networks, error = scan_networks()

    if error:
        print("Scan failed:")
        print(error)
        print("\nMake sure NetworkManager is running and you have permission.")
        sys.exit(1)

    # Create filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"wifi_scan_{timestamp}.txt"

    # Save in current directory (or change to /home/pi/ or /sdcard/ if preferred)
    save_report(networks, filename)

    print(f"Scan complete! Found {len(networks)} network(s).")
    print(f"Report saved to: {os.path.abspath(filename)}")
    print()

    # Also print a short summary to the terminal
    print(f"{'SSID':<32} {'Signal':<8} {'Channel':<8} {'Security'}")
    print("-" * 70)
    for net in networks[:15]:  # show top 15
        print(f"{net['ssid']:<32} {net['signal']:>3}%     {net['channel']:<8} {net['security']}")
    if len(networks) > 15:
        print(f"... and {len(networks) - 15} more (see the .txt file)")

if __name__ == "__main__":
    main()
