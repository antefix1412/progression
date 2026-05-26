#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from api.index import cron_payload


def is_authorized(headers) -> bool:
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    return headers.get("Authorization") == f"Bearer {secret}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not is_authorized(self.headers):
            self.send_response(401)
            self.end_headers()
            return

        payload, status = cron_payload(urlparse(self.path).query)
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
