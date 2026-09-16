#!/usr/bin/env python3
"""
SharkDeck Network Suite
Pure Python (standard library only)
Author: for WalnutPi / SharkDeck
"""

import subprocess
import socket
import os
import sys
import time
import datetime
import ipaddress
import concurrent.futures
from urllib.request import urlopen
from urllib.error import URLError

# ====================== HELPERS ======================

def run(cmd, timeout=12):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

# ====================== CURRENT CONNECTION ======================

def get_current_info():
    info = {}
    info["ssid"] = run("nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2") or "Not connected"
    info["ip"] = run("hostname -I | awk '{print $1}'") or "N/A"
    info["gateway"] = run("ip route | grep default | awk '{print $3}'") or "N/A"
    info["interface"] = run("ip route | grep default | awk '{print $5}'") or "N/A"
    info["mac"] = run(f"cat /sys/class/net/{info['interface']}/address 2>/dev/null") or "N/A"
    info["dns"] = run("nmcli -t -f IP4.DNS device show 2>/dev/null | head -1 | cut -d: -f2") or \
                  run("grep nameserver /etc/resolv.conf | awk '{print $2}' | tr '\n' ' '") or "N/A"
    info["netmask"] = run(f"ip -o -f inet addr show {info['interface']} | awk '{{print $4}}'") or "N/A"
    return info

def show_current_connection():
    clear()
    header("CURRENT CONNECTION")
    info = get_current_info()
    print(f"  SSID           : {info['ssid']}")
    print(f"  IP Address     : {info['ip']}")
    print(f"  Netmask        : {info['netmask']}")
    print(f"  Gateway/Router : {info['gateway']}")
    print(f"  DNS            : {info['dns']}")
    print(f"  Interface      : {info['interface']}")
    print(f"  MAC Address    : {info['mac']}")
    pause()

# ====================== WIFI SCANNER ======================

def wifi_scan():
    clear()
    header("WIFI SCANNER")
    print("Scanning... (this may take a few seconds)\n")

    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,BARS,SECURITY device wifi list")

    networks = []
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 8:
            continue
        in_use, ssid, bssid, chan, freq, signal, bars, security = parts[:8]
        if not ssid:
            ssid = "<Hidden>"
        networks.append({
            "in_use": "*" if in_use == "*" else " ",
            "ssid": ssid,
            "bssid": bssid,
            "channel": chan,
            "freq": freq,
            "signal": int(signal) if signal.isdigit() else 0,
            "bars": bars,
            "security": security or "Open"
        })

    networks.sort(key=lambda x: x["signal"], reverse=True)

    print(f"{'':2} {'SSID':<26} {'Signal':<9} {'Ch':<5} {'Security':<14} {'BSSID (Router MAC)'}")
    print("-" * 85)
    for n in networks:
        print(f"{n['in_use']:2} {n['ssid']:<26} {n['signal']:>3}% {n['bars']:<4} {n['channel']:<5} {n['security']:<14} {n['bssid']}")

    print(f"\nFound {len(networks)} network(s)")
    pause()
    return networks

# ====================== DEVICE DISCOVERY ======================

def ping_host(ip):
    """Return True if host responds to ping"""
    result = run(f"ping -c 1 -W 1 {ip}", timeout=3)
    return "1 received" in result or "1 packets received" in result

def get_mac(ip):
    """Try to get MAC from ARP table"""
    return run(f"arp -n {ip} | awk '/{ip}/ {{print $3}}'") or "Unknown"

def discover_devices():
    clear()
    header("LOCAL NETWORK DEVICE DISCOVERY")

    info = get_current_info()
    if info["ip"] == "N/A" or info["netmask"] == "N/A":
        print("Not connected to a network.")
        pause()
        return

    try:
        network = ipaddress.IPv4Network(f"{info['ip']}/{info['netmask'].split('/')[-1]}", strict=False)
    except Exception:
        # Fallback: assume /24
        base = ".".join(info["ip"].split(".")[:3])
        network = ipaddress.IPv4Network(f"{base}.0/24", strict=False)

    print(f"Scanning network: {network}")
    print("This can take 20–60 seconds...\n")

    alive = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(ping_host, str(ip)): str(ip) for ip in network.hosts()}
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            if future.result():
                mac = get_mac(ip)
                alive.append((ip, mac))
                print(f"  [+] {ip:<16}  MAC: {mac}")

    print(f"\nFound {len(alive)} active device(s)")
    pause()
    return alive

# ====================== PORT SCANNER ======================

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS",
    445: "SMB", 3306: "MySQL", 3389: "RDP", 8080: "HTTP-Alt",
    8443: "HTTPS-Alt"
}

def scan_port(ip, port, timeout=0.8):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            return port if result == 0 else None
    except Exception:
        return None

def port_scanner():
    clear()
    header("PORT SCANNER")

    target = input("Enter target IP (or press Enter for gateway): ").strip()
    if not target:
        target = get_current_info()["gateway"]
        print(f"Using gateway: {target}")

    print(f"\nScanning common ports on {target}...\n")

    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(scan_port, target, port): port for port in COMMON_PORTS}
        for future in concurrent.futures.as_completed(futures):
            port = future.result()
            if port:
                service = COMMON_PORTS.get(port, "Unknown")
                print(f"  [OPEN] Port {port:<5} ({service})")
                open_ports.append((port, service))

    if not open_ports:
        print("  No common ports open (or host is filtered)")
    print(f"\nScan finished. {len(open_ports)} open port(s) found.")
    pause()

# ====================== PUBLIC IP ======================

def public_ip():
    clear()
    header("PUBLIC IP LOOKUP")
    print("Checking...")

    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com"
    ]

    for url in services:
        try:
            with urlopen(url, timeout=5) as resp:
                ip = resp.read().decode().strip()
                print(f"\n  Your Public IP : {ip}")
                print(f"  Source         : {url}")
                break
        except (URLError, Exception):
            continue
    else:
        print("\n  Could not determine public IP")

    pause()

# ====================== INTERFACE INFO ======================

def interface_info():
    clear()
    header("NETWORK INTERFACES")
    print(run("ip -br addr"))
    print("\n" + "-" * 40)
    print(run("ip route"))
    pause()

# ====================== FULL REPORT ======================

def full_report():
    clear()
    header("GENERATING FULL REPORT")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"network_report_{timestamp}.txt"

    current = get_current_info()
    networks = []
    devices = []

    print("1/3 Scanning WiFi...")
    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,BARS,SECURITY device wifi list")
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) >= 8:
            networks.append(parts)

    print("2/3 Discovering devices...")
    # Quick discovery of current /24
    if current["ip"] != "N/A":
        base = ".".join(current["ip"].split(".")[:3])
        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
            futures = {executor.submit(ping_host, f"{base}.{i}"): f"{base}.{i}" for i in range(1, 255)}
            for future in concurrent.futures.as_completed(futures):
                ip = futures[future]
                if future.result():
                    devices.append((ip, get_mac(ip)))

    print("3/3 Writing report...")

    with open(filename, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("  SharkDeck Full Network Report\n")
        f.write(f"  Generated: {datetime.datetime.now()}\n")
        f.write("=" * 70 + "\n\n")

        f.write("CURRENT CONNECTION\n")
        f.write("-" * 40 + "\n")
        for k, v in current.items():
            f.write(f"  {k:<12}: {v}\n")

        f.write("\nNEARBY WIFI NETWORKS\n")
        f.write("-" * 40 + "\n")
        for n in networks:
            f.write(f"  {'* ' if n[0]=='*' else '  '}{n[1]:<25} Ch:{n[3]:<4} Signal:{n[5]}%  {n[7]}  {n[2]}\n")

        f.write(f"\nACTIVE DEVICES ON LAN ({len(devices)})\n")
        f.write("-" * 40 + "\n")
        for ip, mac in sorted(devices):
            f.write(f"  {ip:<16}  {mac}\n")

        f.write("\n" + "=" * 70 + "\n")

    print(f"\nReport saved → {os.path.abspath(filename)}")
    pause()

# ====================== MAIN MENU ======================

def main_menu():
    while True:
        clear()
        header("SHARKDECK NETWORK SUITE")
        print("""
  1. Current Connection Info
  2. WiFi Scanner (nearby networks)
  3. Discover Devices on LAN
  4. Port Scanner
  5. Public IP Lookup
  6. Network Interfaces
  7. Generate Full Report
  0. Exit
        """)
        choice = input("Select option: ").strip()

        if choice == "1":
            show_current_connection()
        elif choice == "2":
            wifi_scan()
        elif choice == "3":
            discover_devices()
        elif choice == "4":
            port_scanner()
        elif choice == "5":
            public_ip()
        elif choice == "6":
            interface_info()
        elif choice == "7":
            full_report()
        elif choice == "0":
            print("\nGoodbye.")
            break
        else:
            print("Invalid choice")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Bye.")
        sys.exit(0)
