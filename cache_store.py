#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path
from typing import Optional

import requests

CACHE_KEY = "pingpocket:players"
LOCAL_CACHE_PATH = Path(__file__).resolve().parent / "ping_cache.json"


def _redis_env() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("KV_REST_API_URL"), os.environ.get("KV_REST_API_TOKEN")


def _redis_command(*command: str) -> object:
    url, token = _redis_env()
    if not url or not token:
        raise RuntimeError("Redis REST env vars are missing")

    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=list(command),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result")


def get_cached_results() -> Optional[dict]:
    url, token = _redis_env()
    if url and token:
        raw = _redis_command("GET", CACHE_KEY)
        return json.loads(raw) if raw else None

    if not LOCAL_CACHE_PATH.exists():
        return None
    return json.loads(LOCAL_CACHE_PATH.read_text(encoding="utf-8"))


def set_cached_results(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    url, token = _redis_env()
    if url and token:
        _redis_command("SET", CACHE_KEY, serialized)
        return

    LOCAL_CACHE_PATH.write_text(serialized, encoding="utf-8")
