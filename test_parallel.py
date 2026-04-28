#!/usr/bin/env python3
import time
from api.index import app

c = app.test_client()
start = time.time()
r = c.get('/api/results')
elapsed = time.time() - start
d = r.get_json()

print(f'STATUS {r.status_code}')
print(f'ELAPSED {elapsed:.1f}s')
print(f'SUCCESS {d.get("success")}')
print(f'COUNT {d.get("count")}')
print(f'PROCESSED {d.get("processed")}')
print(f'AVAILABLE {d.get("available")}')
print(f'FORMULA {d.get("formula")}')
data = d.get('data') or []
if data:
    p = data[0]
    print(f'FIRST: {p.get("licence")} {p.get("nom")} {p.get("prenom")} init={p.get("points_classement")} prop={p.get("points_proposes")}')
else:
    print('No data')

# Show top 5 players
print('\nTop 5 by points_proposes:')
top5 = sorted(data, key=lambda x: x.get('points_proposes', 0), reverse=True)[:5]
for p in top5:
    print(f'  {p["licence"]} {p["nom"]} {p["prenom"]} {p["points_proposes"]}')
