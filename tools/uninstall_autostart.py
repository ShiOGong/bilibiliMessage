#!/usr/bin/env python3
import os
import subprocess

PLIST_ID = "com.bili.notify"


def main():
    plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_ID}.plist")
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], check=False)
        os.remove(plist_path)
        print(f"Removed: {plist_path}")
    else:
        print("No autostart plist found.")


if __name__ == "__main__":
    main()
