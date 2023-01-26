#!/usr/bin/env python3
import json
import os

ROOT = os.path.realpath(os.path.dirname(__file__))
DB = os.path.join(ROOT, 'anitsu.json')
OUTPUT = os.path.join(ROOT, 'anitsu_files.json')

with open(DB, 'r') as fp:
    db = json.load(fp)

files = dict()
for k, v in db.items():
    title = db[k]['title']
    s = f'{title} (post-{k})'
    files[s] = dict()
    for v2 in v['nextcloud'].values():
        files[s].update(v2)

    for v2 in v['gdrive'].values():
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
files = {k: files[k] for k in sorted(list(files.keys()))}
with open(OUTPUT, 'w') as fp:
    json.dump(files, fp)
