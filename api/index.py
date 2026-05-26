#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from urllib.parse import parse_qs

from ping import CLUB_ID, SORT_PARAM, scrape_club_players


def players_payload(query: str) -> tuple[dict, int]:
    params = parse_qs(query)
    club_id = params.get("club_id", [CLUB_ID])[0].strip()
    sort_param = params.get("sort", [SORT_PARAM])[0].strip() or SORT_PARAM

    if not re.fullmatch(r"\d+", club_id):
        return {"error": "L'ID club doit contenir uniquement des chiffres."}, 400

    try:
        players = scrape_club_players(club_id=club_id, sort_param=sort_param)
    except Exception as exc:
        return {"error": f"Impossible de récupérer les données PingPocket: {exc}"}, 502

    return {
        "club_id": club_id,
        "players": [player.to_dict() for player in players],
    }, 200
