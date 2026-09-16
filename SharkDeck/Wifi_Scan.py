#!/usr/bin/env python3
"""
WiFi Network Scanner for SharkDeck / WalnutPi Zero (walnutOS)
- Shows current connection info (IP + Router/Gateway)
- Scans all available networks
- Saves everything to a timestamped .txt file
"""

import subprocess
import datetime
import os
import sys
import socket

def run_cmd(cmd):
    """Run a shell command and return stdout as string."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def get_current_connection_info():
    """Get detailed info about the currently connected network."""
    info = {}

    # Current SSID
    info["ssid"] = run_cmd("nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2") or "Not connected"

    # IP Address
    info["ip"] = run_cmd("hostname -I | awk '{print $1}'") or "N/A"

    # Gateway / Router IP
    info["gateway"] = run_cmd("ip route | grep default | awk '{print $3}'") or "N/A"

    # DNS servers
    info["dns"] = run_cmd("nmcli -t -f IP4.DNS device show | head -1 | cut -d: -f2") or \
                  run_cmd("grep nameserver /etc/resolv.conf | awk '{print $2}' | tr '\n' ' '") or "N/A"

    # MAC address of the interface
    info["mac"] = run_cmd("cat /sys/class/net/$(ip route | grep default | awk '{print $5}')/address 2>/dev/null") or "N/A"

    # Interface name
    info["interface"] = run_cmd("ip route | grep default | awk '{print $5}'") or "N/A"

    return info

def scan_networks():
    """Scan WiFi networks using nmcli."""
    run_cmd("nmcli device wifi rescan >/dev/null 2>&1")

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

    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks, None

def save_report(current, networks, filename):
    """Write a detailed report to a text file."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 75 + "\n")
        f.write("  SharkDeck WiFi Network Scan Report\n")
        f.write(f"  Generated: {now}\n")
        f.write("=" * 75 + "\n\n")

        # === Current Connection ===
        f.write("CURRENT CONNECTION\n")
        f.write("-" * 40 + "\n")
        f.write(f"  SSID          : {current['ssid']}\n")
        f.write(f"  IP Address    : {current['ip']}\n")
        f.write(f"  Router/Gateway: {current['gateway']}\n")
        f.write(f"  DNS           : {current['dns']}\n")
        f.write(f"  Interface     : {current['interface']}\n")
        f.write(f"  MAC Address   : {current['mac']}\n")
        f.write("\n")

        # === Nearby Networks ===
        f.write("NEARBY NETWORKS\n")
        f.write("-" * 40 + "\n")

        if not networks:
            f.write("No networks found.\n")
        else:
            f.write(f"Found {len(networks)} network(s):\n\n")

            f.write(f"{'In Use':<8} {'SSID':<28} {'Signal':<9} {'Ch':<5} "
                    f"{'Freq':<10} {'Security':<16} {'BSSID (Router MAC)'}\n")
            f.write("-" * 110 + "\n")

            for net in networks:
                f.write(
                    f"{net['in_use']:<8} "
                    f"{net['ssid']:<28} "
                    f"{net['signal']:>3}% {net['bars']:<4} "
                    f"{net['channel']:<5} "
                    f"{net['frequency']:<10} "
                    f"{net['security']:<16} "
                    f"{net['bssid']}\n"
                )

        f.write("\n" + "=" * 75 + "\n")
        f.write("Notes:\n")
        f.write("  - IP Address & Router/Gateway only available for the network you are connected to.\n")
        f.write("  - BSSID = MAC address of the access point / router.\n")
        f.write("  - Signal: Higher % and more bars = stronger signal.\n")
        f.write("=" * 75 + "\n")

def main():
    print("Gathering current connection info...")
    current = get_current_connection_info()

    print("Scanning for nearby WiFi networks...")
    networks, error = scan_networks()

    if error:
        print("Scan failed:")
        print(error)
        sys.exit(1)

    # Create filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"wifi_scan_{timestamp}.txt"

    save_report(current, networks, filename)

    # === Print to screen ===
    print("\n" + "=" * 60)
    print("CURRENT CONNECTION")
    print("=" * 60)
    print(f"  SSID           : {current['ssid']}")
    print(f"  IP Address     : {current['ip']}")
    print(f"  Router/Gateway : {current['gateway']}")
    print(f"  DNS            : {current['dns']}")
    print(f"  Interface      : {current['interface']}")
    print(f"  MAC Address    : {current['mac']}")
    print()

    print("=" * 60)
    print(f"NEARBY NETWORKS ({len(networks)} found)")
    print("=" * 60)
    print(f"{'SSID':<28} {'Signal':<9} {'Ch':<5} {'Security':<14} {'BSSID'}")
    print("-" * 80)
    for net in networks[:12]:
        print(f"{net['ssid']:<28} {net['signal']:>3}% {net['bars']:<4} {net['channel']:<5} {net['security']:<14} {net['bssid']}")
    if len(networks) > 12:
        print(f"... and {len(networks) - 12} more (see the .txt file)")

    print(f"\nFull report saved to: {os.path.abspath(filename)}")

if __name__ == "__main__":
    main()
