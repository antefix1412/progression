#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            from api.index import save_payload

            length = int(self.headers.get("Content-Length", "0") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            payload, status = save_payload(body)
        except Exception as exc:
            payload, status = {"error": f"Erreur serveur: {exc}"}, 500

        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
