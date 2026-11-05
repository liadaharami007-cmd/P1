"""שרת חנות מקומי לבדיקות אוטומטיות בלבד (לא חלק מהמוצר)."""
from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/index"
        if path == "/collections/all":
            path = "/collections_all"
        return str(Path(self.directory) / (path.lstrip("/") + ".html"))

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


def start(name: str) -> tuple[str, ThreadingHTTPServer]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(FIXTURES / name)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/", srv
