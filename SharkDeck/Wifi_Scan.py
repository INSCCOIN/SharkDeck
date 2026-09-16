#!/usr/bin/env python3
"""
SharkDeck Network Suite - Advanced Edition
Pure Python + system tools only
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
import csv
import re
import signal
from collections import defaultdict
from urllib.request import urlopen, Request

# ====================== OUI VENDOR DATABASE (short version) ======================
OUI_VENDORS = {
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi", "E4:5F:01": "Raspberry Pi",
    "28:CD:C1": "Raspberry Pi", "D8:3A:DD": "Raspberry Pi",
    "F0:18:98": "Apple", "3C:22:FB": "Apple", "A4:83:E7": "Apple", "AC:DE:48": "Apple",
    "00:50:56": "VMware", "00:0C:29": "VMware", "00:05:69": "VMware",
    "00:15:5D": "Microsoft", "00:50:F2": "Microsoft", "00:03:FF": "Microsoft",
    "00:1A:11": "Google", "F4:F5:D8": "Google", "3C:5A:B4": "Google",
    "00:1E:8C": "ASUS", "04:92:26": "ASUS", "2C:4D:54": "ASUS", "54:04:A6": "ASUS",
    "00:11:32": "Synology", "00:07:7D": "Cisco", "00:1A:A1": "Cisco",
    "00:0E:8F": "Sercomm", "00:22:6B": "Cisco-Linksys", "00:25:9C": "Cisco-Linksys",
}

def get_vendor(mac):
    if not mac or len(mac) < 8:
        return "Unknown"
    prefix = mac.upper().replace("-", ":")[:8]
    return OUI_VENDORS.get(prefix, "Unknown")

# ====================== HELPERS ======================

def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 66)
    print(f"  {title}")
    print("=" * 66)

def get_current_info():
    info = {}
    info["ssid"] = run("nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2") or "Not connected"
    info["ip"] = run("hostname -I | awk '{print $1}'") or "N/A"
    info["gateway"] = run("ip route | grep default | awk '{print $3}'") or "N/A"
    info["iface"] = run("ip route | grep default | awk '{print $5}'") or "N/A"
    info["mac"] = run(f"cat /sys/class/net/{info['iface']}/address 2>/dev/null") or "N/A"
    info["dns"] = run("nmcli -t -f IP4.DNS device show 2>/dev/null | head -1 | cut -d: -f2") or "N/A"
    info["netmask"] = run(f"ip -o -f inet addr show {info['iface']} | awk '{{print $4}}'") or "N/A"
    return info

# ====================== 1. CURRENT CONNECTION ======================

def show_current_connection():
    clear()
    header("CURRENT CONNECTION")
    info = get_current_info()
    for k, v in info.items():
        print(f"  {k:<10}: {v}")
    print(f"  vendor    : {get_vendor(info['mac'])}")
    pause()

# ====================== 2. WIFI SCANNER ======================

def wifi_scan(return_data=False):
    if not return_data:
        clear()
        header("WIFI SCANNER")
        print("Scanning...\n")

    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,BARS,SECURITY device wifi list")

    networks = []
    for line in raw.splitlines():
        p = line.split(":")
        if len(p) < 8:
            continue
        networks.append({
            "in_use": "*" if p[0] == "*" else " ",
            "ssid": p[1] or "<Hidden>",
            "bssid": p[2],
            "channel": p[3],
            "freq": p[4],
            "signal": int(p[5]) if p[5].isdigit() else 0,
            "bars": p[6],
            "security": p[7] or "Open",
            "vendor": get_vendor(p[2])
        })
    networks.sort(key=lambda x: x["signal"], reverse=True)

    if not return_data:
        print(f"{'':2}{'SSID':<22} {'Sig':<8} {'Ch':<4} {'Sec':<10} {'Vendor':<13} BSSID")
        print("-" * 90)
        for n in networks:
            print(f"{n['in_use']:2}{n['ssid']:<22} {n['signal']:>3}% {n['bars']:<4} {n['channel']:<4} "
                  f"{n['security']:<10} {n['vendor']:<13} {n['bssid']}")
        print(f"\nTotal: {len(networks)} networks")
        pause()
    return networks

# ====================== 3. DEVICE DISCOVERY ======================

def ping_host(ip):
    return "1 received" in run(f"ping -c 1 -W 1 {ip}", timeout=2.5)

def get_mac(ip):
    return run(f"arp -n {ip} 2>/dev/null | awk '/{ip}/{{print $3}}'") or "Unknown"

def discover_devices(return_data=False):
    if not return_data:
        clear()
        header("LAN DEVICE DISCOVERY")

    info = get_current_info()
    if info["ip"] == "N/A":
        if not return_data:
            print("Not connected.")
            pause()
        return []

    try:
        net = ipaddress.IPv4Network(f"{info['ip']}/{info['netmask'].split('/')[-1]}", strict=False)
    except Exception:
        base = ".".join(info["ip"].split(".")[:3])
        net = ipaddress.IPv4Network(f"{base}.0/24", strict=False)

    if not return_data:
        print(f"Scanning {net} ...\n")

    devices = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=70) as exe:
        futs = {exe.submit(ping_host, str(ip)): str(ip) for ip in net.hosts()}
        for fut in concurrent.futures.as_completed(futs):
            ip = futs[fut]
            if fut.result():
                mac = get_mac(ip)
                devices.append({"ip": ip, "mac": mac, "vendor": get_vendor(mac)})
                if not return_data:
                    print(f"  [+] {ip:<15} {mac:<17} {get_vendor(mac)}")

    if not return_data:
        print(f"\nFound {len(devices)} devices")
        pause()
    return devices

# ====================== 4. PORT SCANNER ======================

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP",
    110: "POP3", 139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    993: "IMAPS", 995: "POP3S", 1433: "MSSQL", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 8080: "HTTP-Proxy",
    8443: "HTTPS-Alt", 27017: "MongoDB"
}

def scan_port(ip, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.6)
            return port if s.connect_ex((ip, port)) == 0 else None
    except:
        return None

def port_scanner():
    clear()
    header("PORT SCANNER")
    target = input("Target IP [gateway]: ").strip() or get_current_info()["gateway"]
    print(f"\nScanning {target}...\n")
    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as exe:
        futs = {exe.submit(scan_port, target, p): p for p in COMMON_PORTS}
        for fut in concurrent.futures.as_completed(futs):
            p = fut.result()
            if p:
                print(f"  OPEN  {p:<5} {COMMON_PORTS[p]}")
                open_ports.append(p)
    print(f"\n{len(open_ports)} open ports")
    pause()

# ====================== 5. PUBLIC IP ======================

def public_ip():
    clear()
    header("PUBLIC IP")
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            with urlopen(Request(url, headers={"User-Agent": "curl/8.0"}), timeout=5) as r:
                print(f"\n  Public IP: {r.read().decode().strip()}")
                print(f"  Source   : {url}")
                break
        except:
            continue
    else:
        print("Failed to get public IP")
    pause()

# ====================== 6. DNS TOOLS ======================

def dns_tools():
    clear()
    header("DNS TOOLS")
    print("1. Forward  2. Reverse")
    c = input("Choice: ").strip()
    if c == "1":
        host = input("Hostname: ").strip()
        try:
            print(f"\n  {host} → {socket.gethostbyname(host)}")
        except Exception as e:
            print(f"Error: {e}")
    elif c == "2":
        ip = input("IP: ").strip()
        try:
            print(f"\n  {ip} → {socket.gethostbyaddr(ip)[0]}")
        except Exception as e:
            print(f"Error: {e}")
    pause()

# ====================== 7. PING ======================

def ping_tool():
    clear()
    header("PING")
    target = input("Target: ").strip()
    count = input("Count [4]: ").strip() or "4"
    os.system(f"ping -c {count} {target}")
    pause()

# ====================== 8. TRACEROUTE ======================

def traceroute():
    clear()
    header("TRACEROUTE")
    target = input("Target: ").strip()
    os.system(f"traceroute -n -w 1 -q 1 {target} 2>/dev/null || tracepath -n {target}")
    pause()

# ====================== 9. ARP TABLE ======================

def arp_table():
    clear()
    header("ARP TABLE")
    print(run("arp -n"))
    pause()

# ====================== 10. LISTENING PORTS ======================

def listening_ports():
    clear()
    header("LISTENING PORTS")
    print(run("ss -tulnp 2>/dev/null || netstat -tulnp"))
    pause()

# ====================== 11. INTERFACE STATS ======================

def interface_stats():
    clear()
    header("INTERFACE STATISTICS")
    print(run("cat /proc/net/dev"))
    print("\n" + run("ip -s link"))
    pause()

# ====================== 12. SPEED TEST ======================

def speed_test():
    clear()
    header("SPEED TEST")
    print("Downloading test file...\n")
    for url in ["https://speed.cloudflare.com/__down?bytes=15000000",
                "https://proof.ovh.net/files/10Mb.dat"]:
        try:
            start = time.time()
            with urlopen(Request(url, headers={"User-Agent": "curl"}), timeout=25) as r:
                data = r.read()
            elapsed = time.time() - start
            mbps = (len(data) * 8) / (elapsed * 1_000_000)
            print(f"Downloaded {len(data)/1e6:.1f} MB in {elapsed:.2f}s")
            print(f"Speed ≈ {mbps:.2f} Mbps")
            break
        except Exception as e:
            print(f"Failed: {e}")
    pause()

# ====================== 13. WIFI SIGNAL MONITOR ======================

def wifi_monitor():
    clear()
    header("WIFI SIGNAL MONITOR (Ctrl+C to stop)")
    try:
        while True:
            line = run("nmcli -t -f IN-USE,SIGNAL,BARS,SSID dev wifi | grep '^*'")
            if line:
                parts = line.split(":")
                print(f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}]  "
                      f"{parts[3] if len(parts)>3 else '?'}  {parts[1]}%  {parts[2]}   ", end="")
            time.sleep(1.2)
    except KeyboardInterrupt:
        print("\nStopped.")
        pause()

# ====================== 14. FULL REPORT + CSV + JSON ======================

def full_report():
    clear()
    header("FULL REPORT")
    print("Collecting data...\n")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current = get_current_info()
    networks = wifi_scan(return_data=True)
    devices = discover_devices(return_data=True)

    # TXT
    with open(f"report_{ts}.txt", "w") as f:
        f.write(f"SharkDeck Report - {datetime.datetime.now()}\n{'='*60}\n\n")
        f.write("CURRENT CONNECTION\n")
        for k, v in current.items():
            f.write(f"  {k}: {v}\n")
        f.write("\nWIFI NETWORKS\n")
        for n in networks:
            f.write(f"  {n['ssid']:<22} {n['signal']}% Ch{n['channel']} {n['security']} {n['bssid']}\n")
        f.write(f"\nDEVICES ({len(devices)})\n")
        for d in devices:
            f.write(f"  {d['ip']:<15} {d['mac']:<17} {d['vendor']}\n")

    # JSON
    with open(f"report_{ts}.json", "w") as f:
        json.dump({"current": current, "wifi": networks, "devices": devices}, f, indent=2)

    # CSV - Devices
    with open(f"devices_{ts}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ip", "mac", "vendor"])
        w.writeheader()
        w.writerows(devices)

    # CSV - WiFi
    with open(f"wifi_{ts}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ssid", "signal", "channel", "security", "bssid", "vendor"])
        w.writeheader()
        for n in networks:
            w.writerow({k: n[k] for k in w.fieldnames})

    print(f"Saved: report_{ts}.txt / .json")
    print(f"       devices_{ts}.csv / wifi_{ts}.csv")
    pause()

# ====================== 15. WIFI CHANNEL ANALYZER ======================

def channel_analyzer():
    clear()
    header("WIFI CHANNEL ANALYZER / CONGESTION")
    networks = wifi_scan(return_data=True)

    channels = defaultdict(list)
    for n in networks:
        try:
            ch = int(n["channel"])
            channels[ch].append(n)
        except:
            pass

    print(f"{'Ch':<5} {'Count':<7} {'Strongest':<8} {'Networks'}")
    print("-" * 70)
    for ch in sorted(channels.keys()):
        nets = channels[ch]
        strongest = max(n["signal"] for n in nets)
        names = ", ".join(n["ssid"][:12] for n in nets[:4])
        if len(nets) > 4:
            names += f" +{len(nets)-4}"
        print(f"{ch:<5} {len(nets):<7} {strongest:>3}%     {names}")

    print("\nTip: Choose channels with low count and low strongest signal.")
    pause()

# ====================== 16. BANDWIDTH PER PROCESS ======================

def bandwidth_per_process():
    clear()
    header("BANDWIDTH / CONNECTIONS PER PROCESS")
    print("Active connections by process:\n")
    print(run("ss -tunap 2>/dev/null | head -50"))
    print("\n" + "-"*50)
    print("Top processes by connection count:")
    print(run("ss -tunap 2>/dev/null | grep -oP 'users:\\(\\(\"?\\K[^,\"]+' | sort | uniq -c | sort -nr | head -15"))
    pause()

# ====================== 17. TOP TALKERS ======================

def top_talkers():
    clear()
    header("TOP TALKERS (approx via conntrack/ss)")
    print("Current connections summary:\n")
    print(run("ss -s"))
    print("\nEstablished connections:\n")
    print(run("ss -tn state established 2>/dev/null | head -30"))
    pause()

# ====================== 18. CONTINUOUS MONITOR DASHBOARD ======================

def live_dashboard():
    clear()
    header("LIVE NETWORK DASHBOARD (Ctrl+C to stop)")
    try:
        while True:
            clear()
            header("LIVE NETWORK DASHBOARD")
            info = get_current_info()
            print(f"Time      : {datetime.datetime.now().strftime('%H:%M:%S')}")
            print(f"SSID      : {info['ssid']}")
            print(f"IP        : {info['ip']}")
            print(f"Gateway   : {info['gateway']}")
            print(f"Interface : {info['iface']}")

            # Signal
            sig = run("nmcli -t -f IN-USE,SIGNAL,BARS dev wifi | grep '^*'")
            if sig:
                parts = sig.split(":")
                print(f"Signal    : {parts[1]}%  {parts[2]}")

            # Quick traffic
            print("\nInterface traffic (bytes):")
            print(run(f"cat /proc/net/dev | grep {info['iface']}"))

            print("\nTop connections:")
            print(run("ss -tn state established 2>/dev/null | head -8"))

            print("\n(Refreshing every 3 seconds...)")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        pause()

# ====================== 19. ADVANCED PACKET SNIFFER ======================

def packet_sniffer():
    clear()
    header("ADVANCED PACKET SNIFFER")
    print("""
Modes:
  1. Live traffic (summary)
  2. Live traffic (detailed)
  3. Capture to PCAP file
  4. Filter by host
  5. Filter by port
  6. Only HTTP/DNS/TCP SYN
    """)
    choice = input("Select mode: ").strip()

    iface = get_current_info()["iface"]
    if iface == "N/A":
        print("No active interface.")
        pause()
        return

    base = f"tcpdump -i {iface} -n -l"

    if choice == "1":
        print("\nLive summary (Ctrl+C to stop):\n")
        os.system(f"{base} -c 50")
    elif choice == "2":
        print("\nDetailed live capture (Ctrl+C to stop):\n")
        os.system(f"{base} -v -c 30")
    elif choice == "3":
        fname = f"capture_{datetime.datetime.now().strftime('%H%M%S')}.pcap"
        count = input("Number of packets to capture [100]: ").strip() or "100"
        print(f"\nCapturing {count} packets to {fname} ...")
        os.system(f"tcpdump -i {iface} -n -c {count} -w {fname}")
        print(f"Saved → {fname}")
    elif choice == "4":
        host = input("Host IP to filter: ").strip()
        print(f"\nTraffic involving {host} (Ctrl+C to stop):\n")
        os.system(f"{base} host {host}")
    elif choice == "5":
        port = input("Port to filter: ").strip()
        print(f"\nTraffic on port {port} (Ctrl+C to stop):\n")
        os.system(f"{base} port {port}")
    elif choice == "6":
        print("\nInteresting traffic only (HTTP/DNS/SYN) (Ctrl+C to stop):\n")
        os.system(f"{base} 'tcp[13] & 2 != 0 or port 53 or port 80 or port 443'")
    else:
        print("Invalid choice")

    pause()

# ====================== MAIN MENU ======================

def main_menu():
    menu = {
        "1": ("Current Connection Info", show_current_connection),
        "2": ("WiFi Scanner", wifi_scan),
        "3": ("Discover Devices on LAN", discover_devices),
        "4": ("Port Scanner", port_scanner),
        "5": ("Public IP Lookup", public_ip),
        "6": ("DNS Tools", dns_tools),
        "7": ("Ping Tool", ping_tool),
        "8": ("Traceroute", traceroute),
        "9": ("ARP Table", arp_table),
        "10": ("Listening Ports", listening_ports),
        "11": ("Interface Statistics", interface_stats),
        "12": ("Speed Test", speed_test),
        "13": ("WiFi Signal Monitor", wifi_monitor),
        "14": ("Full Report (TXT+JSON+CSV)", full_report),
        "15": ("WiFi Channel Analyzer", channel_analyzer),
        "16": ("Bandwidth / Connections per Process", bandwidth_per_process),
        "17": ("Top Talkers", top_talkers),
        "18": ("Live Network Dashboard", live_dashboard),
        "19": ("Advanced Packet Sniffer", packet_sniffer),
        "0": ("Exit", None),
    }

    while True:
        clear()
        header("SHARKDECK NETWORK SUITE - ADVANCED")
        for k, (name, _) in menu.items():
            print(f"  {k:>2}. {name}")
        choice = input("\nSelect: ").strip()

        if choice == "0":
            print("\nGoodbye!")
            break
        elif choice in menu:
            menu[choice][1]()
        else:
            print("Invalid option")
            time.sleep(0.8)

if __name__ == "__main__":
    # Make sure we have necessary tools
    for tool in ["nmcli", "tcpdump", "ss", "arp", "ping"]:
        if not run(f"which {tool}"):
            print(f"Warning: '{tool}' not found. Some features may not work.")
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nExiting.")
        sys.exit(0)
