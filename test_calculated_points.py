#!/usr/bin/env python3
# Test l'endpoint /api/results avec calcul des points

import json
from app import app

with app.test_client() as client:
    resp = client.get('/api/results?calculated=1&licence=3533138')
    data = resp.get_json()
    
    print('Status:', resp.status_code)
    print('Success:', data.get('success'))
    print('Licence:', data.get('licence'))
    print('Match count:', data.get('count'))
    print('Total points calculated:', data.get('total_points_calculated'))
    print()
    
    # Afficher les 3 premiers matchs
    if 'matches' in data:
        print('Premiers matchs:')
        for m in data['matches'][:3]:
            date = m['date']
            adv = m['adversaire']
            res = m['resultat']
            adv_pts = m['adversaire_points']
            calc_pts = m['points_calculated']
            print(f"  {date} | {adv:20s} | {res} | Pts adv: {adv_pts:4} | Points: {calc_pts:+6.2f}")
    
    # Afficher tout le JSON pour inspection
    print()
    print('=== JSON Complet ===')
    print(json.dumps(data, indent=2, ensure_ascii=False))
