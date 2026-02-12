#!/usr/bin/env python3
import json
import os
import sys
import time
import subprocess
from datetime import datetime

import requests
import rumps

APP_DISPLAY_NAME = "B站关注通知"
APP_VERSION = "1.1.0"
APP_DIR = os.path.join(
    os.path.expanduser("~"),
    "Library",
    "Application Support",
    APP_DISPLAY_NAME,
)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
TOKEN_FILE = os.path.join(APP_DIR, "token.txt")
LOG_FILE = os.path.join(APP_DIR, "main.log")
PID_FILE = os.path.join(APP_DIR, "main.pid")
STATE_FILE = os.path.join(APP_DIR, "state.json")
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765


def load_config():
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        try:
            project_cfg = os.path.abspath("config.json")
            if os.path.exists(project_cfg):
                try:
                    with open(project_cfg, "r", encoding="utf-8") as fproj:
                        proj_data = json.load(fproj)
                    if proj_data.get("use_project_config_as_default") is True:
                        with open(project_cfg, "r", encoding="utf-8") as fproj_raw:
                            content = fproj_raw.read()
                        with open(CONFIG_FILE, "w", encoding="utf-8") as fdst:
                            fdst.write(content)
                        return json.loads(content)
                except Exception:
                    pass

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
            proc = subprocess.Popen(
                [py, script],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        try:
            with open(PID_FILE, "w", encoding="utf-8") as f:
                f.write(str(proc.pid))
        except Exception:
            pass
        return True
    except Exception:
        return False


def stop_main_process():
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
    except Exception:
        pass
    try:
        os.remove(PID_FILE)
    except Exception:
        pass


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
        self.last_total = 0
        self.next_refresh_ts = None
        self.refresh_interval = 60
        self.menu = [
            rumps.MenuItem(f"Version {APP_VERSION}"),
            None,
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            rumps.MenuItem("Start Monitor", callback=self.start_monitor),
            rumps.MenuItem("Edit Config", callback=self.edit_config),
            rumps.MenuItem("View Logs", callback=self.view_logs),
            rumps.MenuItem("已读时间点", callback=self.show_last_seen_times),
            rumps.MenuItem("Refresh", callback=self.refresh),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self.timer = rumps.Timer(self.refresh, self.refresh_interval)
        self.timer.start()
        self.countdown_timer = rumps.Timer(self._tick, 1)
        self.countdown_timer.start()
        self.refresh(None)

    def quit_app(self, _):
        stop_main_process()
        if os.path.exists(LOG_FILE):
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass
        rumps.quit_application()

    def show_last_seen_times(self, _):
        if not os.path.exists(STATE_FILE):
            rumps.alert("暂无已读时间点记录")
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            last_seen_ts = state_data.get("last_seen_ts", {})
            if not last_seen_ts:
                rumps.alert("暂无已读时间点记录")
                return
            lines = []
            for uid, ts in last_seen_ts.items():
                try:
                    time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    lines.append(f"UID: {uid}\n时间: {time_str}")
                except Exception:
                    lines.append(f"UID: {uid}\n时间: 无效时间戳")
            message = "\n\n".join(lines)
            rumps.alert(title="已读时间点", message=message)
        except Exception as e:
            rumps.alert(f"读取已读时间点失败: {str(e)}")

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

    def view_logs(self, _):
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(LOG_FILE):
            # create empty log so tail works
            with open(LOG_FILE, "a", encoding="utf-8"):
                pass
        cmd = f'tell application "Terminal" to do script "tail -f \\"{LOG_FILE}\\""'
        try:
            subprocess.run(["/usr/bin/osascript", "-e", cmd], check=False)
        except Exception:
            rumps.alert("Failed to open Terminal for logs.")

    def refresh(self, _):
        cfg = load_config()
        global SERVER_PORT
        SERVER_PORT = int(cfg.get("port", SERVER_PORT))
        interval = int(cfg.get("poll_seconds", self.refresh_interval))
        if interval != self.refresh_interval:
            self.refresh_interval = interval
            self.timer.interval = interval
        if not self.token:
            self.token = read_token()

        if not is_server_up(self.token):
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
            self.next_refresh_ts = time.time() + self.refresh_interval
        except Exception:
            self.title = "B站(!)"
            self._render_items([])

    def _render_items(self, items):
        fixed = [
            f"Version {APP_VERSION}",
            "Open Dashboard",
            "Start Monitor",
            "Edit Config",
            "View Logs",
            "已读时间点",
            "Refresh",
            "Quit",
        ]
        for key in list(self.menu.keys()):
            if key not in fixed:
                del self.menu[key]

        self.items = items
        total = sum(int(x.get("count", 0)) for x in items)
        self.last_total = total
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

    def _tick(self, _):
        if not self.next_refresh_ts:
            return
        remaining = max(0, int(self.next_refresh_ts - time.time()))
        base = f"B站({self.last_total})" if self.last_total else "B站"
        self.title = f"{base} {remaining}s"


if __name__ == "__main__":
    BiliMenuApp().run()
