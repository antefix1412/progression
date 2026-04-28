#!/usr/bin/env python3
import json
from api.index import app

c = app.test_client()
r = c.get('/api/results')
d = r.get_json()

# Afficher les 3 premiers joueurs
data = d.get('data', [])
if data:
    print("RESPONSE FORMAT CHECK:")
    print(f"Status: {r.status_code}")
    print(f"Success: {d.get('success')}")
    print(f"Count: {d.get('count')}")
    print(f"Formula: {d.get('formula')}")
    print(f"\nFirst 3 players:")
    for p in data[:3]:
        print(json.dumps(p, indent=2))
else:
    print("No data!")
