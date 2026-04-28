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
from concurrent.futures import ThreadPoolExecutor, as_completed

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
TEST_API_TOKEN = get_env("FFTT_TEST_API_TOKEN", "TEST_API_TOKEN")
DEFAULT_PLAYER_LICENSE = get_env("FFTT_TEST_PLAYER_LICENSE") or "3533138"
BASE_URL = "https://apiv2.fftt.com/mobile/pxml/"
JOUEUR_BASE_URL = "https://www.fftt.com/mobile/pxml/"
PLAYER_REQUEST_DELAY_SECONDS = 0.5

HAS_FFTT_AUTH = all([MOTDEPASSE, ID_APP, SERIE])

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


def validate_test_api_token(candidate_token):
    if not TEST_API_TOKEN:
        raise ValueError(
            "Token manquant sur le serveur. Definis FFTT_TEST_API_TOKEN dans les variables d'environnement."
        )
    if not candidate_token:
        raise PermissionError("Parametre token obligatoire")
    if not hmac.compare_digest(candidate_token, TEST_API_TOKEN):
        raise PermissionError("Token invalide")


def parse_xml_records(content):
    root = ET.fromstring(content)
    api_error = extract_api_error(root)
    if api_error:
        raise ValueError(api_error)

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
            if not content:
                aggregated[key] = {
                    "endpoint": endpoint,
                    "params": params,
                    "error": "Aucune reponse API",
                }
                continue
        except Exception as exc:
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
        except ValueError as exc:
            aggregated[key] = {
                "endpoint": endpoint,
                "params": params,
                "error": str(exc),
                "raw_preview": content[:1000],
            }

    return aggregated


def get_club_licence_details(club_num=None):
    target_club = resolve_club_num(club_num)
    content = make_request("xml_licence_b.php", {"club": target_club})
    if not content:
        return []
    try:
        root = ET.fromstring(content)
        if extract_api_error(root):
            return []

        players = []
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

            players.append({
                "licence": licence_number.strip(),
                "nom": nom.strip(),
                "prenom": prenom.strip(),
                "points_classement": initm,
                "points_proposes": pointm,
            })

        logging.info(f"{len(players)} joueurs récupérés pour le club {target_club}")
        return players
    except ET.ParseError as e:
        logging.error(f"Erreur parsing XML licence_b : {e}\n{content}")
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
    except ET.ParseError as e:
        raise ValueError(f"Reponse XML invalide pour la licence {licence}: {e}") from e


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
                        except Exception as e:
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
            result = build_results_with_calculated_points(licence, joueur_points)
            return jsonify(result)
        
        # Sinon, retourner les résultats standard
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


@app.route('/api/test-player-full')
def api_test_player_full():
    from flask import request

    licence = (request.args.get('licence', '') or DEFAULT_PLAYER_LICENSE).strip()
    token = request.args.get('token', '').strip()

    if not licence:
        return jsonify({"success": False, "error": "Parametre licence obligatoire"}), 400

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
    except ValueError as e:
        logging.error(f"Erreur test-player-full: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        logging.error(f"Erreur test-player-full: {e}")
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
