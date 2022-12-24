#!/usr/bin/env python3
import json
import os

HOME = os.getenv('HOME')
DB = os.path.join(HOME, '.cache/anitsu.json')

with open(DB, 'r') as fp:
    db = json.load(fp)

for k in db:
    for i in db[k]['nextcloud']:
        db[k]['nextcloud'][i] = dict()

if input('Save changes? (y/n) ').lower() == 'y':
    with open(DB, 'w') as fp:
        json.dump(db, fp)
