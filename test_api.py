#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Outil de debug FFTT.

Ce script:
1) appelle un ou plusieurs endpoints XML FFTT avec les paramètres d'auth,
2) affiche le XML brut,
3) affiche pour chaque enregistrement la correspondance champ -> valeur.

Exemples:
  python test_api.py --endpoint xml_joueur.php --base www --licence 358240
  python test_api.py --endpoint xml_licence_b.php --club 03350022 --save xml_licence_b.xml
  python test_api.py --endpoint xml_club_b.php --nom VERN
    python test_api.py --all-endpoints --licence 358240 --club 03350022 --nom VERN --out-dir outputs
"""

import argparse
import json
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
    parser.add_argument("--all-endpoints", action="store_true", help="Appelle automatiquement xml_joueur, xml_licence_b et xml_club_b")
    parser.add_argument("--licence", help="Numéro de licence")
    parser.add_argument("--club", help="Numéro de club")
    parser.add_argument("--nom", help="Nom pour la recherche club")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout HTTP en secondes")
    parser.add_argument("--save", help="Chemin de sauvegarde du XML brut")
    parser.add_argument("--out-dir", help="Dossier de sortie pour sauvegarder chaque XML en mode --all-endpoints")
    parser.add_argument("--no-raw", action="store_true", help="N'affiche pas le XML brut")
    parser.add_argument("--limit-records", type=int, default=0, help="Limite le nombre d'enregistrements affichés (0 = tous)")
    parser.add_argument("--player-full", action="store_true", help="Récupère toutes les données joueur disponibles pour une licence")
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


def endpoint_params(endpoint, licence, club, nom):
    if endpoint == "xml_joueur.php":
        return {"licence": licence, "auto": "1"}
    if endpoint == "xml_licence_b.php":
        return {"club": club}
    if endpoint == "xml_club_b.php":
        return {"nom": nom}
    return {}


def parse_xml_records(raw_xml):
    root = ET.fromstring(raw_xml)
    records = []
    for item in list(root):
        row = {}
        for child in list(item):
            row[child.tag] = (child.text or "").strip()
        if row:
            records.append(row)
    return records, root.tag


def fetch_player_full(args):
    licence = args.licence or "3533138"
    auth_params = generate_auth_params()

    targets = [
        {
            "key": "joueur",
            "base": "www",
            "endpoint": "xml_joueur.php",
            "params": {"licence": licence, "auto": "1"},
        },
        {
            "key": "licence",
            "base": "apiv2",
            "endpoint": "xml_licence.php",
            "params": {"licence": licence},
        },
        {
            "key": "licence_b",
            "base": "apiv2",
            "endpoint": "xml_licence_b.php",
            "params": {"licence": licence},
        },
        {
            "key": "liste_joueur_o",
            "base": "apiv2",
            "endpoint": "xml_liste_joueur_o.php",
            "params": {"licence": licence, "valid": "0"},
        },
        {
            "key": "partie_mysql",
            "base": "www",
            "endpoint": "xml_partie_mysql.php",
            "params": {"licence": licence},
        },
        {
            "key": "partie_spid",
            "base": "apiv2",
            "endpoint": "xml_partie.php",
            "params": {"numlic": licence},
        },
        {
            "key": "histo_classement",
            "base": "apiv2",
            "endpoint": "xml_histo_classement.php",
            "params": {"numlic": licence},
        },
    ]

    output = {
        "licence": licence,
        "sources": [target["key"] for target in targets],
        "data": {},
    }

    for target in targets:
        try:
            raw_xml = call_endpoint(
                base=target["base"],
                endpoint=target["endpoint"],
                auth_params=auth_params,
                extra_params=target["params"],
                timeout=args.timeout,
            )
        except requests.RequestException as exc:
            output["data"][target["key"]] = {
                "endpoint": target["endpoint"],
                "params": target["params"],
                "error": str(exc),
            }
            continue

        try:
            records, root_tag = parse_xml_records(raw_xml)
            fields = sorted({field for row in records for field in row.keys()})
            output["data"][target["key"]] = {
                "endpoint": target["endpoint"],
                "params": target["params"],
                "root": root_tag,
                "count": len(records),
                "fields": fields,
                "records": records,
            }
        except ET.ParseError as exc:
            output["data"][target["key"]] = {
                "endpoint": target["endpoint"],
                "params": target["params"],
                "error": f"Reponse XML invalide: {exc}",
                "raw_preview": raw_xml[:1000],
            }

    print("\n=== JSON complet joueur ===")
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as file_handle:
            json.dump(output, file_handle, ensure_ascii=False, indent=2)
        print(f"JSON sauvegarde dans: {args.save}")


def print_records(root, limit_records=0):
    # Cas standard FFTT: <liste><joueur>...</joueur></liste>
    records = list(root)
    if not records:
        records = [root]

    total_records = len(records)
    shown_records = total_records
    if limit_records and limit_records > 0:
        shown_records = min(total_records, limit_records)
        records = records[:shown_records]

    print("\n=== Champs disponibles ===")
    all_fields = sorted({child.tag for rec in records for child in list(rec)})
    for field in all_fields:
        print(f"- {field}")

    print(f"\nTotal enregistrements: {total_records} | Affiches: {shown_records}")

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


def save_raw_xml(raw_xml, output_path):
    with open(output_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(raw_xml)
    print(f"XML sauvegarde dans: {output_path}")


def call_endpoint(base, endpoint, auth_params, extra_params, timeout):
    base_url = BASES[base]
    url = f"{base_url}{endpoint}"
    params = dict(auth_params)
    params.update(extra_params)

    print("\n" + "=" * 80)
    print(f"Endpoint: {endpoint}")
    print(f"URL: {url}")
    print(f"Params: {params}")

    response = requests.get(url, params=params, timeout=timeout)
    response.encoding = "latin-1"
    print(f"Status: {response.status_code}")
    return response.text


def inspect_xml(raw_xml, show_raw, limit_records):
    if show_raw:
        print("\n=== XML brut ===")
        print(raw_xml)

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        print(f"\nErreur parse XML: {exc}")
        print("Debut de reponse brute:")
        print(raw_xml[:300])
        return

    print_records(root, limit_records=limit_records)


def run_single_endpoint(args):
    auth_params = generate_auth_params()
    dynamic_params = build_params(args)
    raw_xml = call_endpoint(
        base=args.base,
        endpoint=args.endpoint,
        auth_params=auth_params,
        extra_params={k: v for k, v in dynamic_params.items() if k not in auth_params},
        timeout=args.timeout,
    )

    if args.save:
        save_raw_xml(raw_xml, args.save)

    inspect_xml(raw_xml, show_raw=not args.no_raw, limit_records=args.limit_records)


def run_all_endpoints(args):
    licence = args.licence or "358240"
    club = args.club or os.getenv("FFTT_CLUB_NUM") or "03350022"
    nom = args.nom or "VERN"

    targets = [
        {"endpoint": "xml_joueur.php", "base": "www", "params": endpoint_params("xml_joueur.php", licence, club, nom)},
        {"endpoint": "xml_licence_b.php", "base": "apiv2", "params": endpoint_params("xml_licence_b.php", licence, club, nom)},
        {"endpoint": "xml_club_b.php", "base": "apiv2", "params": endpoint_params("xml_club_b.php", licence, club, nom)},
    ]

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)

    auth_params = generate_auth_params()

    for target in targets:
        raw_xml = call_endpoint(
            base=target["base"],
            endpoint=target["endpoint"],
            auth_params=auth_params,
            extra_params=target["params"],
            timeout=args.timeout,
        )

        if args.out_dir:
            output_name = target["endpoint"].replace(".php", ".xml")
            save_raw_xml(raw_xml, os.path.join(args.out_dir, output_name))

        inspect_xml(raw_xml, show_raw=not args.no_raw, limit_records=args.limit_records)


def main():
    args = parse_args()
    if args.player_full:
        fetch_player_full(args)
    elif args.all_endpoints:
        run_all_endpoints(args)
    else:
        run_single_endpoint(args)


if __name__ == "__main__":
    main()
