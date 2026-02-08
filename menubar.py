#!/usr/bin/env python3
import json
import os
import sys
import time
import subprocess

import requests
import rumps

APP_DISPLAY_NAME = "B站关注通知"
APP_DIR = os.path.join(
    os.path.expanduser("~"),
    "Library",
    "Application Support",
    APP_DISPLAY_NAME,
)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
TOKEN_FILE = os.path.join(APP_DIR, "token.txt")
LOG_FILE = os.path.join(APP_DIR, "main.log")
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765


def load_config():
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        try:
            resource = os.environ.get("RESOURCEPATH")
            candidates = []
            if resource:
                candidates.append(os.path.join(resource, "config.app.example.json"))
                candidates.append(os.path.join(resource, "config.example.json"))
            candidates.append(os.path.abspath("config.app.example.json"))
            candidates.append(os.path.abspath("config.example.json"))
            for src in candidates:
                if src and os.path.exists(src):
                    with open(src, "r", encoding="utf-8") as fsrc:
                        content = fsrc.read()
                    with open(CONFIG_FILE, "w", encoding="utf-8") as fdst:
                        fdst.write(content)
                    break
        except Exception:
            pass
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def read_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def status_url(token: str):
    return f"http://{SERVER_HOST}:{SERVER_PORT}/status?token={token}"


def read_url(uid: str, token: str):
    return f"http://{SERVER_HOST}:{SERVER_PORT}/read?uid={uid}&token={token}"


def dashboard_url(token: str):
    return f"http://{SERVER_HOST}:{SERVER_PORT}/?token={token}"


def main_script_path():
    # menubar.py and main.py are in the same folder in source,
    # and both are bundled in the app resources by py2app.
    base = os.path.dirname(os.path.abspath(__file__))
    # App bundle resource path
    try:
        macos_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        res_dir = os.path.abspath(os.path.join(macos_dir, "..", "Resources"))
        candidate = os.path.join(res_dir, "main.py")
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    # Fallback for non-bundled runs
    candidate = os.path.join(base, "main.py")
    if os.path.exists(candidate):
        return candidate
    res_dir2 = os.path.abspath(os.path.join(base, "..", "Resources"))
    candidate = os.path.join(res_dir2, "main.py")
    return candidate


def preferred_python(config):
    py = config.get("python_path")
    if py and os.path.exists(py):
        return py
    # Try venv next to this repo (for dev/alias builds)
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.abspath(os.path.join(base, ".venv", "bin", "python"))
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return sys.executable


def start_main_process():
    os.makedirs(APP_DIR, exist_ok=True)
    script = main_script_path()
    if not os.path.exists(script):
        return False
    try:
        cfg = load_config()
        py = preferred_python(cfg)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            subprocess.Popen(
                [py, script],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        return True
    except Exception:
        return False


def is_server_up(token: str):
    if not token:
        return False
    try:
        r = requests.get(status_url(token), timeout=2)
        return r.status_code == 200
    except Exception:
        return False


class BiliMenuApp(rumps.App):
    def __init__(self):
        super().__init__("B站", quit_button=None)
        self.token = None
        self.items = []
        self.menu = [
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            rumps.MenuItem("Start Monitor", callback=self.start_monitor),
            rumps.MenuItem("Edit Config", callback=self.edit_config),
            rumps.MenuItem("Refresh", callback=self.refresh),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self.timer = rumps.Timer(self.refresh, 30)
        self.timer.start()
        self.refresh(None)

    def quit_app(self, _):
        rumps.quit_application()

    def open_dashboard(self, _):
        if not self.token:
            rumps.alert("Token not found. Start main process first.")
            return
        rumps.open_url(dashboard_url(self.token))

    def start_monitor(self, _):
        if start_main_process():
            rumps.alert("Monitor started.")
            time.sleep(1)
            self.refresh(None)
        else:
            rumps.alert("Failed to start monitor. Check main.log.")

    def edit_config(self, _):
        os.makedirs(APP_DIR, exist_ok=True)
        existing = ""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                existing = f.read()
        resp = rumps.Window(
            title="Edit config.json",
            message="Paste full JSON content for config.json",
            default_text=existing,
            dimensions=(600, 500),
            ok="Save",
            cancel="Cancel",
        ).run()
        if not resp.clicked:
            return
        text = (resp.text or "").strip()
        if not text:
            rumps.alert("Config is empty. Not saved.")
            return
        try:
            json.loads(text)
        except Exception as e:
            rumps.alert(f"Invalid JSON: {e}")
            return
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        rumps.alert("Config saved. Restart if needed.")

    def refresh(self, _):
        if not self.token:
            self.token = read_token()

        if not is_server_up(self.token):
            cfg = load_config()
            if cfg.get("autostart_main", True):
                start_main_process()
                time.sleep(1)
                self.token = read_token()

        if not is_server_up(self.token):
            self.title = "B站(!)"
            self._render_items([])
            return

        try:
            r = requests.get(status_url(self.token), timeout=3)
            if r.status_code != 200:
                self.title = "B站(!)"
                self._render_items([])
                return
            data = r.json()
            items = data.get("items", [])
            self._render_items(items)
        except Exception:
            self.title = "B站(!)"
            self._render_items([])

    def _render_items(self, items):
        fixed = ["Open Dashboard", "Start Monitor", "Edit Config", "Refresh", "Quit"]
        for key in list(self.menu.keys()):
            if key not in fixed:
                del self.menu[key]

        self.items = items
        total = sum(int(x.get("count", 0)) for x in items)
        self.title = f"B站({total})" if total else "B站"

        for item in items:
            uid = item.get("uid")
            name = item.get("name") or uid
            count = item.get("count", 0)
            title = f"{name} ({count})"
            self.menu.insert_before(
                "Open Dashboard", rumps.MenuItem(title, callback=self._make_read(uid))
            )

    def _make_read(self, uid):
        def _cb(_):
            if not self.token:
                return
            try:
                requests.get(read_url(uid, self.token), timeout=3)
            except Exception:
                pass
            self.refresh(None)
        return _cb


if __name__ == "__main__":
    BiliMenuApp().run()
