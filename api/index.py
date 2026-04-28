#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# Ajouter le répertoire parent au PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, make_response
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
import hashlib
import hmac
from datetime import datetime
import logging
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== CONFIG ==========
# Charger les variables d'environnement
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MOTDEPASSE = os.getenv("FFTT_PASSWORD")
ID_APP = os.getenv("FFTT_ID_APP")
SERIE = os.getenv("FFTT_SERIE")
CLUB_NUM = os.getenv("FFTT_CLUB_NUM")
BASE_URL = "https://apiv2.fftt.com/mobile/pxml/"
JOUEUR_BASE_URL = "https://www.fftt.com/mobile/pxml/"
PLAYER_REQUEST_DELAY_SECONDS = 0.5
CLPRO_TIME_BUDGET_SECONDS = 18
CLUB_CALC_TIME_BUDGET_SECONDS = 20
MODE_POINT = "point"
MODE_VALINIT = "valinit"

def get_env(*names):
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


MOTDEPASSE = get_env("FFTT_PASSWORD", "MOTDEPASSE")
ID_APP = get_env("FFTT_ID_APP", "ID_APP")
SERIE = get_env("FFTT_SERIE", "SERIE")
CLUB_NUM = get_env("FFTT_CLUB_NUM", "CLUB_NUM", "NUM_CLUB")
TEST_API_TOKEN = get_env("FFTT_TEST_API_TOKEN", "TEST_API_TOKEN")
DEFAULT_PLAYER_LICENSE = get_env("FFTT_TEST_PLAYER_LICENSE") or "3533138"

HAS_FFTT_AUTH = all([MOTDEPASSE, ID_APP, SERIE])

if not HAS_FFTT_AUTH:
    logging.warning(
        "Variables FFTT manquantes. Definis FFTT_PASSWORD, FFTT_ID_APP et FFTT_SERIE (ou alias MOTDEPASSE, ID_APP, SERIE)."
    )

if not CLUB_NUM:
    logging.warning(
        "Numero de club absent. Definis FFTT_CLUB_NUM (ou alias CLUB_NUM/NUM_CLUB), ou passe ?club=... a l'API."
    )
# ============================

# Calculer les chemins absolus pour templates et static
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class FFTTApiError(Exception):
    pass


PLAYER_FULL_ENDPOINTS = {
    "joueur": {
        "endpoint": "xml_joueur.php",
        "base_url": JOUEUR_BASE_URL,
        "build_params": lambda licence: {"licence": licence, "auto": "1"},
    },
    "licence": {
        "endpoint": "xml_licence.php",
        "base_url": BASE_URL,
        "build_params": lambda licence: {"licence": licence},
    },
    "licence_b": {
        "endpoint": "xml_licence_b.php",
        "base_url": BASE_URL,
        "build_params": lambda licence: {"licence": licence},
    },
    "liste_joueur_o": {
        "endpoint": "xml_liste_joueur_o.php",
        "base_url": BASE_URL,
        "build_params": lambda licence: {"licence": licence, "valid": "0"},
    },
    "partie_mysql": {
        "endpoint": "xml_partie_mysql.php",
        "base_url": JOUEUR_BASE_URL,
        "build_params": lambda licence: {"licence": licence},
    },
    "partie_spid": {
        "endpoint": "xml_partie.php",
        "base_url": BASE_URL,
        "build_params": lambda licence: {"numlic": licence},
    },
    "histo_classement": {
        "endpoint": "xml_histo_classement.php",
        "base_url": BASE_URL,
        "build_params": lambda licence: {"numlic": licence},
    },
}


def normalize_mode(mode_value):
    mode = (mode_value or "").strip().lower()
    if mode == MODE_VALINIT:
        return MODE_VALINIT
    return MODE_POINT


def resolve_club_num(club_num):
    target = (club_num or CLUB_NUM or "").strip()
    if not target:
        raise FFTTApiError(
            "Numero de club manquant. Definis FFTT_CLUB_NUM (ou CLUB_NUM/NUM_CLUB) dans les variables d'environnement Vercel."
        )
    return target


def extract_api_error(root):
    if root is None:
        return None
    if root.tag and root.tag.lower() == "error":
        return (root.text or "").strip() or "Erreur FFTT inconnue"
    error_text = root.findtext("error")
    if error_text:
        return error_text.strip()
    nested_error = root.find(".//error")
    if nested_error is not None:
        return (nested_error.text or "").strip() or "Erreur FFTT inconnue"
    return None


def generate_auth_params():
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    ccle = hashlib.md5(MOTDEPASSE.encode()).hexdigest()
    tmc = hmac.new(ccle.encode(), timestamp.encode(), hashlib.sha1).hexdigest()
    return {'serie': SERIE, 'tm': timestamp, 'tmc': tmc, 'id': ID_APP}


def make_request(
    endpoint,
    additional_params=None,
    timeout=30,
    use_new_session=False,
    close_connection=False,
    base_url=BASE_URL,
):
    if not HAS_FFTT_AUTH:
        raise FFTTApiError(
            "Configuration FFTT manquante. Definis FFTT_PASSWORD, FFTT_ID_APP et FFTT_SERIE dans les variables d'environnement."
        )
    params = generate_auth_params()
    if additional_params:
        params.update(additional_params)
    url = f"{base_url}{endpoint}"
    try:
        headers = {"Connection": "close"} if close_connection else None
        if use_new_session:
            with requests.Session() as session:
                resp = session.get(url, params=params, timeout=timeout, headers=headers)
        else:
            resp = requests.get(url, params=params, timeout=timeout, headers=headers)
        resp.raise_for_status()
        resp.encoding = "latin-1"
        return resp.text
    except requests.RequestException as e:
        message = f"Impossible de joindre l'API FFTT pour {endpoint}: {e}"
        logging.error(message)
        raise FFTTApiError(message) from e


def parse_points(value) -> Optional[int]:
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except (TypeError, ValueError):
        return None


def validate_test_api_token(candidate_token):
    if not TEST_API_TOKEN:
        raise FFTTApiError(
            "Token manquant sur le serveur. Definis FFTT_TEST_API_TOKEN dans les variables d'environnement."
        )
    if not candidate_token:
        raise PermissionError("Paramètre token obligatoire")
    if not hmac.compare_digest(candidate_token, TEST_API_TOKEN):
        raise PermissionError("Token invalide")


def parse_xml_records(content):
    root = ET.fromstring(content)
    api_error = extract_api_error(root)
    if api_error:
        raise FFTTApiError(api_error)

    records = []
    children = list(root)
    if not children:
        return records, root.tag

    for item in children:
        record = {}
        for child in list(item):
            record[child.tag] = (child.text or "").strip()
        if record:
            records.append(record)

    return records, root.tag


def fetch_player_full_data(licence):
    aggregated = {}

    for key, config in PLAYER_FULL_ENDPOINTS.items():
        endpoint = config["endpoint"]
        params = config["build_params"](licence)
        try:
            content = make_request(
                endpoint,
                additional_params=params,
                timeout=25,
                base_url=config["base_url"],
                use_new_session=True,
                close_connection=True,
            )
        except FFTTApiError as exc:
            aggregated[key] = {
                "endpoint": endpoint,
                "params": params,
                "error": str(exc),
            }
            continue

        try:
            records, root_tag = parse_xml_records(content)
            fields = sorted({field for row in records for field in row.keys()})
            aggregated[key] = {
                "endpoint": endpoint,
                "root": root_tag,
                "params": params,
                "count": len(records),
                "fields": fields,
                "records": records,
            }
        except ET.ParseError as exc:
            aggregated[key] = {
                "endpoint": endpoint,
                "params": params,
                "error": f"Reponse XML invalide: {exc}",
                "raw_preview": content[:1000],
            }
        except FFTTApiError as exc:
            aggregated[key] = {
                "endpoint": endpoint,
                "params": params,
                "error": str(exc),
                "raw_preview": content[:1000],
            }

    return aggregated


def get_player_clpro(licence, retries=1):
    last_error = None
    for attempt in range(retries):
        try:
            content = make_request(
                "xml_joueur.php",
                {"licence": licence, "auto": "1"},
                timeout=20,
                use_new_session=True,
                close_connection=True,
                base_url=JOUEUR_BASE_URL,
            )
            root = ET.fromstring(content)
            api_error = extract_api_error(root)
            if api_error:
                raise FFTTApiError(f"Erreur FFTT pour la licence {licence}: {api_error}")

            joueur = root.find(".//joueur")
            if joueur is None:
                raise FFTTApiError(f"Aucune fiche joueur trouvee pour la licence {licence}")

            clpro = parse_points(joueur.findtext("clpro"))
            if clpro is None:
                raise FFTTApiError(f"clpro manquant pour la licence {licence}")
            return clpro
        except (ET.ParseError, FFTTApiError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(PLAYER_REQUEST_DELAY_SECONDS)

    raise FFTTApiError(str(last_error) if last_error else f"Impossible de recuperer clpro pour {licence}")


def get_player_details_xml_joueur(licence):
    content = make_request(
        "xml_joueur.php",
        {"licence": licence, "auto": "1"},
        timeout=20,
        use_new_session=True,
        close_connection=True,
        base_url=JOUEUR_BASE_URL,
    )
    try:
        root = ET.fromstring(content)
        api_error = extract_api_error(root)
        if api_error:
            raise FFTTApiError(f"Erreur FFTT pour la licence {licence}: {api_error}")

        joueur = root.find(".//joueur")
        if joueur is None:
            raise FFTTApiError(f"Aucune fiche joueur trouvee pour la licence {licence}")

        clpro = parse_points(joueur.findtext("clpro"))
        valinit = parse_points(joueur.findtext("valinit"))
        if clpro is None:
            raise FFTTApiError(f"clpro manquant pour la licence {licence}")
        if valinit is None:
            raise FFTTApiError(f"valinit manquant pour la licence {licence}")

        point = parse_points(joueur.findtext("point"))
        
        return {
            "licence": (joueur.findtext("licence") or licence).strip(),
            "nom": (joueur.findtext("nom") or "").strip(),
            "prenom": (joueur.findtext("prenom") or "").strip(),
            "club": (joueur.findtext("club") or "").strip(),
            "nclub": (joueur.findtext("nclub") or "").strip(),
            "point": point,
            "clpro": clpro,
            "valinit": valinit,
            "progression": clpro - valinit,
        }
    except ET.ParseError as exc:
        raise FFTTApiError(f"Reponse XML invalide pour la licence {licence}: {exc}") from exc


def get_club_licence_rows(club_num=None):
    target_club = resolve_club_num(club_num)
    content = make_request("xml_licence_b.php", {"club": target_club})
    try:
        root = ET.fromstring(content)
        api_error = extract_api_error(root)
        if api_error:
            raise FFTTApiError(f"Erreur FFTT pour le club {target_club}: {api_error}")

        licence_rows = []
        for node in root.findall(".//licence"):
            licence_number = node.findtext("licence")
            nom = node.findtext("nom")
            prenom = node.findtext("prenom")
            pointm = parse_points(node.findtext("pointm"))
            initm = parse_points(node.findtext("initm"))

            if not licence_number or not nom or not prenom:
                continue

            if pointm is None or initm is None:
                continue

            licence_rows.append({
                "licence": licence_number.strip(),
                "nom": nom.strip(),
                "prenom": prenom.strip(),
                "pointm": pointm,
                "initm": initm,
            })

        if not licence_rows:
            logging.info(f"Aucun joueur renvoye pour le club {target_club}")
            return [], target_club

        return licence_rows, target_club
    except ET.ParseError as e:
        message = f"Reponse XML invalide pour le club {target_club}: {e}"
        logging.error(f"{message}\n{content}")
        raise FFTTApiError(message) from e


def build_results_point(club_num=None):
    rows, resolved_club = get_club_licence_rows(club_num)
    players = []
    for row in rows:
        players.append({
            "licence": row["licence"],
            "nom": row["nom"],
            "prenom": row["prenom"],
            "points_classement": row["initm"],
            "points_proposes": row["pointm"],
        })

    meta = {
        "mode": MODE_POINT,
        "formula": "pointm - initm (xml_licence_b)",
        "truncated": False,
        "resolved_club": resolved_club,
    }
    return players, meta


def build_results_valinit(club_num=None):
    rows, resolved_club = get_club_licence_rows(club_num)
    if not rows:
        return [], {
            "mode": MODE_VALINIT,
            "formula": "clpro - valinit (xml_joueur)",
            "truncated": False,
            "resolved_club": resolved_club,
        }

    players = []
    errors = []
    last_call_at = None
    started_at = time.monotonic()

    for row in rows:
        if (time.monotonic() - started_at) >= CLPRO_TIME_BUDGET_SECONDS:
            break

        now = time.monotonic()
        if last_call_at is not None:
            remaining = PLAYER_REQUEST_DELAY_SECONDS - (now - last_call_at)
            if remaining > 0:
                time.sleep(remaining)

        try:
            joueur = get_player_details_xml_joueur(row["licence"])
            players.append({
                "licence": row["licence"],
                "nom": row["nom"],
                "prenom": row["prenom"],
                "points_classement": joueur["valinit"],
                "points_proposes": joueur["clpro"],
            })
        except FFTTApiError as exc:
            errors.append(f"{row['licence']}: {exc}")
        finally:
            last_call_at = time.monotonic()

    truncated = len(players) < len(rows)
    if errors:
        logging.warning("%s erreur(s) xml_joueur pour le club %s", len(errors), resolved_club)

    meta = {
        "mode": MODE_VALINIT,
        "formula": "clpro - valinit (xml_joueur)",
        "truncated": truncated,
        "resolved_club": resolved_club,
        "processed": len(players),
        "available": len(rows),
    }
    return players, meta


def search_club_by_name(club_name):
    content = make_request('xml_club_b.php', {'nom': club_name})
    clubs = []
    try:
        root = ET.fromstring(content)
        api_error = extract_api_error(root)
        if api_error:
            raise FFTTApiError(f"Erreur FFTT pour la recherche de club '{club_name}': {api_error}")
        for club in root.findall('club'):
            numero = club.findtext('numero')
            nom = club.findtext('nom')
            ville = club.findtext('ville', default='')
            if numero and nom:
                clubs.append({
                    'numero': numero.strip(),
                    'nom': nom.strip(),
                    'ville': ville.strip()
                })
        logging.info(f"{len(clubs)} clubs trouvés pour '{club_name}'")
    except ET.ParseError as e:
        message = f"Reponse XML invalide pour la recherche de club '{club_name}': {e}"
        logging.error(f"{message}\n{content}")
        raise FFTTApiError(message) from e
    return clubs


# ===== TABLEAU FFTT DE POINTS =====
# Format: (écart_min, écart_max): (victoire_normale, défaite_normale, victoire_anormale, défaite_anormale)
FFTT_POINTS_TABLE = [
    (0, 24, 6, -5, 6, -5),          # écart 0-24
    (25, 49, 5.5, -4.5, 7, -6),     # écart 25-49
    (50, 99, 5, -4, 8, -7),         # écart 50-99
    (100, 149, 4, -3, 10, -8),      # écart 100-149
    (150, 199, 3, -2, 13, -10),     # écart 150-199
    (200, 299, 2, -1, 17, -12.5),   # écart 200-299
    (300, 399, 1, -0.5, 22, -16),   # écart 300-399
    (400, 499, 0.5, 0, 28, -20),    # écart 400-499
    (500, 999999, 0, 0, 40, -29),   # écart 500+
]


def get_base_points_from_table(ecart, resultat):
    """
    Retourne les points de base selon le tableau FFTT.
    
    Args:
        ecart: différence de classement (points adversaire - points joueur)
        resultat: 'V' (victoire) ou 'D' (défaite)
    
    Returns:
        float: points de base (peut être négatif pour défaite)
    """
    # Déterminer si c'est une victoire/défaite exceptionnelle ou normale
    is_exceptional = (resultat == 'V' and ecart > 0) or (resultat == 'D' and ecart < 0)
    
    # Chercher dans la table
    abs_ecart = abs(ecart)
    for ecart_min, ecart_max, vic_norm, def_norm, vic_anom, def_anom in FFTT_POINTS_TABLE:
        if ecart_min <= abs_ecart <= ecart_max:
            if is_exceptional:
                # Victoire exceptionnelle ou défaite anormale
                if resultat == 'V':
                    return vic_anom
                else:
                    return def_anom
            else:
                # Victoire normale ou défaite normale
                if resultat == 'V':
                    return vic_norm
                else:
                    return def_norm
    
    # Fallback (ne devrait pas arriver ici)
    return 0


def calculate_match_points(joueur_points, adversaire_points, resultat, coefchamp):
    """
    Calcule les points gagnés/perdus pour un match.
    
    Args:
        joueur_points: classement du joueur
        adversaire_points: classement de l'adversaire
        resultat: 'V' ou 'D'
        coefchamp: coefficient du championnat (1, 0.75, 1.5, etc.)
    
    Returns:
        float: points du match (peut être négatif)
    """
    if not joueur_points or not adversaire_points:
        return 0
    
    try:
        j_pts = float(joueur_points)
        a_pts = float(adversaire_points)
        coef = float(coefchamp) if coefchamp else 1.0
    except (ValueError, TypeError):
        return 0
    
    ecart = a_pts - j_pts
    base_points = get_base_points_from_table(ecart, resultat)
    final_points = base_points * coef
    
    return round(final_points, 2)


def build_results_with_calculated_points(licence, joueur_points):
    """
    Construit les résultats avec points calculés pour un joueur.
    
    Args:
        licence: numéro de licence du joueur
        joueur_points: classement du joueur (e.g., pointm de licence_b)
    
    Returns:
        dict: agrégation des matches avec points calculés
    """
    try:
        # Récupérer les données complètes du joueur
        full_data = fetch_player_full_data(licence)
        
        # Extraire les données nécessaires
        partie_mysql_records = full_data.get('partie_mysql', {}).get('records', [])
        
        matches_with_points = []
        adversaire_cache = {}  # Cache pour éviter les appels redondants
        
        for match in partie_mysql_records:
            try:
                idpartie = match.get('idpartie', '')
                date = match.get('date', '')
                adversaire = match.get('advnompre', '')
                advlic = match.get('advlic', '')
                resultat = match.get('vd', '')  # 'V' ou 'D'
                coefchamp = match.get('coefchamp', '1')
                
                # Récupérer les points de l'adversaire via xml_joueur (avec cache)
                adversaire_points = None
                if advlic:
                    if advlic not in adversaire_cache:
                        try:
                            adv_joueur = get_player_details_xml_joueur(advlic)
                            # Utiliser le champ 'point' si disponible, sinon 'valinit' en fallback
                            adversaire_points = adv_joueur.get('point') or adv_joueur.get('valinit')
                            adversaire_cache[advlic] = adversaire_points
                            # Petit délai pour ne pas surcharger l'API
                            time.sleep(0.1)
                        except FFTTApiError as e:
                            logging.warning(f"Impossible de récupérer les points pour advlic {advlic}: {e}")
                            adversaire_cache[advlic] = None
                    
                    adversaire_points = adversaire_cache[advlic]
                
                if not adversaire_points:
                    logging.warning(f"Points adversaire manquants pour match {idpartie}")
                    continue
                
                points = calculate_match_points(joueur_points, adversaire_points, resultat, coefchamp)
                
                matches_with_points.append({
                    'idpartie': idpartie,
                    'date': date,
                    'adversaire': adversaire,
                    'advlic': advlic,
                    'adversaire_points': adversaire_points,
                    'resultat': resultat,
                    'coefchamp': float(coefchamp),
                    'points_calculated': points,
                })
            except Exception as e:
                logging.warning(f"Erreur calcul points pour match {match.get('idpartie', '?')}: {e}")
                continue
        
        total_points = sum(m['points_calculated'] for m in matches_with_points)
        
        return {
            "success": True,
            "licence": licence,
            "joueur_points": joueur_points,
            "matches": matches_with_points,
            "count": len(matches_with_points),
            "total_points_calculated": round(total_points, 2),
        }
    except Exception as e:
        logging.error(f"Erreur build_results_with_calculated_points pour licence {licence}: {e}")
        return {
            "success": False,
            "licence": licence,
            "error": str(e),
        }


def get_current_period_bounds(now=None):
    reference = now or datetime.now()
    if reference.day >= 11:
        start = datetime(reference.year, reference.month, 1)
    else:
        if reference.month == 1:
            start = datetime(reference.year - 1, 12, 1)
        else:
            start = datetime(reference.year, reference.month - 1, 1)
    end = datetime(reference.year, reference.month, reference.day)
    return start, end


def parse_match_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y")
    except (TypeError, ValueError):
        return None


def fetch_player_partie_mysql_records(licence):
    content = make_request(
        "xml_partie_mysql.php",
        additional_params={"licence": licence},
        timeout=15,
        use_new_session=True,
        close_connection=True,
        base_url=JOUEUR_BASE_URL,
    )
    records, _ = parse_xml_records(content)
    return records


def calculate_player_period_total(
    licence,
    joueur_points,
    start_date,
    end_date,
    shared_opponent_cache=None,
    include_matches=False,
):
    partie_mysql_records = fetch_player_partie_mysql_records(licence)
    opponent_cache = shared_opponent_cache if shared_opponent_cache is not None else {}

    matches = []
    total_points = 0.0

    for match in partie_mysql_records:
        match_date = parse_match_date(match.get("date"))
        if not match_date or match_date < start_date or match_date > end_date:
            continue

        advlic = (match.get("advlic") or "").strip()
        resultat = (match.get("vd") or "").strip()
        coefchamp = match.get("coefchamp", "1")
        idpartie = match.get("idpartie", "")
        adversaire = match.get("advnompre", "")

        if not advlic:
            continue

        if advlic not in opponent_cache:
            try:
                adv_joueur = get_player_details_xml_joueur(advlic)
                opponent_cache[advlic] = adv_joueur.get("point") or adv_joueur.get("valinit")
                time.sleep(0.05)
            except FFTTApiError:
                opponent_cache[advlic] = None

        adversaire_points = opponent_cache.get(advlic)
        if not adversaire_points:
            continue

        points = calculate_match_points(joueur_points, adversaire_points, resultat, coefchamp)
        total_points += points

        if include_matches:
            matches.append({
                "idpartie": idpartie,
                "date": match.get("date", ""),
                "adversaire": adversaire,
                "advlic": advlic,
                "adversaire_points": adversaire_points,
                "resultat": resultat,
                "coefchamp": float(coefchamp),
                "points_calculated": points,
            })

    payload = {
        "success": True,
        "licence": licence,
        "joueur_points": joueur_points,
        "count": len(matches) if include_matches else None,
        "total_points_calculated": round(total_points, 2),
    }
    if include_matches:
        payload["matches"] = matches
    return payload


def fetch_all_club_matches_parallel(licences, max_workers=5):
    """Charge les matches de tous les joueurs du club EN PARALLÈLE"""
    matches_by_licence = {}
    errors = {}
    
    def fetch_with_error_handling(licence):
        try:
            return licence, fetch_player_partie_mysql_records(licence)
        except Exception as e:
            return licence, e
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_with_error_handling, lic): lic for lic in licences}
        for future in as_completed(futures):
            licence, result = future.result()
            if isinstance(result, Exception):
                errors[licence] = str(result)
            else:
                matches_by_licence[licence] = result
    
    return matches_by_licence, errors


def fetch_all_opponents_info_parallel(matches_by_licence, max_workers=12):
    """Charge les infos adversaires EN PARALLÈLE (thread-safe avec Lock)"""
    import threading
    opponent_cache = {}
    lock = threading.Lock()
    
    def fetch_opponent(advlic):
        try:
            adv_joueur = get_player_details_xml_joueur(advlic)
            points = adv_joueur.get("point") or adv_joueur.get("valinit")
            with lock:
                opponent_cache[advlic] = points
            time.sleep(0.005)  # throttle léger
        except Exception as e:
            with lock:
                opponent_cache[advlic] = None
            logging.debug(f"Erreur opponent {advlic}: {e}")
    
    # Collect tous les advlic uniques
    all_advlic = set()
    for matches in matches_by_licence.values():
        for match in matches:
            advlic = (match.get("advlic") or "").strip()
            if advlic:
                all_advlic.add(advlic)
    
    logging.info(f"Chargement de {len(all_advlic)} adversaires en parallèle (max_workers={max_workers})...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(fetch_opponent, all_advlic))
    
    return opponent_cache


def build_results_calculated_club(club_num=None):
    rows, resolved_club = get_club_licence_rows(club_num)
    if not rows:
        return [], {
            "mode": MODE_POINT,
            "formula": "points officiels -> points mensuels + somme(points recalcules FFTT) (fallback pointm si timeout/erreur)",
            "truncated": False,
            "resolved_club": resolved_club,
            "period_start": None,
            "period_end": None,
            "processed": 0,
            "available": 0,
        }

    start_date, end_date = get_current_period_bounds()
    players = []
    errors = []
    processed = 0
    
    # PHASE 1: Charger TOUS les matches en parallèle
    logging.info(f"[Club {resolved_club}] Chargement des matches pour {len(rows)} joueurs en parallèle...")
    licences = [row["licence"] for row in rows]
    matches_by_licence, fetch_errors = fetch_all_club_matches_parallel(licences, max_workers=12)
    
    if fetch_errors:
        for lic, err in fetch_errors.items():
            errors.append(f"{lic}: {err}")
            logging.warning(f"Erreur fetch matches pour {lic}: {err}")
    
    # PHASE 2: Charger TOUS les adversaires en parallèle
    logging.info(f"[Club {resolved_club}] Chargement des infos adversaires en parallèle...")
    opponent_cache = fetch_all_opponents_info_parallel(matches_by_licence, max_workers=12)
    
    # PHASE 3: Calculer en mémoire pour chaque joueur
    logging.info(f"[Club {resolved_club}] Calculs en mémoire...")
    for row in rows:
        licence = row["licence"]
        joueur_points = row["pointm"]
        
        if licence not in matches_by_licence:
            # Pas de matches trouvés pour ce joueur
            players.append({
                "licence": licence,
                "nom": row["nom"],
                "prenom": row["prenom"],
                "points_classement": joueur_points,
                "points_proposes": row["pointm"],
            })
            continue
        
        total_points = 0.0
        player_matches = matches_by_licence[licence]
        
        for match in player_matches:
            match_date = parse_match_date(match.get("date"))
            if not match_date or match_date < start_date or match_date > end_date:
                continue
            
            advlic = (match.get("advlic") or "").strip()
            resultat = (match.get("vd") or "").strip()
            coefchamp = match.get("coefchamp", "1")
            
            if not advlic or advlic not in opponent_cache:
                continue
            
            adversaire_points = opponent_cache.get(advlic)
            if not adversaire_points:
                continue
            
            points = calculate_match_points(joueur_points, adversaire_points, resultat, coefchamp)
            total_points += points
        
        processed += 1
        players.append({
            "licence": licence,
            "nom": row["nom"],
            "prenom": row["prenom"],
            "points_officiels": row["initm"],
            "points_classement": row["initm"],
            "points_proposes": round(joueur_points + total_points, 2),
        })

    if errors:
        logging.warning("%s erreur(s) de recalcul club %s", len(errors), resolved_club)

    meta = {
        "mode": MODE_POINT,
        "formula": "points officiels -> points mensuels + somme(points recalcules FFTT) (fallback pointm si timeout/erreur)",
        "truncated": processed < len(rows),
        "resolved_club": resolved_club,
        "period_start": start_date.strftime("%Y-%m-%d"),
        "period_end": end_date.strftime("%Y-%m-%d"),
        "processed": processed,
        "available": len(rows),
    }
    return players, meta


def get_results(club_num=None, mode=MODE_POINT):
    # Recalcul FFTT parallélisé pour tout le club (pas de timeout!)
    return build_results_calculated_club(club_num)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search-club')
def api_search_club():
    from flask import request
    club_name = request.args.get('name', '').strip()
    if not club_name or len(club_name) < 3:
        return jsonify({"success": False, "error": "Le nom du club doit contenir au moins 3 caractères"}), 400
    
    try:
        clubs = search_club_by_name(club_name)
        search_lower = club_name.lower()
        filtered_clubs = [
            club for club in clubs 
            if search_lower in club['nom'].lower() or search_lower in club['ville'].lower()
        ]
        filtered_clubs.sort(key=lambda c: (
            not c['nom'].lower().startswith(search_lower),
            c['nom'].lower()
        ))
        return jsonify({"success": True, "data": filtered_clubs, "count": len(filtered_clubs)})
    except FFTTApiError as e:
        logging.error(f"Erreur FFTT lors de la recherche de club: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        logging.error(f"Erreur lors de la recherche de club: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/results')
def api_results():
    from flask import request
    club_num = request.args.get('club', '').strip() or None
    licence = request.args.get('licence', '').strip() or None
    calculated = request.args.get('calculated', '').strip().lower() == '1'

    try:
        # Si demande de points calculés pour un joueur spécifique
        if calculated and licence:
            # Récupérer les données du joueur pour obtenir ses points
            full_data = fetch_player_full_data(licence)
            licence_b_records = full_data.get('licence_b', {}).get('records', [])
            
            if not licence_b_records:
                return jsonify({
                    "success": False,
                    "error": f"Joueur {licence} non trouvé ou données manquantes"
                }), 404
            
            joueur_points = parse_points(licence_b_records[0].get('pointm', ''))
            start_date, end_date = get_current_period_bounds()
            result = calculate_player_period_total(
                licence=licence,
                joueur_points=joueur_points,
                start_date=start_date,
                end_date=end_date,
                include_matches=True,
            )
            result["period_start"] = start_date.strftime("%Y-%m-%d")
            result["period_end"] = end_date.strftime("%Y-%m-%d")
            result["points_proposes"] = round(joueur_points + result.get("total_points_calculated", 0), 2)
            return jsonify(result)
        
        # Sinon, retourner les résultats standard
        results, meta = get_results(club_num=club_num, mode=MODE_POINT)
        return jsonify({
            "success": True,
            "data": results,
            "count": len(results),
            "club": club_num,
            "resolved_club": meta.get("resolved_club"),
            "mode": meta.get("mode"),
            "formula": meta.get("formula"),
            "truncated": meta.get("truncated", False),
            "processed": meta.get("processed"),
            "available": meta.get("available"),
            "period_start": meta.get("period_start"),
            "period_end": meta.get("period_end"),
        })
    except FFTTApiError as e:
        logging.error(f"Erreur FFTT lors de la récupération des résultats: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des résultats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/test-joueur')
def api_test_joueur():
    from flask import request

    licence = request.args.get('licence', '').strip()
    if not licence:
        return jsonify({"success": False, "error": "Paramètre licence obligatoire"}), 400

    try:
        joueur = get_player_details_xml_joueur(licence)
        return jsonify({"success": True, "data": joueur})
    except FFTTApiError as e:
        logging.error(f"Erreur FFTT lors du test joueur: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        logging.error(f"Erreur lors du test joueur: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/test-player-full')
def api_test_player_full():
    from flask import request

    licence = (request.args.get('licence', '') or DEFAULT_PLAYER_LICENSE).strip()
    token = request.args.get('token', '').strip()

    if not licence:
        return jsonify({"success": False, "error": "Paramètre licence obligatoire"}), 400

    try:
        validate_test_api_token(token)
        data = fetch_player_full_data(licence)
        return jsonify({
            "success": True,
            "licence": licence,
            "sources": list(PLAYER_FULL_ENDPOINTS.keys()),
            "data": data,
        })
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except FFTTApiError as e:
        logging.error(f"Erreur FFTT test-player-full: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        logging.error(f"Erreur test-player-full: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/download')
def download_results():
    from flask import request
    club_num = request.args.get('club', '').strip() or None

    try:
        results, meta = get_results(club_num=club_num, mode=MODE_POINT)
        if not results:
            return jsonify({"success": False, "error": "Aucun résultat à télécharger"}), 404
        
        lines = []
        for r in results:
            progression = r["points_proposes"] - r["points_classement"]
            line = (
                f"{r['prenom']} {r['nom']} | classement: {r['points_classement']} "
                f"| proposes: {r['points_proposes']} | progression: {progression:+d}"
            )
            lines.append(line)

        lines.insert(0, f"Mode: {meta.get('mode')} | Formule: {meta.get('formula')}")
        
        content = "\n".join(lines)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}_progression_mensuelle.txt"
        
        response = make_response(content)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logging.info(f"Téléchargement du fichier {filename} avec {len(results)} résultats")
        return response
    except FFTTApiError as e:
        logging.error(f"Erreur FFTT lors du téléchargement: {e}")
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        logging.error(f"Erreur lors du téléchargement: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Export explicite pour Vercel
app = app
