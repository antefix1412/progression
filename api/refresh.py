#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from api.index import refresh_payload


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload, status = refresh_payload(urlparse(self.path).query)
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
