#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from api.index import cron_payload, players_payload, refresh_payload
from ping import CLUB_ID

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def load_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_template("index.html")
            return

        if parsed.path == "/api/players":
            payload, status = players_payload(parsed.query)
            self.send_json(payload, status)
            return

        if parsed.path == "/api/refresh":
            payload, status = refresh_payload(parsed.query)
            self.send_json(payload, status)
            return

        if parsed.path == "/api/cron":
            payload, status = cron_payload(parsed.query)
            self.send_json(payload, status)
            return

        if parsed.path.startswith("/static/"):
            self.send_static(parsed.path.removeprefix("/static/"))
            return

        self.send_error(404, "Page introuvable")

    def send_template(self, filename: str) -> None:
        path = TEMPLATES_DIR / filename
        if not path.exists():
            self.send_error(404, "Template introuvable")
            return

        body = path.read_text(encoding="utf-8").replace("__CLUB_ID__", CLUB_ID)
        self.send_bytes(body.encode("utf-8"), "text/html; charset=utf-8")

    def send_static(self, relative_path: str) -> None:
        path = (STATIC_DIR / relative_path).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(403, "Chemin interdit")
            return

        if not path.is_file():
            self.send_error(404, "Fichier introuvable")
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(path.read_bytes(), content_type)

    def send_json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_bytes(self, content: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    load_env()
    host = os.environ.get("HOST", "127.0.0.1")
    port = env_int("PORT", 8000)

    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Application disponible sur http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
