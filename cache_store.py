#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Optional

LOCAL_CACHE_PATH = Path(__file__).resolve().parent / "ping_cache.json"


def get_cached_results() -> Optional[dict]:
    if not LOCAL_CACHE_PATH.exists():
        return None
    return json.loads(LOCAL_CACHE_PATH.read_text(encoding="utf-8"))


def set_cached_results(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    LOCAL_CACHE_PATH.write_text(serialized, encoding="utf-8")
