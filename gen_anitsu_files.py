#!/usr/bin/env python3
from urllib.parse import unquote
import json
import re
import os

HOME = os.getenv('HOME')
DB = os.path.join(HOME, '.cache/anitsu.json')
OUTPUT = os.path.join(HOME, '.local/share/anitsu_files.json')

with open(DB, 'r') as fp:
    db = json.load(fp)

files = dict()
for k, v in db.items():
    title = db[k]['title']
    c = 1
    s = title
    while s in files:
        s = f'{title}.{c}'
        c += 1
    files[s] = dict()
    for v2 in v['nextcloud'].values():
        files[s].update(v2)

def count(data):
    t = 0
    for k in data:
        if not isinstance(data[k], dict):
            t += 1
        else:
            t += count(data[k])
    return t

print(count(files))

with open(OUTPUT, 'w') as fp:
    json.dump(files, fp)
