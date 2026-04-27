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

        return {
            "licence": (joueur.findtext("licence") or licence).strip(),
            "nom": (joueur.findtext("nom") or "").strip(),
            "prenom": (joueur.findtext("prenom") or "").strip(),
            "club": (joueur.findtext("club") or "").strip(),
            "nclub": (joueur.findtext("nclub") or "").strip(),
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


def get_results(club_num=None, mode=MODE_POINT):
    # Mode production simplifie: uniquement xml_licence_b avec pointm-initm.
    return build_results_point(club_num)


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

    try:
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
