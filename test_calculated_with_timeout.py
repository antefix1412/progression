#!/usr/bin/env python3
import json
from app import app
import sys

try:
    print("Lancement du test de calcul des points...")
    print("Note: Cela prendra plusieurs minutes (1 requête par adversaire unique + délai de 0.1s)")
    print()
    
    with app.test_client() as client:
        resp = client.get('/api/results?calculated=1&licence=3533138')
        data = resp.get_json()
        
        print('Status:', resp.status_code)
        print('Success:', data.get('success'))
        print('Licence:', data.get('licence'))
        print('Match count:', data.get('count'))
        print('Total points calculated:', data.get('total_points_calculated'))
        print()
        
        # Afficher les 5 premiers matchs avec points
        if 'matches' in data:
            print('Premiers matchs avec points calculés:')
            for i, m in enumerate(data['matches'][:5]):
                date = m['date']
                adv = m['adversaire']
                res = m['resultat']
                adv_pts = m['adversaire_points']
                calc_pts = m['points_calculated']
                coef = m['coefchamp']
                print(f"  [{i+1}] {date} | {adv:20s} | {res} | Adv pts: {adv_pts:4} | Coef: {coef} | Points: {calc_pts:+7.2f}")
        
        print()
        print("✓ Test réussi!")
        
except KeyboardInterrupt:
    print("\n[INTERRUPTED] Test interrompu par l'utilisateur")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
