#!/usr/bin/env python3
import json
from app import get_player_details_xml_joueur, calculate_match_points, parse_points

# Test avec les données réelles d'un match
joueur_points = 1382  # Antoine LEMESLE (licence 3533138)

# Premier match : PEGET Kevin (licence 2922033)
print("Test 1: PEGET Kevin (licence 2922033)")
try:
    joueur = get_player_details_xml_joueur('2922033')
    print(f"  Points de PEGET: {joueur['point']}")
    
    # Résultat: V (victoire), coefchamp: 1.5, date: 05/04/2026
    points = calculate_match_points(joueur_points, joueur['point'], 'V', 1.5)
    ecart = joueur['point'] - joueur_points
    print(f"  Écart: {ecart:+3d}")
    print(f"  Résultat: Victoire | Coefficient: 1.5")
    print(f"  Points calculés: {points:+.2f}")
    print()
except Exception as e:
    print(f"  Erreur: {e}")
    print()

# Deuxième match : MENGUY Emmanuel (licence ?)
# Je vais chercher un autre match avec points
print("Test 2: Chercher les adversaires uniques...")
try:
    from app import fetch_player_full_data
    data = fetch_player_full_data('3533138')
    partie_mysql = data['partie_mysql']['records']
    
    # Afficher le résumé des adversaires uniques
    adversaires = {}
    for match in partie_mysql:
        advlic = match.get('advlic', '')
        advnompre = match.get('advnompre', '')
        if advlic not in adversaires:
            adversaires[advlic] = advnompre
    
    print(f"  Total d'adversaires uniques: {len(adversaires)}")
    print(f"  Premiers 5 adversaires:")
    for i, (lic, nom) in enumerate(list(adversaires.items())[:5]):
        print(f"    {i+1}. {nom} (licence {lic})")
    
except Exception as e:
    print(f"  Erreur: {e}")
