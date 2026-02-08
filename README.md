# bilibiliMessage

Monitor Bilibili dynamics for multiple UIDs and send persistent macOS notifications until you mark read.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Install notification helper:

```bash
brew install terminal-notifier
```

3. Create config:

```bash
cp config.example.json config.json
```

Edit `config.json` with your UID list.

Add run mode:
- `mode: 1` persist history (unread + last seen) and catch up missed updates on startup
- `mode: 2` in-memory only; only monitor while running
- `sender`: bundle id for notifications (e.g. `com.apple.Terminal` or `com.googlecode.iterm2`)
- `uid_names`: optional map to override display names
- `click_action`: `open` (default) or `execute` (run curl to mark read without opening a browser)

Runtime commands (stdin):
- `read <uid>` mark one UID as read
- `readall` mark all as read
- `status` show unread counts

Local dashboard:
- Open `http://127.0.0.1:8765/?token=...` printed at startup
- You can mark one UID or all as read in the browser

Menu bar tool:
1. Install extra dependency:
```bash
pip install rumps
```
2. Run after main.py:
```bash
python3 menubar.py
```
You will see a menu bar item `Bili`. It shows total unread and lets you click a name to mark read.

App bundle (double click):
1. Install build tool:
```bash
pip install py2app
```
2. Build:
```bash
python3 setup.py py2app
```
3. Run the app:
```
dist/B站关注通知.app
```

Build with venv (recommended):
```bash
tools/build_app.sh
```
This will install dependencies from `requirements.txt` into `.venv` before building.
Default build uses alias mode (`py2app -A`) to avoid dependency bundling errors on Python 3.13.
If you want a standalone bundle, run:
```bash
BUILD_MODE=standalone tools/build_app.sh
```

Icon:
```bash
python3 tools/make_icon.py
```
Then rebuild the app to include `BiliNotify.icns`.

Config location (app mode):
```
~/Library/Application Support/B站关注通知/config.json
```
On first launch, the app will copy `config.app.example.json` into this path automatically.
If main process fails to start due to missing modules, set:
```
"python_path": "/Users/shio/My/Work/Workspace/Python/bilibiliMessage/.venv/bin/python"
```
If app can't find `terminal-notifier` (common in app sandbox PATH), set:
```
"notify_backend": "terminal-notifier",
"terminal_notifier_path": "/opt/homebrew/bin/terminal-notifier"
```
Or use:
```
"notify_backend": "osascript"
```
QR login:
- `auto_open_qr: true` will open the QR PNG automatically

Autostart (login item):
```bash
python3 tools/install_autostart.py /Applications/B站关注通知.app
```
To remove:
```bash
python3 tools/uninstall_autostart.py
```

## Run

```bash
python3 main.py
```

When prompted, scan the QR code using the Bilibili app.

## How it works

- Polls each UID every 1 minute
- If new dynamics appear, it keeps sending a notification every 1 minute
- Click the notification to mark as read
- Mode 1 saves history; mode 2 does not
  - Mode 1 uses `state.json` in the project directory
  - First run with mode 1 sets the baseline to current latest to avoid old spam

## Notes

- The click action opens a local URL to mark read.
- If QR code expires, restart the program.
