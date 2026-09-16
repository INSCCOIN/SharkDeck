#!/usr/bin/env python3
"""
SharkDeck Network Suite - Expanded Edition
Pure Python (standard library only)
"""

import subprocess
import socket
import os
import sys
import time
import datetime
import ipaddress
import concurrent.futures
import json
import re
from urllib.request import urlopen, Request
from urllib.error import URLError

# ====================== COMMON VENDORS (partial OUI) ======================
OUI_VENDORS = {
    "00:50:56": "VMware",
    "00:0C:29": "VMware",
    "00:1A:11": "Google",
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    "28:CD:C1": "Raspberry Pi",
    "00:1E:06": "Wahoo Fitness",
    "F0:18:98": "Apple",
    "3C:22:FB": "Apple",
    "A4:83:E7": "Apple",
    "AC:DE:48": "Apple",
    "00:1B:63": "Apple",
    "00:25:00": "Apple",
    "00:26:4A": "Apple",
    "00:26:B0": "Apple",
    "00:26:BB": "Apple",
    "00:50:F2": "Microsoft",
    "00:15:5D": "Microsoft",
    "00:03:FF": "Microsoft",
    "00:12:5A": "Microsoft",
    "00:17:FA": "Microsoft",
    "00:1D:D8": "Microsoft",
    "00:50:F2": "Microsoft",
    "00:0D:3A": "Microsoft",
    "00:1E:8C": "ASUSTek",
    "00:22:15": "ASUSTek",
    "00:23:54": "ASUSTek",
    "00:24:8C": "ASUSTek",
    "00:25:22": "ASUSTek",
    "00:26:18": "ASUSTek",
    "04:92:26": "ASUSTek",
    "08:60:6E": "ASUSTek",
    "1C:87:2C": "ASUSTek",
    "2C:4D:54": "ASUSTek",
    "2C:56:DC": "ASUSTek",
    "30:85:A9": "ASUSTek",
    "34:97:F6": "ASUSTek",
    "38:D5:47": "ASUSTek",
    "40:B0:76": "ASUSTek",
    "50:46:5D": "ASUSTek",
    "54:04:A6": "ASUSTek",
    "60:45:CB": "ASUSTek",
    "70:4D:7B": "ASUSTek",
    "74:D0:2B": "ASUSTek",
    "78:24:AF": "ASUSTek",
    "88:D7:F6": "ASUSTek",
    "9C:5C:8E": "ASUSTek",
    "AC:22:0B": "ASUSTek",
    "B0:6E:BF": "ASUSTek",
    "BC:EE:7B": "ASUSTek",
    "C8:60:00": "ASUSTek",
    "D0:17:C2": "ASUSTek",
    "E0:3F:49": "ASUSTek",
    "F4:6D:04": "ASUSTek",
    "00:18:F3": "ASUSTek",
    "00:1A:92": "ASUSTek",
    "00:1D:60": "ASUSTek",
    "00:1E:8C": "ASUSTek",
    "00:22:15": "ASUSTek",
    "00:23:54": "ASUSTek",
    "00:24:8C": "ASUSTek",
    "00:25:22": "ASUSTek",
    "00:26:18": "ASUSTek",
    "00:0E:8F": "Sercomm",
    "00:11:32": "Synology",
    "00:07:7D": "Cisco",
    "00:1A:A1": "Cisco",
    "00:1B:0D": "Cisco",
    "00:1C:58": "Cisco",
    "00:1E:13": "Cisco",
    "00:1E:14": "Cisco",
    "00:21:A0": "Cisco",
    "00:23:04": "Cisco",
    "00:23:AB": "Cisco",
    "00:24:C4": "Cisco",
    "00:25:45": "Cisco",
    "00:25:83": "Cisco",
    "00:25:9C": "Cisco",
    "00:26:0B": "Cisco",
    "00:26:98": "Cisco",
    "00:26:CA": "Cisco",
    "00:03:6B": "Cisco",
    "00:04:9F": "Cisco",
    "00:0A:41": "Cisco",
    "00:0A:8A": "Cisco",
    "00:0C:85": "Cisco",
    "00:0E:38": "Cisco",
    "00:0F:23": "Cisco",
    "00:0F:8F": "Cisco",
    "00:11:5C": "Cisco",
    "00:11:92": "Cisco",
    "00:12:00": "Cisco",
    "00:12:17": "Cisco",
    "00:12:43": "Cisco",
    "00:12:7F": "Cisco",
    "00:12:D9": "Cisco",
    "00:13:10": "Cisco",
    "00:13:60": "Cisco",
    "00:13:7F": "Cisco",
    "00:13:C4": "Cisco",
    "00:14:1B": "Cisco",
    "00:14:69": "Cisco",
    "00:14:A8": "Cisco",
    "00:14:F1": "Cisco",
    "00:14:F2": "Cisco",
    "00:15:62": "Cisco",
    "00:15:C6": "Cisco",
    "00:15:F9": "Cisco",
    "00:16:9C": "Cisco",
    "00:16:B6": "Cisco",
    "00:16:C7": "Cisco",
    "00:17:0E": "Cisco",
    "00:17:33": "Cisco",
    "00:17:59": "Cisco",
    "00:17:94": "Cisco",
    "00:17:DF": "Cisco",
    "00:18:0F": "Cisco",
    "00:18:18": "Cisco",
    "00:18:68": "Cisco",
    "00:18:73": "Cisco",
    "00:18:B9": "Cisco",
    "00:19:06": "Cisco",
    "00:19:2F": "Cisco",
    "00:19:55": "Cisco",
    "00:19:A9": "Cisco",
    "00:19:E7": "Cisco",
    "00:1A:2F": "Cisco",
    "00:1A:6D": "Cisco",
    "00:1A:A2": "Cisco",
    "00:1B:0C": "Cisco",
    "00:1B:2A": "Cisco",
    "00:1B:54": "Cisco",
    "00:1B:67": "Cisco",
    "00:1B:8F": "Cisco",
    "00:1B:D4": "Cisco",
    "00:1B:D5": "Cisco",
    "00:1C:0E": "Cisco",
    "00:1C:57": "Cisco",
    "00:1C:B0": "Cisco",
    "00:1C:B1": "Cisco",
    "00:1D:45": "Cisco",
    "00:1D:46": "Cisco",
    "00:1D:70": "Cisco",
    "00:1D:71": "Cisco",
    "00:1D:A1": "Cisco",
    "00:1D:A2": "Cisco",
    "00:1E:13": "Cisco",
    "00:1E:14": "Cisco",
    "00:1E:49": "Cisco",
    "00:1E:4A": "Cisco",
    "00:1E:79": "Cisco",
    "00:1E:7A": "Cisco",
    "00:1E:BD": "Cisco",
    "00:1E:BE": "Cisco",
    "00:1E:F6": "Cisco",
    "00:1E:F7": "Cisco",
    "00:1F:26": "Cisco",
    "00:1F:27": "Cisco",
    "00:1F:6C": "Cisco",
    "00:1F:6D": "Cisco",
    "00:1F:9E": "Cisco",
    "00:1F:9F": "Cisco",
    "00:1F:C9": "Cisco",
    "00:1F:CA": "Cisco",
    "00:21:1B": "Cisco",
    "00:21:1C": "Cisco",
    "00:21:55": "Cisco",
    "00:21:56": "Cisco",
    "00:21:A0": "Cisco",
    "00:21:A1": "Cisco",
    "00:21:D7": "Cisco",
    "00:21:D8": "Cisco",
    "00:22:3A": "Cisco",
    "00:22:3B": "Cisco",
    "00:22:55": "Cisco",
    "00:22:56": "Cisco",
    "00:22:90": "Cisco",
    "00:22:91": "Cisco",
    "00:22:CE": "Cisco",
    "00:22:CF": "Cisco",
    "00:23:04": "Cisco",
    "00:23:05": "Cisco",
    "00:23:33": "Cisco",
    "00:23:34": "Cisco",
    "00:23:5E": "Cisco",
    "00:23:5F": "Cisco",
    "00:23:AB": "Cisco",
    "00:23:AC": "Cisco",
    "00:23:BE": "Cisco",
    "00:23:EA": "Cisco",
    "00:23:EB": "Cisco",
    "00:24:13": "Cisco",
    "00:24:14": "Cisco",
    "00:24:50": "Cisco",
    "00:24:51": "Cisco",
    "00:24:97": "Cisco",
    "00:24:98": "Cisco",
    "00:24:C3": "Cisco",
    "00:24:C4": "Cisco",
    "00:24:F9": "Cisco",
    "00:24:FA": "Cisco",
    "00:25:2E": "Cisco",
    "00:25:2F": "Cisco",
    "00:25:45": "Cisco",
    "00:25:46": "Cisco",
    "00:25:83": "Cisco",
    "00:25:84": "Cisco",
    "00:25:9C": "Cisco",
    "00:25:9D": "Cisco",
    "00:25:B4": "Cisco",
    "00:25:B5": "Cisco",
    "00:26:0A": "Cisco",
    "00:26:0B": "Cisco",
    "00:26:51": "Cisco",
    "00:26:52": "Cisco",
    "00:26:98": "Cisco",
    "00:26:99": "Cisco",
    "00:26:CA": "Cisco",
    "00:26:CB": "Cisco",
}

def get_vendor(mac):
    if not mac or mac == "Unknown":
        return "Unknown"
    prefix = mac.upper().replace("-", ":")[:8]
    return OUI_VENDORS.get(prefix, "Unknown")

# ====================== HELPERS ======================

def run(cmd, timeout=15):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)

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
    print(f"  Vendor         : {get_vendor(info['mac'])}")
    pause()

# ====================== WIFI SCANNER ======================

def wifi_scan(return_data=False):
    if not return_data:
        clear()
        header("WIFI SCANNER")
        print("Scanning nearby networks...\n")

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
            "security": security or "Open",
            "vendor": get_vendor(bssid)
        })

    networks.sort(key=lambda x: x["signal"], reverse=True)

    if not return_data:
        print(f"{'':2} {'SSID':<24} {'Signal':<9} {'Ch':<4} {'Security':<12} {'Vendor':<14} {'BSSID'}")
        print("-" * 95)
        for n in networks:
            print(f"{n['in_use']:2} {n['ssid']:<24} {n['signal']:>3}% {n['bars']:<4} {n['channel']:<4} "
                  f"{n['security']:<12} {n['vendor']:<14} {n['bssid']}")
        print(f"\nFound {len(networks)} network(s)")
        pause()
    return networks

# ====================== DEVICE DISCOVERY ======================

def ping_host(ip):
    result = run(f"ping -c 1 -W 1 {ip}", timeout=3)
    return "1 received" in result or "1 packets received" in result

def get_mac(ip):
    return run(f"arp -n {ip} 2>/dev/null | awk '/{ip}/ {{print $3}}'") or "Unknown"

def discover_devices(return_data=False):
    if not return_data:
        clear()
        header("LOCAL NETWORK DEVICE DISCOVERY")

    info = get_current_info()
    if info["ip"] == "N/A":
        if not return_data:
            print("Not connected to a network.")
            pause()
        return []

    try:
        network = ipaddress.IPv4Network(f"{info['ip']}/{info['netmask'].split('/')[-1]}", strict=False)
    except Exception:
        base = ".".join(info["ip"].split(".")[:3])
        network = ipaddress.IPv4Network(f"{base}.0/24", strict=False)

    if not return_data:
        print(f"Scanning {network} ...\n")

    alive = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = {executor.submit(ping_host, str(ip)): str(ip) for ip in network.hosts()}
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            if future.result():
                mac = get_mac(ip)
                vendor = get_vendor(mac)
                alive.append({"ip": ip, "mac": mac, "vendor": vendor})
                if not return_data:
                    print(f"  [+] {ip:<16}  {mac:<18}  {vendor}")

    if not return_data:
        print(f"\nFound {len(alive)} active device(s)")
        pause()
    return alive

# ====================== PORT SCANNER ======================

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 139: "NetBIOS", 143: "IMAP", 443: "HTTPS",
    445: "SMB", 993: "IMAPS", 995: "POP3S", 1433: "MSSQL", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 5900: "VNC", 6379: "Redis",
    8080: "HTTP-Alt", 8443: "HTTPS-Alt", 27017: "MongoDB"
}

def scan_port(ip, port, timeout=0.7):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return port if s.connect_ex((ip, port)) == 0 else None
    except Exception:
        return None

def port_scanner():
    clear()
    header("PORT SCANNER")
    target = input("Target IP (Enter = gateway): ").strip()
    if not target:
        target = get_current_info()["gateway"]
        print(f"Using gateway: {target}")

    print(f"\nScanning common ports on {target}...\n")
    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        futures = {executor.submit(scan_port, target, p): p for p in COMMON_PORTS}
        for future in concurrent.futures.as_completed(futures):
            port = future.result()
            if port:
                service = COMMON_PORTS.get(port, "Unknown")
                print(f"  [OPEN] {port:<5} → {service}")
                open_ports.append((port, service))

    print(f"\n{len(open_ports)} open port(s) found.")
    pause()

# ====================== PUBLIC IP ======================

def public_ip():
    clear()
    header("PUBLIC IP LOOKUP")
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://ident.me"
    ]
    for url in services:
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=5) as resp:
                ip = resp.read().decode().strip()
                print(f"\n  Public IP : {ip}")
                print(f"  Source    : {url}")
                break
        except Exception:
            continue
    else:
        print("\n  Could not determine public IP")
    pause()

# ====================== DNS TOOLS ======================

def dns_tools():
    clear()
    header("DNS TOOLS")
    print("1. Forward Lookup (name → IP)")
    print("2. Reverse Lookup (IP → name)")
    choice = input("\nChoice: ").strip()

    if choice == "1":
        host = input("Hostname: ").strip()
        try:
            ip = socket.gethostbyname(host)
            print(f"\n  {host} → {ip}")
        except Exception as e:
            print(f"\n  Error: {e}")
    elif choice == "2":
        ip = input("IP Address: ").strip()
        try:
            name = socket.gethostbyaddr(ip)[0]
            print(f"\n  {ip} → {name}")
        except Exception as e:
            print(f"\n  Error: {e}")
    pause()

# ====================== PING TOOL ======================

def ping_tool():
    clear()
    header("PING TOOL")
    target = input("Target (IP or hostname): ").strip()
    count = input("Count [4]: ").strip() or "4"
    print()
    os.system(f"ping -c {count} {target}")
    pause()

# ====================== TRACEROUTE ======================

def traceroute():
    clear()
    header("TRACEROUTE")
    target = input("Target: ").strip()
    print()
    os.system(f"traceroute -n -w 1 -q 1 {target} 2>/dev/null || tracepath -n {target}")
    pause()

# ====================== ARP TABLE ======================

def arp_table():
    clear()
    header("ARP TABLE")
    print(run("arp -n"))
    pause()

# ====================== LISTENING PORTS ======================

def listening_ports():
    clear()
    header("LOCAL LISTENING PORTS")
    print(run("ss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null"))
    pause()

# ====================== INTERFACE TRAFFIC ======================

def interface_stats():
    clear()
    header("INTERFACE TRAFFIC STATISTICS")
    print(run("cat /proc/net/dev"))
    print("\n" + "-" * 40)
    print(run("ip -s link"))
    pause()

# ====================== SPEED TEST ======================

def speed_test():
    clear()
    header("SIMPLE SPEED TEST")
    print("Downloading a test file to measure speed...\n")

    urls = [
        ("https://speed.cloudflare.com/__down?bytes=10000000", 10),   # 10 MB
        ("https://proof.ovh.net/files/10Mb.dat", 10),
    ]

    for url, size_mb in urls:
        try:
            print(f"Testing with {url} ...")
            start = time.time()
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            elapsed = time.time() - start
            if elapsed > 0:
                speed = (len(data) * 8) / (elapsed * 1_000_000)  # Mbps
                print(f"  Downloaded {len(data)/1_000_000:.1f} MB in {elapsed:.2f}s")
                print(f"  Approximate speed: {speed:.2f} Mbps\n")
                break
        except Exception as e:
            print(f"  Failed: {e}\n")
    else:
        print("All speed test servers failed.")
    pause()

# ====================== WIFI SIGNAL MONITOR ======================

def wifi_monitor():
    clear()
    header("WIFI SIGNAL MONITOR")
    print("Monitoring signal strength of current network (Ctrl+C to stop)\n")
    try:
        while True:
            signal = run("nmcli -t -f IN-USE,SIGNAL,SSID device wifi | grep '^*' | cut -d: -f2")
            ssid = run("nmcli -t -f IN-USE,SSID device wifi | grep '^*' | cut -d: -f2")
            bars = run("nmcli -t -f IN-USE,BARS device wifi | grep '^*' | cut -d: -f2")
            print(f"\r  [{datetime.datetime.now().strftime('%H:%M:%S')}]  {ssid}  →  {signal}%  {bars}   ", end="")
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")
        pause()

# ====================== FULL REPORT + JSON ======================

def full_report():
    clear()
    header("FULL NETWORK REPORT")
    print("Collecting data, please wait...\n")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_file = f"network_report_{timestamp}.txt"
    json_file = f"network_report_{timestamp}.json"

    current = get_current_info()
    networks = wifi_scan(return_data=True)
    devices = discover_devices(return_data=True)

    # Text report
    with open(txt_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("  SharkDeck Full Network Report\n")
        f.write(f"  Generated: {datetime.datetime.now()}\n")
        f.write("=" * 70 + "\n\n")

        f.write("CURRENT CONNECTION\n" + "-"*40 + "\n")
        for k, v in current.items():
            f.write(f"  {k:<12}: {v}\n")
        f.write(f"  vendor      : {get_vendor(current.get('mac'))}\n\n")

        f.write("NEARBY WIFI NETWORKS\n" + "-"*40 + "\n")
        for n in networks:
            f.write(f"  {n['in_use']} {n['ssid']:<24} {n['signal']:>3}%  Ch:{n['channel']:<4} "
                    f"{n['security']:<10} {n['vendor']:<12} {n['bssid']}\n")

        f.write(f"\nACTIVE DEVICES ({len(devices)})\n" + "-"*40 + "\n")
        for d in sorted(devices, key=lambda x: x["ip"]):
            f.write(f"  {d['ip']:<16}  {d['mac']:<18}  {d['vendor']}\n")

    # JSON report
    report = {
        "generated": str(datetime.datetime.now()),
        "current_connection": current,
        "wifi_networks": networks,
        "devices": devices
    }
    with open(json_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Text report  → {os.path.abspath(txt_file)}")
    print(f"JSON report  → {os.path.abspath(json_file)}")
    pause()

# ====================== MAIN MENU ======================

def main_menu():
    while True:
        clear()
        header("SHARKDECK NETWORK SUITE - EXPANDED")
        print("""
  1.  Current Connection Info
  2.  WiFi Scanner
  3.  Discover Devices on LAN
  4.  Port Scanner
  5.  Public IP Lookup
  6.  DNS Tools (Forward / Reverse)
  7.  Ping Tool
  8.  Traceroute
  9.  ARP Table
 10.  Local Listening Ports
 11.  Interface Traffic Stats
 12.  Speed Test (Download)
 13.  WiFi Signal Monitor (live)
 14.  Generate Full Report (TXT + JSON)
  0.  Exit
        """)
        choice = input("Select option: ").strip()

        actions = {
            "1": show_current_connection,
            "2": wifi_scan,
            "3": discover_devices,
            "4": port_scanner,
            "5": public_ip,
            "6": dns_tools,
            "7": ping_tool,
            "8": traceroute,
            "9": arp_table,
            "10": listening_ports,
            "11": interface_stats,
            "12": speed_test,
            "13": wifi_monitor,
            "14": full_report,
        }

        if choice == "0":
            print("\nGoodbye.")
            break
        elif choice in actions:
            actions[choice]()
        else:
            print("Invalid choice")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting.")
        sys.exit(0)
