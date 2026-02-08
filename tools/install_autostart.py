#!/usr/bin/env python3
import os
import plistlib
import subprocess
import sys

PLIST_ID = "com.bili.notify"


def main():
    app_path = sys.argv[1] if len(sys.argv) > 1 else "/Applications/B站关注通知.app"
    if not os.path.exists(app_path):
        print(f"App not found: {app_path}")
        sys.exit(1)

    plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_ID}.plist")
    program = os.path.join(app_path, "Contents", "MacOS", "B站关注通知")
    if not os.path.exists(program):
        print(f"Executable not found: {program}")
        sys.exit(1)

    data = {
        "Label": PLIST_ID,
        "ProgramArguments": [program],
        "RunAtLoad": True,
        "KeepAlive": False,
    }

    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)

    subprocess.run(["launchctl", "unload", plist_path], check=False)
    subprocess.run(["launchctl", "load", plist_path], check=False)
    print(f"Installed autostart: {plist_path}")


if __name__ == "__main__":
    main()
