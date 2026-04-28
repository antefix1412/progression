#!/usr/bin/env python3
"""Test final: vérifier que tout marche sans erreurs"""
import time
from api.index import app

c = app.test_client()

print("=" * 60)
print("TEST FINAL: /api/results (club entier)")
print("=" * 60)

start = time.time()
r = c.get('/api/results')
elapsed = time.time() - start

print(f"\nStatus: {r.status_code}")
print(f"Time: {elapsed:.1f}s")

if r.status_code != 200:
    print(f"ERROR: Expected 200, got {r.status_code}")
    print(f"Response: {r.text[:500]}")
    exit(1)

d = r.get_json()

# Vérifier les champs requis
required = ['success', 'data', 'count', 'formula']
for field in required:
    if field not in d:
        print(f"ERROR: Missing field '{field}'")
        exit(1)

# Vérifier les données
data = d.get('data', [])
if not data:
    print("ERROR: No data returned")
    exit(1)

print(f"\nSuccess: {d['success']}")
print(f"Count: {d['count']}")
print(f"Processed: {d.get('processed', '?')}")
print(f"Period: {d.get('period_start')} to {d.get('period_end')}")

# Vérifier les joueurs
print(f"\nTop 5 players by points_proposes:")
top5 = sorted(data, key=lambda x: x.get('points_proposes', 0), reverse=True)[:5]
for p in top5:
    prog = p['points_proposes'] - p['points_classement']
    print(f"  {p['licence']:8} {p['nom']:15} {p['prenom']:15} {p['points_proposes']:8.2f} (prog: {prog:+.2f})")

# Vérifier format
first = data[0]
required_keys = ['licence', 'nom', 'prenom', 'points_classement', 'points_proposes']
missing = [k for k in required_keys if k not in first]
if missing:
    print(f"\nERROR: Missing keys in player data: {missing}")
    exit(1)

print(f"\n[OK] All checks passed!")
print(f"[OK] API is working correctly")
print("=" * 60)
