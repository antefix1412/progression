#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Outil de debug FFTT.

Ce script:
1) appelle un endpoint XML FFTT avec les paramètres d'auth,
2) affiche le XML brut,
3) affiche pour chaque enregistrement la correspondance champ -> valeur.

Exemples:
  python test_api.py --endpoint xml_joueur.php --base www --licence 358240
  python test_api.py --endpoint xml_licence_b.php --club 03350022 --save xml_licence_b.xml
  python test_api.py --endpoint xml_club_b.php --nom VERN
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET

import requests

sys.path.append(os.getcwd())

try:
    from api.index import generate_auth_params
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)


BASES = {
    "apiv2": "https://apiv2.fftt.com/mobile/pxml/",
    "www": "https://www.fftt.com/mobile/pxml/",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Inspecter les réponses XML de l'API FFTT")
    parser.add_argument("--endpoint", default="xml_joueur.php", help="Endpoint FFTT (ex: xml_joueur.php)")
    parser.add_argument("--base", choices=["apiv2", "www"], default="www", help="Base URL FFTT")
    parser.add_argument("--licence", help="Numéro de licence")
    parser.add_argument("--club", help="Numéro de club")
    parser.add_argument("--nom", help="Nom pour la recherche club")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout HTTP en secondes")
    parser.add_argument("--save", help="Chemin de sauvegarde du XML brut")
    parser.add_argument("--no-raw", action="store_true", help="N'affiche pas le XML brut")
    return parser.parse_args()


def build_params(args):
    params = generate_auth_params()

    if args.licence:
        params["licence"] = args.licence
        # xml_joueur utilise souvent auto=1
        params.setdefault("auto", "1")
    if args.club:
        params["club"] = args.club
    if args.nom:
        params["nom"] = args.nom

    return params


def print_records(root):
    # Cas standard FFTT: <liste><joueur>...</joueur></liste>
    records = list(root)
    if not records:
        records = [root]

    print("\n=== Champs disponibles ===")
    all_fields = sorted({child.tag for rec in records for child in list(rec)})
    for field in all_fields:
        print(f"- {field}")

    print("\n=== Valeurs par enregistrement ===")
    for idx, rec in enumerate(records, start=1):
        print(f"\n[{idx}] type={rec.tag}")
        children = list(rec)
        if not children:
            value = (rec.text or "").strip()
            print(f"{rec.tag}: {value}")
            continue

        for child in children:
            value = (child.text or "").strip()
            print(f"{child.tag}: {value}")


def main():
    args = parse_args()
    params = build_params(args)
    base_url = BASES[args.base]
    url = f"{base_url}{args.endpoint}"

    print(f"URL: {url}")
    print(f"Params: {params}")

    response = requests.get(url, params=params, timeout=args.timeout)
    response.encoding = "latin-1"

    print(f"Status: {response.status_code}")

    raw_xml = response.text
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(raw_xml)
        print(f"XML sauvegardé dans: {args.save}")

    if not args.no_raw:
        print("\n=== XML brut ===")
        print(raw_xml)

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        print(f"\nErreur parse XML: {exc}")
        return

    print_records(root)


if __name__ == "__main__":
    main()
