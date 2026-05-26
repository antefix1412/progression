#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from zoneinfo import ZoneInfo

from cache_store import set_cached_results
from ping import CLUB_ID, SORT_PARAM, scrape_club_players


def main() -> None:
    players = scrape_club_players(club_id=CLUB_ID, sort_param=SORT_PARAM)
    payload = {
        "club_id": CLUB_ID,
        "players": [player.to_dict() for player in players],
        "updated_at": datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
        "empty_cache": False,
    }
    set_cached_results(payload)
    print(f"{len(players)} joueur(s) sauvegardé(s)")


if __name__ == "__main__":
    main()
