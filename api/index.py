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
from datetime import datetime, timedelta
import logging

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

# Vérifier que toutes les variables sont définies
if not all([MOTDEPASSE, ID_APP, SERIE, CLUB_NUM]):
    logging.warning("Variables d'environnement manquantes - utilisation des valeurs par défaut")
    MOTDEPASSE = "g2XCYk1eK3"
    ID_APP = "SW436"
    SERIE = "RSJKKEQZCLBACUX"
    CLUB_NUM = "03350022"
# ============================

# Calculer les chemins absolus pour templates et static
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def generate_auth_params():
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    ccle = hashlib.md5(MOTDEPASSE.encode()).hexdigest()
    tmc = hmac.new(ccle.encode(), timestamp.encode(), hashlib.sha1).hexdigest()
    return {'serie': SERIE, 'tm': timestamp, 'tmc': tmc, 'id': ID_APP}


def make_request(endpoint, additional_params=None, timeout=30):
    params = generate_auth_params()
    if additional_params:
        params.update(additional_params)
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = "latin-1"
        try:
            return resp.text.encode('latin-1').decode('utf-8', errors='ignore')
        except Exception:
            return resp.text
    except requests.RequestException as e:
        logging.error(f"Erreur API : {e}")
        return None


def get_club_players(club_num=None):
    target_club = club_num if club_num else CLUB_NUM
    content = make_request('xml_liste_joueur_o.php', {'club': target_club, 'valid': '1'})
    players = []
    if not content:
        return players
    try:
        root = ET.fromstring(content)
        for joueur in root.findall('joueur'):
            licence = joueur.findtext('licence')
            nom = joueur.findtext('nom')
            prenom = joueur.findtext('prenom')
            if licence and nom and prenom:
                players.append({'licence': licence.strip(), 'nom': nom.strip(), 'prenom': prenom.strip()})
        logging.info(f"{len(players)} joueurs récupérés pour le club {target_club}")
    except ET.ParseError as e:
        logging.error(f"Erreur parsing XML joueurs : {e}\n{content}")
    return players


def get_player_points(licence):
    content = make_request("xml_licence_b.php", {"licence": licence})
    if not content:
        return None
    try:
        root = ET.fromstring(content)
        if root.findtext("error"):
            return None
        pointm = root.findtext("licence/pointm")
        point = root.findtext("licence/point")
        if pointm and pointm.strip():
            try:
                return int(float(pointm.strip()))
            except (ValueError, TypeError):
                pass
        if point and point.strip():
            try:
                return int(float(point.strip()))
            except (ValueError, TypeError):
                pass
        return None
    except ET.ParseError:
        return None


def parse_classement(value: str) -> int:
    if not value:
        return 0
    try:
        if "-" in value:
            value = value.split("-")[-1].strip()
        return int(float(value))
    except Exception:
        return 0


def get_matches_for_player(licence):
    content = make_request('xml_partie.php', {'numlic': licence})
    if not content:
        return []
    try:
        root = ET.fromstring(content)
        matches = []
        for partie in root.findall('.//resultat'):
            date = partie.findtext('date', default='N/A')
            adversaire = partie.findtext('nom', default='N/A')
            victoire = partie.findtext('victoire', default='N/A')
            classement_adv = parse_classement(partie.findtext('classement', default='0'))
            matches.append({'date': date, 'adversaire': adversaire, 'victoire': victoire, 'classement_adv': classement_adv})
        for partie in root.findall('.//partie'):
            date = partie.findtext('date', default='N/A')
            adversaire = partie.findtext('nom', default='N/A')
            victoire = partie.findtext('victoire', default='N/A')
            classement_adv = parse_classement(partie.findtext('classement', default='0'))
            matches.append({'date': date, 'adversaire': adversaire, 'victoire': victoire, 'classement_adv': classement_adv})
        return matches
    except ET.ParseError:
        return []


def search_club_by_name(club_name):
    content = make_request('xml_club_b.php', {'nom': club_name})
    clubs = []
    if not content:
        return clubs
    try:
        root = ET.fromstring(content)
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


def get_results(club_num=None, min_ecart=75):
    target_club = club_num if club_num else CLUB_NUM
    players = get_club_players(target_club)
    if not players:
        return []
    results = []
    cutoff_date = datetime.now() - timedelta(days=6)
    for player in players:
        licence = player['licence']
        joueur_points = get_player_points(licence)
        if joueur_points is None:
            continue
        matches = get_matches_for_player(licence)
        if not matches:
            continue
        for m in matches:
            try:
                match_date = datetime.strptime(m['date'], "%d/%m/%Y")
            except Exception:
                continue
            if match_date < cutoff_date:
                continue
            if m['victoire'] == 'V' and m['classement_adv'] >= joueur_points + min_ecart:
                ecart = m['classement_adv'] - joueur_points
                results.append({
                    "prenom": player['prenom'],
                    "nom": player['nom'],
                    "points_joueur": joueur_points,
                    "points_adv": m['classement_adv'],
                    "ecart": ecart,
                    "date": m['date']
                })
    results.sort(key=lambda x: x['ecart'], reverse=True)
    return results


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
    except Exception as e:
        logging.error(f"Erreur lors de la recherche de club: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/results')
def api_results():
    from flask import request
    club_num = request.args.get('club', CLUB_NUM)
    try:
        min_ecart = int(request.args.get('ecart', 75))
    except ValueError:
        min_ecart = 75
    
    try:
        results = get_results(club_num=club_num, min_ecart=min_ecart)
        return jsonify({"success": True, "data": results, "count": len(results)})
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des résultats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/download')
def download_results():
    from flask import request
    club_num = request.args.get('club', CLUB_NUM)
    try:
        min_ecart = int(request.args.get('ecart', 75))
    except ValueError:
        min_ecart = 75
    
    try:
        results = get_results(club_num=club_num, min_ecart=min_ecart)
        if not results:
            return jsonify({"success": False, "error": "Aucun résultat à télécharger"}), 404
        
        lines = []
        for r in results:
            line = f"{r['prenom']} {r['nom']} ({r['points_joueur']}) --> {r['points_adv']} +{r['ecart']}"
            lines.append(line)
        
        content = "\n".join(lines)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{today}_perf_tableau.txt"
        
        response = make_response(content)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logging.info(f"Téléchargement du fichier {filename} avec {len(results)} résultats")
        return response
    except Exception as e:
        logging.error(f"Erreur lors du téléchargement: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
