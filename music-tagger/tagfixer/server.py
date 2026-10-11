"""Tiny local web server for the TagFixer interface (standard library only)."""

import json
import os
import string
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .app import App

STATIC = os.path.join(os.path.dirname(__file__), "static")


def list_dir(path):
    """Folders inside ``path`` for the folder picker."""
    if not path:
        if sys.platform == "win32":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return {"path": "", "parent": None, "dirs": drives}
        path = os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(path))
    try:
        dirs = sorted((d for d in os.listdir(path)
                       if not d.startswith(".") and os.path.isdir(os.path.join(path, d))),
                      key=str.lower)
    except OSError as e:
        return {"path": path, "parent": os.path.dirname(path), "dirs": [], "error": str(e)}
    parent = os.path.dirname(path)
    if parent == path:
        parent = "" if sys.platform == "win32" else None
    return {"path": path, "parent": parent, "dirs": dirs}


LOCAL_NAMES = {"localhost", "127.0.0.1", "[::1]"}


def make_handler(app, local_only=True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep the terminal quiet

        def _host_ok(self):
            # Guards against "DNS rebinding" tricks by other websites when we
            # are only meant to be reachable from this computer.
            if not local_only:
                return True
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
            return host in LOCAL_NAMES

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "forbidden"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path in ("/", "/index.html"):
                    with open(os.path.join(STATIC, "index.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/state":
                    return self._send(200, app.state(int(q.get("since", 0))))
                if url.path == "/api/album":
                    return self._send(200, app.album_detail(q["id"]))
                if url.path == "/api/settings":
                    return self._send(200, app.settings)
                if url.path == "/api/browse":
                    return self._send(200, list_dir(q.get("path", "")))
                return self._send(404, {"error": "not found"})
            except KeyError:
                return self._send(404, {"error": "not found"})
            except Exception as e:
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            # Only accept requests from our own page (blocks other websites
            # from poking the local server via the browser).
            if self.headers.get("X-TagFixer") != "1" or not self._host_ok():
                return self._send(403, {"error": "forbidden"})
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/scan":
                    app.start_scan(body.get("path"))
                    return self._send(200, {"ok": True})
                if url.path == "/api/retry":
                    return self._send(200, {"count": app.retry_pending()})
                if url.path == "/api/stop":
                    app.stop()
                    return self._send(200, {"ok": True})
                if url.path == "/api/select":
                    app.set_selected(body.get("ids", []), body.get("selected", True))
                    return self._send(200, {"ok": True})
                if url.path == "/api/choose":
                    app.choose_release(body["id"], body.get("release", ""))
                    return self._send(200, app.album_detail(body["id"]))
                if url.path == "/api/apply":
                    return self._send(200, {"count": app.start_apply()})
                if url.path == "/api/undo":
                    return self._send(200, {"count": app.undo()})
                if url.path == "/api/settings":
                    return self._send(200, app.update_settings(body))
                return self._send(404, {"error": "not found"})
            except (ValueError, RuntimeError, KeyError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def serve(host="127.0.0.1", port=8765, open_browser=True, app=None):
    app = app or App()
    local_only = host in ("127.0.0.1", "localhost", "::1")
    server = ThreadingHTTPServer((host, port), make_handler(app, local_only))
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0", "") else host
    url = f"http://{shown}:{port}/"
    print(f"TagFixer is running at {url}")
    if not local_only:
        print("Warning: reachable from other machines on your network. Anyone who can reach "
              "this port can browse folders and change tags.")
    print("Press Ctrl+C to quit.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        server.server_close()
