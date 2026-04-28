#!/usr/bin/env python3
import time
import json
from api.index import app

c = app.test_client()

# Simuler une vraie demande du site
print("Simulation frontend:")
start = time.time()
r = c.get('/api/results')
elapsed = time.time() - start

d = r.get_json()
print(f"Status: {r.status_code}")
print(f"Time: {elapsed:.1f}s")
print(f"Success: {d.get('success')}")
print(f"Count: {d.get('count')}")
print(f"Processed: {d.get('processed')}")
print(f"Formula: {d.get('formula')}")
print(f"Period: {d.get('period_start')} to {d.get('period_end')}")

# Vérifier que les données qu'attendles frontend existent
data = d.get('data') or []
if data:
    print(f"\nFront-end check (first 3 players):")
    for p in data[:3]:
        print(f"  {p['licence']:8} {p['nom']:15} {p['prenom']:15} "
              f"init={p['points_classement']:8.0f} prop={p['points_proposes']:8.2f}")
    
    # Check que progression peut être calculée
    for p in data[:3]:
        progression = p['points_proposes'] - p['points_classement']
        print(f"    -> Progression: {progression:+.2f}")
else:
    print("No data returned!")

# Format check: toutes les clés requises
required_keys = ['licence', 'nom', 'prenom', 'points_classement', 'points_proposes']
if data:
    first = data[0]
    for key in required_keys:
        if key not in first:
            print(f"\n[!] MISSING KEY: {key}")
        else:
            print(f"[OK] {key}")
