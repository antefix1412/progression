#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from zoneinfo import ZoneInfo
import re
from urllib.parse import parse_qs

from cache_store import get_cached_results, set_cached_results
from ping import CLUB_ID, SORT_PARAM, scrape_club_players


def players_payload(query: str) -> tuple[dict, int]:
    params = parse_qs(query)
    club_id = params.get("club_id", [CLUB_ID])[0].strip()

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400

    cached = get_cached_results()
    if not cached:
        return {
            "club_id": club_id,
            "players": [],
            "updated_at": None,
            "empty_cache": True,
        }, 200

    return cached, 200


def refresh_payload(query: str = "") -> tuple[dict, int]:
    params = parse_qs(query)
    club_id = params.get("club_id", [CLUB_ID])[0].strip()
    sort_param = params.get("sort", [SORT_PARAM])[0].strip() or SORT_PARAM

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400

    try:
        players = scrape_club_players(club_id=club_id, sort_param=sort_param)
    except Exception as exc:
        return {"error": f"Impossible de récupérer les données PingPocket: {exc}"}, 502

    payload = {
        "club_id": club_id,
        "players": [player.to_dict() for player in players],
        "updated_at": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
        "empty_cache": False,
    }
    set_cached_results(payload)
    return payload, 200


def cron_payload(query: str = "") -> tuple[dict, int]:
    payload, status = refresh_payload(query)
    if status != 200:
        return payload, status

    return {
        "success": True,
        "updated_at": payload["updated_at"],
        "players_count": len(payload["players"]),
    }, 200
