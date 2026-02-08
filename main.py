#!/usr/bin/env python3
import json
import os
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import requests
import qrcode

APP_NAME = "bilibiliMessage"
APP_DISPLAY_NAME = "B站关注通知"
APP_DIR = os.path.join(
    os.path.expanduser("~"),
    "Library",
    "Application Support",
    APP_DISPLAY_NAME,
)
COOKIE_FILE = os.path.join(APP_DIR, "cookies.json")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "state.json")
TOKEN_FILE = os.path.join(APP_DIR, "token.txt")
POLL_SECONDS = 60  # 1 minute
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
NOTIFIER_BIN = None

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def load_config():
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        # Try to copy bundled example (app mode) or local example (dev)
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
                    print(f"Created {CONFIG_FILE} from {src}")
                    break
        except Exception as e:
            print(f"Failed to create config: {e}")
        if not os.path.exists(CONFIG_FILE):
            print(f"Missing {CONFIG_FILE}. Create it from config.example.json")
            sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cookies(session: requests.Session):
    os.makedirs(APP_DIR, exist_ok=True)
    data = requests.utils.dict_from_cookiejar(session.cookies)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2)


def load_cookies(session: requests.Session):
    if not os.path.exists(COOKIE_FILE):
        return False
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    session.cookies = requests.utils.cookiejar_from_dict(data)
    return True


def find_terminal_notifier(config_path: str = None):
    from shutil import which

    if config_path and os.path.exists(config_path):
        return config_path
    candidate = which("terminal-notifier")
    if candidate:
        return candidate
    for p in ("/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"):
        if os.path.exists(p):
            return p
    return None


def notify(
    title: str,
    message: str,
    open_url: str,
    sender: str = None,
    click_action: str = "open",
    backend: str = "terminal-notifier",
):
    try:
        import subprocess

        if backend == "terminal-notifier" and NOTIFIER_BIN:
            cmd = [
                NOTIFIER_BIN,
                "-title",
                title,
                "-message",
                message,
                "-group",
                APP_NAME,
            ]
            if click_action == "execute":
                cmd.extend(
                    ["-execute", f'/usr/bin/curl -fsS "{open_url}" >/dev/null 2>&1']
                )
            else:
                cmd.extend(["-open", open_url])
            if sender:
                cmd.extend(["-sender", sender])
            res = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"terminal-notifier failed: {res.stderr.strip()}")
        else:
            script = f'display notification \"{message}\" with title \"{title}\"'
            subprocess.run(["/usr/bin/osascript", "-e", script], check=False)
    except Exception as e:
        print(f"Failed to send notification: {e}")


def show_qr_in_terminal(url: str):
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def save_qr_png(url: str, path: str):
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(path)


def login_via_qr(session: requests.Session, config: dict):
    print("Requesting QR code...")
    r = session.get(
        "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"QR generate failed: {data}")
    url = data["data"]["url"]
    qrcode_key = data["data"]["qrcode_key"]

    print("Scan this QR code with the Bilibili app:")
    show_qr_in_terminal(url)
    os.makedirs(APP_DIR, exist_ok=True)
    png_path = os.path.join(APP_DIR, "bili_qr.png")
    try:
        save_qr_png(url, png_path)
        print(f"QR image saved to {png_path}")
        print("If terminal QR is hard to scan, open the PNG file.")
        if config.get("auto_open_qr", True):
            import subprocess

            subprocess.run(["/usr/bin/open", png_path], check=False)
    except Exception as e:
        print(f"Failed to save QR PNG: {e}")
    print(f"Or copy this URL into a QR generator if needed: {url}")

    print("Waiting for scan confirmation...")
    while True:
        time.sleep(2)
        poll = session.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qrcode_key},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        poll.raise_for_status()
        pdata = poll.json()
        if pdata.get("code") != 0:
            raise RuntimeError(f"QR poll failed: {pdata}")
        status = pdata["data"]["code"]
        if status == 0:
            print("Login successful.")
            save_cookies(session)
            return
        if status == 86038:
            raise RuntimeError("QR code expired. Please restart.")
        if status == 86090:
            print("Scanned, please confirm on your phone...")
        elif status == 86101:
            # not scanned yet
            pass


def is_logged_in(session: requests.Session) -> bool:
    r = session.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("code") == 0 and data.get("data", {}).get("isLogin") is True


def fetch_latest_items(session: requests.Session, uid: str):
    params = {
        "host_mid": uid,
        "timezone_offset": -480,
        "features": "itemOpusStyle",
    }
    r = session.get(
        "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
        params=params,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": f"https://space.bilibili.com/{uid}/dynamic",
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Fetch dynamic failed for {uid}: {data}")
    return data.get("data", {}).get("items", [])


def fetch_user_name(session: requests.Session, uid: str):
    r = session.get(
        "https://api.bilibili.com/x/space/acc/info",
        params={"mid": uid},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Fetch user info failed for {uid}: {data}")
    return data.get("data", {}).get("name")


def get_item_tag(item):
    if not isinstance(item, dict):
        return None
    modules = item.get("modules") or {}
    module_tag = modules.get("module_tag") or {}
    return module_tag.get("text")


def latest_non_pinned_id(items):
    for item in items:
        tag = get_item_tag(item)
        if tag != "置顶":
            if isinstance(item, dict):
                return item.get("id_str")
    return None


def collect_new_ids(items, last_seen):
    new_ids = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tag = get_item_tag(item)
        if tag == "置顶":
            continue
        item_id = item.get("id_str")
        if item_id == last_seen:
            break
        if item_id:
            new_ids.append(item_id)
    return new_ids


class ReadState:
    def __init__(self, persist: bool):
        self.lock = threading.Lock()
        self.unread_by_uid = {}
        self.last_seen_by_uid = {}
        self.names_by_uid = {}
        self.token = os.urandom(16).hex()
        self.persist = persist

    def load(self):
        if not self.persist or not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.last_seen_by_uid = data.get("last_seen", {})
            self.unread_by_uid = data.get("unread", {})
            self.names_by_uid = data.get("names", {})
        except Exception as e:
            print(f"Failed to load state: {e}")

    def save(self):
        if not self.persist:
            return
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            data = {
                "last_seen": self.last_seen_by_uid,
                "unread": self.unread_by_uid,
                "names": self.names_by_uid,
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except Exception as e:
            print(f"Failed to save state: {e}")

    def mark_read(self, uid: str):
        with self.lock:
            if uid in self.unread_by_uid:
                del self.unread_by_uid[uid]
        self.save()

    def set_last_seen(self, uid: str, dynamic_id: str):
        with self.lock:
            self.last_seen_by_uid[uid] = dynamic_id
        self.save()

    def get_last_seen(self, uid: str):
        with self.lock:
            return self.last_seen_by_uid.get(uid)

    def add_unread(self, uid: str, ids):
        if not ids:
            return
        with self.lock:
            current = self.unread_by_uid.get(uid, [])
            now = int(time.time())
            current.extend([{"id": x, "ts": now} for x in ids])
            # de-dup by id while preserving order
            seen = set()
            deduped = []
            for x in current:
                if not isinstance(x, dict):
                    continue
                xid = x.get("id")
                if not xid or xid in seen:
                    continue
                seen.add(xid)
                deduped.append(x)
            self.unread_by_uid[uid] = deduped
        self.save()

    def get_unread_uids(self):
        with self.lock:
            return list(self.unread_by_uid.keys())

    def get_unread_count(self, uid: str):
        with self.lock:
            return len(self.unread_by_uid.get(uid, []))

    def set_name(self, uid: str, name: str):
        if not name:
            return
        with self.lock:
            self.names_by_uid[uid] = name
        self.save()

    def get_name(self, uid: str):
        with self.lock:
            return self.names_by_uid.get(uid)

    def get_unread_items(self, uid: str):
        with self.lock:
            return list(self.unread_by_uid.get(uid, []))


class ReadHandler(BaseHTTPRequestHandler):
    state: ReadState = None

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        uid = (qs.get("uid") or [""])[0]
        token = (qs.get("token") or [""])[0]
        if parsed.path == "/":
            if token != self.state.token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                print(f"[read] forbidden token={token} uid={uid}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = ["<html><body><h3>Unread</h3>"]
            body.append('<p><a href="/readall?token=%s">Mark all as read</a></p>' % token)
            for u in self.state.get_unread_uids():
                name = self.state.get_name(u) or u
                count = self.state.get_unread_count(u)
                body.append(
                    f'<div><b>{name}</b> (uid {u}) - {count} '
                    f'<a href="/read?uid={u}&token={token}">Mark read</a></div>'
                )
            body.append("</body></html>")
            self.wfile.write("".join(body).encode("utf-8"))
            return

        if parsed.path == "/status":
            if token != self.state.token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                print(f"[status] forbidden token={token}")
                return
            payload = []
            for u in self.state.get_unread_uids():
                payload.append(
                    {
                        "uid": u,
                        "name": self.state.get_name(u) or u,
                        "count": self.state.get_unread_count(u),
                    }
                )
            body = json.dumps({"items": payload}, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/readall":
            if token != self.state.token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                print(f"[read] forbidden token={token} uid={uid}")
                return
            for u in self.state.get_unread_uids():
                self.state.mark_read(u)
            print("[read] marked all (web)")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h3>Marked all as read. You can close this page.</h3></body></html>"
            )
            return

        if parsed.path == "/read":
            if token != self.state.token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"forbidden")
                print(f"[read] forbidden token={token} uid={uid}")
                return
            if uid:
                self.state.mark_read(uid)
                print(f"[read] marked uid={uid}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h3>Marked as read. You can close this page.</h3></body></html>"
            )
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"not found")

    def log_message(self, format, *args):
        # silence default logging
        return


def start_server(state: ReadState):
    ReadHandler.state = state
    server = HTTPServer((SERVER_HOST, SERVER_PORT), ReadHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def write_token(token: str):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token)
    except Exception as e:
        print(f"Failed to write token file: {e}")


def start_stdin_commands(state: ReadState):
    def run():
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                break
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()
            if cmd == "read" and len(parts) >= 2:
                uid = parts[1]
                state.mark_read(uid)
                print(f"[read] marked uid={uid} (stdin)")
            elif cmd == "readall":
                for uid in state.get_unread_uids():
                    state.mark_read(uid)
                print("[read] marked all (stdin)")
            elif cmd == "status":
                for uid in state.get_unread_uids():
                    print(f"[status] uid={uid} unread={state.get_unread_count(uid)}")
            else:
                print("Commands: read <uid> | readall | status")

    t = threading.Thread(target=run, daemon=True)
    t.start()


def main():
    config = load_config()
    uids = [str(x) for x in config.get("uids", [])]
    sender = config.get("sender")
    mode = int(config.get("mode", 2))
    custom_names = config.get("uid_names", {}) or {}
    click_action = config.get("click_action", "open")
    backend = config.get("notify_backend", "terminal-notifier")
    notifier_path = config.get("terminal_notifier_path")
    global NOTIFIER_BIN
    NOTIFIER_BIN = find_terminal_notifier(notifier_path)
    if backend == "terminal-notifier" and not NOTIFIER_BIN:
        print("terminal-notifier not found in PATH. Falling back to osascript.")
        backend = "osascript"
    if mode not in (1, 2):
        print("Invalid mode in config.json. Use 1 or 2.")
        sys.exit(1)
    if not uids:
        print("No UIDs configured in config.json")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    load_cookies(session)
    if not is_logged_in(session):
        login_via_qr(session, config)
        if not is_logged_in(session):
            print("Login failed. Please try again.")
            sys.exit(1)

    state = ReadState(persist=(mode == 1))
    state.load()
    start_server(state)
    write_token(state.token)
    start_stdin_commands(state)
    print(f"Dashboard: http://{SERVER_HOST}:{SERVER_PORT}/?token={state.token}")
    print(f"Read server: http://{SERVER_HOST}:{SERVER_PORT}/read?uid=<UID>&token=...")

    # Resolve names (custom first, then fetch)
    for uid in uids:
        cname = custom_names.get(uid)
        if cname:
            state.set_name(uid, cname)
            continue
        if not state.get_name(uid):
            try:
                name = fetch_user_name(session, uid)
                if name:
                    state.set_name(uid, name)
            except Exception as e:
                print(f"[name] fetch failed for {uid}: {e}")

    # Initialize last seen and catch up missed updates (mode 1)
    for uid in uids:
        try:
            items = fetch_latest_items(session, uid)
            latest = latest_non_pinned_id(items)
            last_seen = state.get_last_seen(uid)
            if latest and not last_seen:
                # First run: set baseline to avoid old spam
                state.set_last_seen(uid, latest)
            elif latest and last_seen:
                new_ids = collect_new_ids(items, last_seen)
                if new_ids:
                    state.add_unread(uid, new_ids)
                    state.set_last_seen(uid, latest)
            print(f"[init] uid={uid} latest={latest} items={len(items)}")
        except Exception as e:
            print(f"Init fetch failed for {uid}: {e}")

    print("Monitoring started. Press Ctrl+C to stop.")

    while True:
        print(f"[poll] {time.strftime('%Y-%m-%d %H:%M:%S')}")
        for uid in uids:
            try:
                items = fetch_latest_items(session, uid)
                last_seen = state.get_last_seen(uid)
                new_ids = collect_new_ids(items, last_seen)
                if new_ids:
                    state.add_unread(uid, new_ids)
                    newest = latest_non_pinned_id(items)
                    if newest:
                        state.set_last_seen(uid, newest)
                print(
                    f"[uid] {uid} items={len(items)} last_seen={last_seen} new={len(new_ids)}"
                )
            except Exception as e:
                print(f"Fetch failed for {uid}: {e}")

        # Notify for unread
        for uid in state.get_unread_uids():
            count = state.get_unread_count(uid)
            if count <= 0:
                continue
            url = f"http://{SERVER_HOST}:{SERVER_PORT}/read?uid={uid}&token={state.token}"
            name = state.get_name(uid) or uid
            notify(
                title="Bilibili 动态更新",
                message=f"{name} 有 {count} 条新动态，点击标记已读",
                open_url=url,
                sender=sender,
                click_action=click_action,
                backend=backend,
            )
            print(f"[notify] mark url: {url}")
            print(f"[notify] uid={uid} count={count}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
