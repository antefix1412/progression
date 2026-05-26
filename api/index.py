#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from zoneinfo import ZoneInfo
import re
from urllib.parse import parse_qs

from cache_store import get_cached_results, set_cached_results
from ping import CLUB_ID, SORT_PARAM, get_club_player_urls, scrape_club_players, scrape_player_urls

DEFAULT_BATCH_SIZE = 8


def players_payload(query: str) -> tuple[dict, int]:
    params = parse_qs(query)
    club_id = params.get("club_id", [CLUB_ID])[0].strip()

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400

    try:
        cached = get_cached_results()
    except Exception as exc:
        return {"error": f"Impossible de lire le cache Supabase: {exc}"}, 502

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
    offset = int(params.get("offset", ["0"])[0] or 0)
    batch_size = int(params.get("batch_size", [str(DEFAULT_BATCH_SIZE)])[0] or DEFAULT_BATCH_SIZE)

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400

    try:
        player_urls = get_club_player_urls(club_id=club_id, sort_param=sort_param)
        total = len(player_urls)
        batch_urls = player_urls[offset : offset + batch_size]
        players = scrape_player_urls(batch_urls)
    except Exception as exc:
        return {"error": f"Impossible de récupérer les données PingPocket: {exc}"}, 502

    next_offset = min(offset + batch_size, total)
    return {
        "club_id": club_id,
        "players": [player.to_dict() for player in players],
        "offset": offset,
        "next_offset": next_offset,
        "total": total,
        "done": next_offset >= total,
    }, 200


def save_payload(body: dict) -> tuple[dict, int]:
    club_id = str(body.get("club_id", CLUB_ID)).strip()
    players = body.get("players", [])

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400
    if not isinstance(players, list):
        return {"error": "Le champ players doit être une liste."}, 400

    try:
        payload = {
            "club_id": club_id,
            "players": players,
            "updated_at": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
            "empty_cache": False,
        }
        set_cached_results(payload)
    except Exception as exc:
        return {"error": f"Impossible de sauvegarder dans Supabase: {exc}"}, 502

    return payload, 200


def cron_payload(query: str = "") -> tuple[dict, int]:
    params = parse_qs(query)
    club_id = params.get("club_id", [CLUB_ID])[0].strip()
    sort_param = params.get("sort", [SORT_PARAM])[0].strip() or SORT_PARAM

    try:
        players = scrape_club_players(club_id=club_id, sort_param=sort_param)
    except Exception as exc:
        return {"error": f"Impossible de récupérer les données PingPocket: {exc}"}, 502

    payload, status = save_payload({
        "club_id": club_id,
        "players": [player.to_dict() for player in players],
    })
    if status != 200:
        return payload, status

    return {
        "success": True,
        "updated_at": payload["updated_at"],
        "players_count": len(payload["players"]),
    }, 200
