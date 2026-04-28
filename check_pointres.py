#!/usr/bin/env python3
import json

with open('player_3533138_full.json', 'r') as f:
    data = json.load(f)

partie_mysql = data['data']['partie_mysql']['records']
print('Vérification du champ pointres dans partie_mysql:')
print()

# Compter les pointres différents de 0
non_zero = [m for m in partie_mysql if m.get('pointres', '0') != '0']
print(f'Total matches: {len(partie_mysql)}')
print(f'Matches avec pointres != 0: {len(non_zero)}')
print()

# Afficher quelques exemples
print('Exemples de matches avec pointres:')
for m in partie_mysql[:10]:
    date = m.get('date', '')
    adv = m.get('advnompre', '')
    vd = m.get('vd', '')
    pts = m.get('pointres', '0')
    cla = m.get('advclaof', '?')
    print(f"  {date} | {adv:20s} | {vd} | pointres: {pts:>3s} | cla: {cla}")

# Regarder aussi les derniers matches (peut-être qu'ils ont des points récemment)
print()
print('Les 10 derniers matches:')
for m in partie_mysql[-10:]:
    date = m.get('date', '')
    adv = m.get('advnompre', '')
    vd = m.get('vd', '')
    pts = m.get('pointres', '0')
    cla = m.get('advclaof', '?')
    print(f"  {date} | {adv:20s} | {vd} | pointres: {pts:>3s} | cla: {cla}")
