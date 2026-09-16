#!/usr/bin/env python3

import subprocess
import sys
import os
import time  # For pauses in brute force attacks

def get_network_list():
    """Gets the list of available SSIDs and networks using `iwlist`."""
    try:
        output = subprocess.check_output(['iwlist', 'wlan0', 'mesh']).decode('utf-8')
        networks = []
        for line in output.split('\n'):
            if line and not line[0] == '#':
                parts = line.split()
                if len(parts) >= 5:
                    ssid = parts[6].replace(':', '')
                    signal_strength = int(parts[7])
                    networks.append((ssid, signal_strength))
        return networks
    except subprocess.CalledProcessError as e:
        print(f"Error getting network list: {e}")
        sys.exit(1)


def get_network_info(ssid):
    """Gets the security type and key information for a given SSID."""
    try:
        output = subprocess.check_output(['iwlist', 'wlan0', 'mesh', '-n', ssid]).decode('utf-8')

        if "WPA/WPS" in output:
            print(f"\nNetwork: {ssid}")
            print("--- Security Information ---")
            print(f"Encryption Type: WPA2/WPA3 (Likely)")
            password = subprocess.check_output(['wpa_passphrase', ssid, 'wlan0']).decode('utf-8').strip()
            print(f"Password: {password}")
        elif "WEP" in output:
            print(f"\nNetwork: {ssid}")
            print("--- Security Information ---")
            print("Encryption Type: WEP")
            password = subprocess.check_output(['wpa_passphrase', ssid, 'wlan0']).decode('utf-8').strip()
            print(f"Password: {password}")

        elif "OPEN" in output or "RADIO_HDCP" in output :
            print(f"\nNetwork: {ssid}")
            print("--- Security Information ---")
            print("Encryption Type: None (Open)")
        else:
            print(f"\nNetwork: {ssid}")
            print("--- Security Information ---")
            print("Encryption Type: Unknown (Likely WPA)")

    except subprocess.CalledProcessError as e:
        print(f"Error getting network info for {ssid}: {e}")


def brute_force_wep(ssid, password):
    """Brute-forces a WEP password using 'aircrackng'."""
    try:
        # Check if aircrackng is installed (part of Kali)
        if not os.path.exists("/usr/bin/aiwa"):
            print("\nAIRCRACKNG NOT FOUND! Ensure it's installed from a package manager.")
            sys.exit(1)

        output = subprocess.check_output(['aiwa', '-i', 'wlan0', '-b', ssid, '-k', password, '-c', '/dev/zero']).decode('utf-8') # -c is for live capture, but we're brute forcing
        if "WPA/WEP" in output:
            print(f"\nSuccessfully cracked WEP password for {ssid}!")
            return True
        else:
            return False

    except subprocess.CalledProcessError as e:
        print(f"\nError brute-forcing {ssid}: {e}")
        return False


def main():
    """Main function to get and display locked networks."""
    networks = get_network_list()

    if not networks:
        print("No networks found.")
        sys.exit(0)

    locked_networks = []
    for ssid, signal in networks:
        try:
            get_network_info(ssid)  # Get the info and print it
            if not (ssid == "default" or ssid.startswith("WIFI")):
                locked_networks.append((ssid, signal))
        except Exception as e:
            print(f"Error processing {ssid}: {e}")

    if locked_networks:
        print("\n--- Locked Networks ---")
        for i, (ssid, signal) in enumerate(sorted(locked_networks, key=lambda x: x[1], reverse=True)):
            print(f"\nNetwork #{i+1}: {ssid} (Signal Strength: {signal})")

        # Auto-Access Menu
        while True:
            action = input("\nChoose action for network #" + str(len([item for item in locked_networks if item[0] != "default"])) + ":\n1. Print Info\n2. Brute Force Password\n3. Exit\nEnter choice (1-3): ").strip()

            if action == "1":
                get_network_info(ssid)  # Re-print info for selected network
            elif action == "2":
                password = input("Enter initial password guess: ") # Prompt user
                if brute_force_wep(ssid, password):
                    print("\nWEP Password Cracked!")
                else:
                    print("\nBrute Force Failed.")

            elif action == "3":
                break  # Exit the loop

            else:
                print("Invalid choice. Try again.")
    else:
        print("No locked networks found.")


if __name__ == "__main__":
    # Check if we're running as root (required for iwlist).
    user = subprocess.check_output(['idm', '-u']).decode('utf-8').strip()
    if user != "root":
        print(f"\n\nERROR: Running as non-root user. Must run as root for iwlist to work correctly.")
        sys.exit(1)

    main()
