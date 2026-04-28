#!/usr/bin/env python3
import time
import sys
from api.index import app

c = app.test_client()
start = time.time()

try:
    r = c.get('/api/results')
    elapsed = time.time() - start
    d = r.get_json()
    print(f'[{elapsed:.1f}s] STATUS {r.status_code} | COUNT {d.get("count")} | PROCESSED {d.get("processed")} | SUCCESS {d.get("success")}')
    sys.exit(0)
except KeyboardInterrupt:
    elapsed = time.time() - start
    print(f'[{elapsed:.1f}s] TIMEOUT/INTERRUPTED')
    sys.exit(1)
except Exception as e:
    elapsed = time.time() - start
    print(f'[{elapsed:.1f}s] ERROR: {e}')
    sys.exit(1)
