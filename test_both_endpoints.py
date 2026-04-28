#!/usr/bin/env python3
import time
from api.index import app

c = app.test_client()

# Test 1: Single player (should be fast)
print("Test 1: Single player endpoint")
start = time.time()
r = c.get('/api/results?calculated=1&licence=3533138')
elapsed = time.time() - start
d = r.get_json()
print(f'  STATUS {r.status_code}')
print(f'  ELAPSED {elapsed:.1f}s')
print(f'  COUNT {d.get("count")}')
print(f'  TOTAL_POINTS {d.get("total_points_calculated")}')
print(f'  FORMULA {d.get("formula")}')

# Test 2: Club endpoint (should be ~20-25s)
print("\nTest 2: Club endpoint")
start = time.time()
r = c.get('/api/results')
elapsed = time.time() - start
d = r.get_json()
print(f'  STATUS {r.status_code}')
print(f'  ELAPSED {elapsed:.1f}s')
print(f'  COUNT {d.get("count")}')
print(f'  PROCESSED {d.get("processed")}')
print(f'  FORMULA {d.get("formula")}')

# Show summary
data = d.get('data') or []
print(f'\n  Summary:')
print(f'    Total players: {len(data)}')
non_zero = [p for p in data if p.get('points_proposes', 0) != p.get('points_classement', 0)]
print(f'    With calculated points: {len(non_zero)}')
