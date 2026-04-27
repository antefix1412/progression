#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
import hashlib
import hmac
from datetime import datetime
import logging
import os
import time
from typing import Optional

# ========== CONFIG ==========
# Charger les variables d'environnement depuis .env (en développement)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv n'est pas installé (mode production sur Vercel)
    pass

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
BASE_URL = "https://apiv2.fftt.com/mobile/pxml/"
JOUEUR_BASE_URL = "https://www.fftt.com/mobile/pxml/"
PLAYER_REQUEST_DELAY_SECONDS = 0.5

HAS_FFTT_AUTH = all([MOTDEPASSE, ID_APP, SERIE])
# ============================

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if not HAS_FFTT_AUTH:
    logging.warning(
        "Variables FFTT manquantes. L'application peut s'afficher, mais les appels API FFTT seront indisponibles tant que FFTT_PASSWORD, FFTT_ID_APP et FFTT_SERIE ne sont pas definies."
    )

if not CLUB_NUM:
    logging.warning(
        "Numero de club absent. Definis FFTT_CLUB_NUM (ou CLUB_NUM/NUM_CLUB), ou passe ?club=... a l'API."
    )


def resolve_club_num(club_num):
    target = (club_num or CLUB_NUM or "").strip()
    if not target:
        raise ValueError(
            "Numero de club manquant. Definis FFTT_CLUB_NUM (ou CLUB_NUM/NUM_CLUB) dans les variables d'environnement."
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


def make_request(endpoint, additional_params=None, timeout=30, use_new_session=False, close_connection=False, base_url=BASE_URL):
    if not HAS_FFTT_AUTH:
        logging.error("Configuration FFTT manquante: impossible d'appeler %s", endpoint)
        return None
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
        logging.error(f"Erreur API : {e}")
        return None


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


def get_player_clpro(licence):
    for _ in range(2):
        content = make_request(
            "xml_joueur.php",
            {"licence": licence, "auto": "1"},
            timeout=20,
            use_new_session=True,
            close_connection=True,
            base_url=JOUEUR_BASE_URL,
        )
        if content:
            try:
                root = ET.fromstring(content)
                if extract_api_error(root):
                    time.sleep(PLAYER_REQUEST_DELAY_SECONDS)
                    continue

                joueur = root.find(".//joueur")
                if joueur is None:
                    time.sleep(PLAYER_REQUEST_DELAY_SECONDS)
                    continue

                clpro = parse_points(joueur.findtext("clpro"))
                if clpro is not None:
                    return clpro
            except ET.ParseError:
                pass

        time.sleep(PLAYER_REQUEST_DELAY_SECONDS)

    return None


def get_club_licence_details(club_num=None):
    target_club = resolve_club_num(club_num)
    content = make_request("xml_licence_b.php", {"club": target_club})
    if not content:
        return []


def get_player_details_xml_joueur(licence):
    content = make_request(
        "xml_joueur.php",
        {"licence": licence, "auto": "1"},
        timeout=20,
        use_new_session=True,
        close_connection=True,
        base_url=JOUEUR_BASE_URL,
    )
    if not content:
        raise ValueError(f"Impossible de recuperer xml_joueur pour la licence {licence}")

    try:
        root = ET.fromstring(content)
        if extract_api_error(root):
            raise ValueError(f"Erreur FFTT sur xml_joueur pour la licence {licence}")

        joueur = root.find(".//joueur")
        if joueur is None:
            raise ValueError(f"Aucune fiche joueur trouvee pour la licence {licence}")

        clpro = parse_points(joueur.findtext("clpro"))
        valinit = parse_points(joueur.findtext("valinit"))
        if clpro is None or valinit is None:
            raise ValueError(f"clpro ou valinit manquant pour la licence {licence}")

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
    except ET.ParseError as e:
        raise ValueError(f"Reponse XML invalide pour la licence {licence}: {e}") from e
    try:
        root = ET.fromstring(content)
        if extract_api_error(root):
            return []

        players = []
        last_call_at = None
        for node in root.findall(".//licence"):
            licence_number = node.findtext("licence")
            nom = node.findtext("nom")
            prenom = node.findtext("prenom")
            point = parse_points(node.findtext("point"))

            if not licence_number or not nom or not prenom:
                continue

            if point is None:
                continue

            now = time.monotonic()
            if last_call_at is not None:
                remaining = PLAYER_REQUEST_DELAY_SECONDS - (now - last_call_at)
                if remaining > 0:
                    time.sleep(remaining)

            clpro = get_player_clpro(licence_number.strip())
            last_call_at = time.monotonic()

            if clpro is None:
                continue

            players.append({
                "licence": licence_number.strip(),
                "nom": nom.strip(),
                "prenom": prenom.strip(),
                "points_classement": point,
                "points_proposes": clpro,
            })

        logging.info(f"{len(players)} joueurs récupérés pour le club {target_club}")
        return players
    except ET.ParseError as e:
        logging.error(f"Erreur parsing XML licence_b : {e}\n{content}")
        return []


def search_club_by_name(club_name):
    """Recherche un club par son nom et retourne les résultats"""
    content = make_request('xml_club_b.php', {'nom': club_name})
    clubs = []
    if not content:
        return clubs
    try:
        root = ET.fromstring(content)
        if extract_api_error(root):
            return clubs
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
        logging.error(f"Erreur parsing XML clubs : {e}\n{content}")
    return clubs


def get_results(club_num=None):
    """Récupère tous les joueurs et les informations utiles au calcul."""
    return get_club_licence_details(club_num)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search-club')
def api_search_club():
    """Recherche un club par son nom"""
    from flask import request
    club_name = request.args.get('name', '').strip()
    if not club_name or len(club_name) < 3:
        return jsonify({"success": False, "error": "Le nom du club doit contenir au moins 3 caractères"}), 400
    
    try:
        clubs = search_club_by_name(club_name)
        
        # Filtrage insensible à la casse côté serveur
        search_lower = club_name.lower()
        filtered_clubs = [
            club for club in clubs 
            if search_lower in club['nom'].lower() or search_lower in club['ville'].lower()
        ]
        
        # Trier par pertinence : clubs qui commencent par le terme recherché en premier
        filtered_clubs.sort(key=lambda c: (
            not c['nom'].lower().startswith(search_lower),  # False (0) avant True (1)
            c['nom'].lower()
        ))
        
        return jsonify({"success": True, "data": filtered_clubs, "count": len(filtered_clubs)})
    except Exception as e:
        logging.error(f"Erreur lors de la recherche de club: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/results')
def api_results():
    """Récupère la progression des joueurs via clpro - valcla"""
    from flask import request
    if not HAS_FFTT_AUTH:
        return jsonify({
            "success": False,
            "error": "Configuration FFTT manquante sur le serveur. Ajoute FFTT_PASSWORD, FFTT_ID_APP et FFTT_SERIE dans les variables d'environnement."
        }), 500
    club_num = request.args.get('club', '').strip() or None

    try:
        results = get_results(club_num=club_num)
        return jsonify({"success": True, "data": results, "count": len(results)})
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
    except Exception as e:
        logging.error(f"Erreur test xml_joueur: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/download')
def download_results():
    """Télécharge les résultats"""
    from flask import request, make_response
    if not HAS_FFTT_AUTH:
        return jsonify({
            "success": False,
            "error": "Configuration FFTT manquante sur le serveur. Ajoute FFTT_PASSWORD, FFTT_ID_APP et FFTT_SERIE dans les variables d'environnement."
        }), 500
    club_num = request.args.get('club', '').strip() or None

    try:
        results = get_results(club_num=club_num)
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
        
        content = "\n".join(lines)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}_progression_mensuelle.txt"
        
        # Créer une réponse avec le contenu
        response = make_response(content)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logging.info(f"Téléchargement du fichier {filename} avec {len(results)} résultats")
        return response
    except Exception as e:
        logging.error(f"Erreur lors du téléchargement: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

# Pour Vercel
app = app
