#!/usr/bin/env python3
"""
Observergotchi - Passive WiFi Companion for SharkDeck
Inspired by Pwnagotchi, but 100% passive & legal.
"""

import subprocess
import os
import sys
import time
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

SAVE_FILE = Path("observergotchi_save.json")

# ====================== FACES ======================

FACES = {
    "happy":      "(•‿•)",
    "excited":    "(≧▽≦)",
    "bored":      "(－_－)",
    "curious":    "(•‿•)؟",
    "sleeping":   "(–_–) zz",
    "surprised":  "(◎_◎)",
    "sad":        "(╥_╥)",
    "cool":       "(•̀ᴗ•́)و",
    "thinking":   "(・_・ )",
    "love":       "(♥‿♥)",
    "neutral":    "(•_•)",
}

# ====================== HELPERS ======================

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def now():
    return datetime.now()

# ====================== CORE CLASS ======================

class Observergotchi:
    def __init__(self):
        self.name = "Observer"
        self.born = now().isoformat()
        self.last_active = now().isoformat()
        self.age_hours = 0.0

        # Personality / Mood
        self.mood = "curious"
        self.boredom = 20
        self.excitement = 40
        self.energy = 80

        # Stats
        self.networks_seen = 0
        self.unique_ssids = set()
        self.unique_bssids = set()
        self.open_networks = 0
        self.wpa3_networks = 0
        self.interesting_found = 0
        self.scans_done = 0
        self.total_uptime_minutes = 0

        # Memory of recent networks
        self.recent_ssids = []
        self.last_scan_count = 0

    def to_dict(self):
        data = self.__dict__.copy()
        data["unique_ssids"] = list(self.unique_ssids)
        data["unique_bssids"] = list(self.unique_bssids)
        return data

    @classmethod
    def from_dict(cls, data):
        obj = cls()
        data["unique_ssids"] = set(data.get("unique_ssids", []))
        data["unique_bssids"] = set(data.get("unique_bssids", []))
        obj.__dict__.update(data)
        return obj

    def save(self):
        with open(SAVE_FILE, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls):
        if SAVE_FILE.exists():
            try:
                with open(SAVE_FILE, "r") as f:
                    return cls.from_dict(json.load(f))
            except Exception:
                pass
        return None

    def update_time(self):
        current = now()
        last = datetime.fromisoformat(self.last_active)
        delta = (current - last).total_seconds() / 3600
        self.age_hours += delta
        self.total_uptime_minutes += delta * 60
        self.last_active = current.isoformat()

        # Natural mood decay
        self.boredom = min(100, self.boredom + delta * 8)
        self.excitement = max(0, self.excitement - delta * 5)
        self.energy = max(10, self.energy - delta * 2)

    def get_face(self):
        if self.energy < 20:
            return FACES["sleeping"]
        if self.excitement > 75:
            return FACES["excited"]
        if self.boredom > 70:
            return FACES["bored"]
        if self.mood == "happy":
            return FACES["happy"]
        if self.mood == "curious":
            return FACES["curious"]
        if self.mood == "cool":
            return FACES["cool"]
        if self.mood == "surprised":
            return FACES["surprised"]
        return FACES["neutral"]

    def speak(self):
        lines = {
            "happy": [
                "The airwaves feel friendly today.",
                "So many networks... I like this place.",
                "I'm in a good mood. Keep me exploring!"
            ],
            "excited": [
                "New signals! New signals everywhere!",
                "This is the best day ever!",
                "I can feel the packets flowing!"
            ],
            "bored": [
                "Same old networks... nothing new.",
                "Is this all there is?",
                "I'm getting bored... take me somewhere else."
            ],
            "curious": [
                "I wonder what's hiding in that hidden SSID...",
                "Hmm... interesting encryption choices.",
                "The spectrum is full of secrets."
            ],
            "cool": [
                "Just another day observing the wild.",
                "I've seen things you wouldn't believe.",
                "Stay curious, human."
            ],
            "surprised": [
                "Whoa! Did you see that open network?!",
                "Unexpected signal detected!",
                "That was new..."
            ]
        }
        return random.choice(lines.get(self.mood, lines["curious"]))

# ====================== WIFI OBSERVATION ======================

def passive_scan():
    run("nmcli device wifi rescan >/dev/null 2>&1")
    raw = run("nmcli -t -f SSID,BSSID,SIGNAL,SECURITY device wifi list")

    networks = []
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        ssid = parts[0] if parts[0] else "<Hidden>"
        bssid = parts[1].upper()
        signal = int(parts[2]) if parts[2].isdigit() else 0
        security = parts[3] if parts[3] else "Open"

        networks.append({
            "ssid": ssid,
            "bssid": bssid,
            "signal": signal,
            "security": security
        })
    return networks

def observe(pet, networks):
    pet.scans_done += 1
    pet.last_scan_count = len(networks)

    new_ssids = 0
    new_bssids = 0
    open_count = 0
    wpa3_count = 0

    for net in networks:
        if net["ssid"] not in pet.unique_ssids:
            pet.unique_ssids.add(net["ssid"])
            new_ssids += 1
        if net["bssid"] not in pet.unique_bssids:
            pet.unique_bssids.add(net["bssid"])
            new_bssids += 1

        sec = net["security"].upper()
        if "OPEN" in sec or sec in ("", "--", "NONE"):
            open_count += 1
        if "WPA3" in sec:
            wpa3_count += 1

    pet.networks_seen += len(networks)
    pet.open_networks += open_count
    pet.wpa3_networks += wpa3_count

    # Mood logic
    if new_ssids > 3 or new_bssids > 5:
        pet.mood = "excited"
        pet.excitement = min(100, pet.excitement + 25)
        pet.boredom = max(0, pet.boredom - 20)
        pet.interesting_found += 1
    elif open_count > 0:
        pet.mood = "surprised"
        pet.excitement = min(100, pet.excitement + 15)
    elif new_ssids > 0:
        pet.mood = "curious"
        pet.boredom = max(0, pet.boredom - 10)
    elif pet.boredom > 60:
        pet.mood = "bored"
    else:
        pet.mood = random.choice(["happy", "curious", "cool"])

    # Keep recent memory short
    pet.recent_ssids = [n["ssid"] for n in networks[:8]]

    pet.save()
    return new_ssids, new_bssids, open_count

# ====================== DISPLAY ======================

def draw(pet):
    clear()
    age_days = pet.age_hours / 24

    print("╔══════════════════════════════════════╗")
    print(f"║         OBSERVERGOTCHI               ║")
    print("╚══════════════════════════════════════╝")
    print()
    print(f"              {pet.get_face()}")
    print()
    print(f"  Name     : {pet.name}")
    print(f"  Age      : {age_days:.1f} days")
    print(f"  Mood     : {pet.mood.capitalize()}")
    print()
    print(f"  Boredom  : {pet.boredom:3.0f}%")
    print(f"  Excitement: {pet.excitement:3.0f}%")
    print(f"  Energy   : {pet.energy:3.0f}%")
    print()
    print("────────────── Stats ──────────────")
    print(f"  Scans done     : {pet.scans_done}")
    print(f"  Unique SSIDs   : {len(pet.unique_ssids)}")
    print(f"  Unique BSSIDs  : {len(pet.unique_bssids)}")
    print(f"  Open networks  : {pet.open_networks}")
    print(f"  WPA3 seen      : {pet.wpa3_networks}")
    print(f"  Interesting    : {pet.interesting_found}")
    print()
    print(f"  Last scan      : {pet.last_scan_count} networks")
    print()
    print("─────────── Thought ─────────────")
    print(f"  \"{pet.speak()}\"")
    print()
    print("──────────────────────────────────")
    print("  [s] Scan now    [a] Auto mode")
    print("  [r] Rename      [q] Quit")
    print("──────────────────────────────────")

# ====================== MAIN ======================

def main():
    pet = Observergotchi.load()

    if pet is None:
        clear()
        print("A new Observergotchi is waking up...\n")
        name = input("Name your Observergotchi: ").strip()
        pet = Observergotchi()
        if name:
            pet.name = name
        pet.save()
        print(f"\n{pet.name} is online. Let's observe the airwaves.")
        time.sleep(1.5)

    auto_mode = False
    scan_interval = 30  # default

    while True:
        pet.update_time()
        draw(pet)

        if auto_mode:
            print(f"\n  Auto mode active — scanning every {scan_interval} seconds.")
            print("  Press Ctrl+C to stop auto mode.")
            try:
                networks = passive_scan()
                new_s, new_b, opens = observe(pet, networks)
                print(f"\n  → Seen {len(networks)} networks | +{new_s} new SSIDs | {opens} open")
                time.sleep(scan_interval)
                continue
            except KeyboardInterrupt:
                auto_mode = False
                print("\n  Auto mode stopped.")
                time.sleep(1)
                continue

        choice = input("\nCommand: ").strip().lower()

        if choice == "s":
            print("\n  Scanning...")
            networks = passive_scan()
            new_s, new_b, opens = observe(pet, networks)
            print(f"  Found {len(networks)} networks")
            print(f"  New SSIDs: {new_s} | New BSSIDs: {new_b} | Open: {opens}")
            time.sleep(1.8)

        elif choice == "a":
            try:
                user_input = input(f"  Scan interval in seconds [{scan_interval}]: ").strip()
                if user_input:
                    val = int(user_input)
                    if val < 5:
                        print("  Minimum interval is 5 seconds.")
                        time.sleep(1.2)
                        continue
                    scan_interval = val
                auto_mode = True
                print(f"\n  Auto mode started (every {scan_interval}s)")
                time.sleep(1)
            except ValueError:
                print("  Please enter a valid number.")
                time.sleep(1)

        elif choice == "r":
            new_name = input("  New name: ").strip()
            if new_name:
                pet.name = new_name
                pet.save()

        elif choice == "q":
            pet.save()
            print(f"\n  {pet.name} goes to sleep. See you later.")
            break

        else:
            time.sleep(0.3)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBye!")
        sys.exit(0)
