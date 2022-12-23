#!/usr/bin/env python3
from urllib.parse import unquote
from optparse import OptionParser
from tempfile import mktemp
from threading import Thread
import subprocess as sp
import json
import os
import sys
import re

ROOT = os.path.dirname(os.path.realpath(__file__))
UPDATE_SCRIPT = os.path.join(ROOT, 'update.sh')
HOME = os.getenv('HOME')
DL_DIR = os.path.join(HOME, 'Downloads')
DB = os.path.join(HOME, '.local/share/anitsu_files.json')
PREVIEW_SCRIPT = os.path.join(ROOT, 'preview.py')
FIFO = '/tmp/anitsu.fifo'

FZF_ARGS = [
    '-m',
    '--preview', f'{PREVIEW_SCRIPT} {{}}',
    '--bind', 'ctrl-a:toggle-all+first+toggle',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-l:last'
]

usage = 'Usage: %prog [options]'
parser = OptionParser(usage=usage)
parser.add_option('-u', '--update', action='store_true')
parser.add_option('-d', '--download', action='store_true')
parser.add_option('--dir', type='string', default=DL_DIR)
opts, args = parser.parse_args()
assert os.path.exists(opts.dir)

if args:
    opts.update   = 'update' in args
    opts.download = 'download' in args

with open(DB, 'r') as fp:
    db = json.load(fp)


def fzf(args):
    proc = sp.Popen(
       ["fzf"] + FZF_ARGS,
       stdin=sp.PIPE,
       stdout=sp.PIPE,
       universal_newlines=True
    )
    out = proc.communicate('\n'.join(args))
    if proc.returncode != 0:
        sys.exit(proc.returncode)
    return [i for i in out[0].split('\n') if i]


def preview_fifo():
    def rec(q, data):
        if q in data:
            if isinstance(data[q], dict):
                return [i for i in data[q]]
            else:
                return []

        for k in data:
            if isinstance(data[k], dict):
                return rec(q, data[k])

    main_k = None
    while True:
        with open(FIFO, 'r') as fifo:
            data = fifo.read()
            if len(data) == 0:
                return

            output = list()
            for k in [i.strip() for i in data.split('\n') if i]:
                if k == '..':
                    break
                elif k in db:
                    main_k = k
                    if isinstance(db[k], dict):
                        output = [i for i in db[k]]
                elif k in db[main_k]:
                    if isinstance(db[main_k][k], dict):
                        output = [i for i in db[main_k][k]]
                else:
                    output = rec(k, db[main_k])

            if not output:
                output = []

        with open(FIFO, 'w') as fp:
            for i in output[:100]:
                fp.write(i + '\n')


def nav(data, old_data=list(), files=[]):
    keys = list(data.keys())
    if old_data:
        keys = ['..'] + keys

    for v in fzf(keys):
        if v == '..':
            last = old_data[-1]
            del old_data[-1]
            return nav(last, old_data)

        if not isinstance(data[v], dict):
            files.append(data[v])

    if files:
        return files

    old_data.append(data)
    return nav(data[v], old_data)

if opts.update:
    assert os.path.exists(UPDATE_SCRIPT)
    try:
        sp.run(['bash', UPDATE_SCRIPT])
    except KeyboardInterrupt:
        pass
else:
    if not os.path.exists(FIFO):
        os.mkfifo(FIFO)

    t = Thread(target=preview_fifo)
    t.start()
    tmpfile = mktemp()
    try:
        files = nav(db)
        with open(tmpfile, 'w') as fp:
            for url in files:
                fp.write(url + '\n')

        p = sp.run([
            'aria2c', '-j', '2',
            '--dir', opts.dir, f'--input-file={tmpfile}'
        ])
    except KeyboardInterrupt:
        pass
    except Exception as err:
        pass
    finally:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)

        if os.path.exists(FIFO):
            with open(FIFO, 'w') as fp:
                fp.write('')
            t.join()
            os.remove(FIFO)
