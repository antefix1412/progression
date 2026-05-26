#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
from dataclasses import dataclass
from dataclasses import asdict
from typing import List, Optional

import requests

BASE_URL = "https://www.pingpocket.fr"
CLUB_ID = "03350022"
SORT_PARAM = "MONTHLY_POINTS"
REQUEST_TIMEOUT = 30
REQUEST_SLEEP_SECONDS = 0.8
MAX_RETRIES = 8
RETRY_BACKOFF_SECONDS = 1.5
DEBUG_DUMP_HTML = True

SESSION = requests.Session()


@dataclass
class PlayerPoints:
    licence: str
    nom: str
    prenom: str
    points_officiels: float
    points_calcules: float

    @property
    def progression(self) -> float:
        return self.points_calcules - self.points_officiels

    def to_dict(self) -> dict:
        data = asdict(self)
        data["progression"] = self.progression
        return data


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": BASE_URL + "/",
    }
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
    response.raise_for_status()
    return response.text


def fetch_fragment(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html, */*;q=0.9",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Referer": BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
    }
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        if DEBUG_DUMP_HTML:
            print(f"GET {url} -> {response.status_code} {response.url}")
        if response.status_code == 429:
            last_error = response
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue
        response.raise_for_status()
        return response.text

    if last_error is not None:
        last_error.raise_for_status()
    raise requests.HTTPError(f"Failed to fetch {url}")


def build_page_url(path: str) -> str:
    path = path.lstrip("/")
    return f"{BASE_URL}/{path}"


def extract_player_links(html: str, club_id: str) -> List[str]:
    pattern = re.compile(r"/app/fftt/licencies/(\d+)\?CLUB_ID=" + re.escape(club_id))
    licences = sorted(set(pattern.findall(html)))
    return [build_page_url(f"app/fftt/licencies/{lic}?CLUB_ID={club_id}") for lic in licences]


def extract_heading(html: str) -> Optional[str]:
    match = re.search(r"<h1[^>]*>([^<]+)</h1>", html, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def extract_series_points(html: str) -> Optional[List[float]]:
    values = []

    js_numbers = re.findall(r"y:\+\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)\.toFixed", html)
    if not js_numbers:
        js_numbers = re.findall(r"y:\s*([0-9]+(?:\.[0-9]+)?)", html)

    for raw in js_numbers:
        try:
            parsed = float(raw)
        except ValueError:
            continue
        if 300 <= parsed <= 3000:
            values.append(parsed)

    return values or None


def split_name(full_name: str) -> (str, str):
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], ""
    prenom = parts[-1]
    nom = " ".join(parts[:-1])
    return nom, prenom


def parse_player_page(url: str) -> Optional[PlayerPoints]:
    html = fetch_fragment(url)
    heading = extract_heading(html)
    if not heading:
        return None

    series = extract_series_points(html)
    if not series:
        return None

    points_officiels = series[0]
    points_calcules = series[-1]

    nom, prenom = split_name(heading)
    licence_match = re.search(r"/licencies/(\d+)\?CLUB_ID=", url)
    licence = licence_match.group(1) if licence_match else ""

    return PlayerPoints(
        licence=licence,
        nom=nom,
        prenom=prenom,
        points_officiels=points_officiels,
        points_calcules=points_calcules,
    )


def format_progression(value: float) -> str:
    return f"+{value:.1f}" if value >= 0 else f"{value:.1f}"


def scrape_club_players(
    club_id: str = CLUB_ID,
    sort_param: str = SORT_PARAM,
    limit: Optional[int] = None,
) -> List[PlayerPoints]:
    SESSION.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    club_url = build_page_url(f"app/fftt/clubs/{club_id}/licencies?SORT={sort_param}")
    listing_html = fetch_fragment(club_url)
    player_urls = extract_player_links(listing_html, club_id)

    if not player_urls:
        if DEBUG_DUMP_HTML:
            with open("pingpocket_listing.html", "w", encoding="utf-8") as file_handle:
                file_handle.write(listing_html)
        return []

    players: List[PlayerPoints] = []
    for idx, url in enumerate(player_urls, start=1):
        licence_match = re.search(r"/licencies/(\d+)", url)
        if not licence_match:
            continue
        licence = licence_match.group(1)
        classement_url = build_page_url(
            f"app/fftt/licencies/{licence}/graphiques/journee/classement"
        )
        player = parse_player_page(classement_url)
        if player:
            players.append(player)
            if limit is not None and len(players) >= limit:
                break
        elif DEBUG_DUMP_HTML and idx == 1:
            html = fetch_fragment(classement_url)
            with open("pingpocket_classement_sample.html", "w", encoding="utf-8") as file_handle:
                file_handle.write(html)
        time.sleep(REQUEST_SLEEP_SECONDS)

    return players


def main() -> None:
    players = scrape_club_players()

    if not players:
        print("Aucun joueur trouvé sur la page PingPocket.")
        return

    print(f"Joueurs détectés: {len(players)}")

    print("Prenom\tNom\tPoints officiels\tPoints calcules\tProgression")
    print("-" * 80)
    for player in players:
        print(
            f"{player.prenom}\t{player.nom}\t{player.points_officiels:.1f}"
            f"\t{player.points_calcules:.1f}\t{format_progression(player.progression)}"
        )


if __name__ == "__main__":
    main()
