#!/usr/bin/env python3
from threading import Thread
import subprocess as sp
import signal
import sys
import os
import json

HOME = os.getenv('HOME')
ROOT = os.path.dirname(os.path.realpath(__file__))
DL_DIR = os.path.join(HOME, 'Downloads')
DB = os.path.join(HOME, '.local/share/anitsu_files.json')
PREVIEW_SCRIPT = os.path.join(ROOT, 'preview.py')
RELOAD_SCRIPT = os.path.join(ROOT, 'reload.py')
PREVIEW_FIFO = '/tmp/anitsu.preview.fifo'
DL_FILE = '/tmp/anitsu'
FIFO = '/tmp/anitsu.fifo'
FZF_FIFO = '/tmp/anitsu.fzf.fifo'
FZF_PID = '/tmp/anitsu.fzf.pid'

FZF_ARGS = [
    '-m',
    '--border', 'none',
    '--preview-window', 'right:52%:border-none',
    '--bind', f'enter:reload(python3 {RELOAD_SCRIPT} {{+}})',
    '--preview', f'{PREVIEW_SCRIPT} {{}}',
    '--bind', 'ctrl-a:toggle-all+last+toggle+first',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-l:last'
]


def fzf(args):
    proc = sp.Popen(
       ["fzf"] + FZF_ARGS,
       stdin=sp.PIPE,
       stdout=sp.PIPE,
       universal_newlines=True
    )
    open(FZF_PID, 'w').write(str(proc.pid))
    out = proc.communicate('\n'.join(args))

    for fifo in [FIFO, PREVIEW_FIFO]:
        open(fifo, 'w').write('')


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
    while os.path.exists(PREVIEW_FIFO):
        with open(PREVIEW_FIFO, 'r') as fifo:
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

        with open(PREVIEW_FIFO, 'w') as fp:
            for i in output[:100]:
                fp.write(i + '\n')


def main():
    global db
    with open(DB, 'r') as fp:
        db = json.load(fp)

    os.mkfifo(FZF_FIFO)
    os.mkfifo(PREVIEW_FIFO)
    os.mkfifo(FIFO)

    t = Thread(target=preview_fifo)
    t.start()

    keys = list(db.keys())
    t = Thread(target=fzf, args=(keys,))
    t.start()

    old_db = []
    while os.path.exists(FIFO):
        with open(FIFO, 'r') as fifo:
            data = fifo.read()
            data = [i.strip() for i in data.split('\n') if i]

        if len(data) == 0 or 'die' in data:
            return

        files = list()
        for k in data:
            if k == '..':
                db = old_db[-1].copy()
                del old_db[-1]
                break

            if not isinstance(db[k], dict):
                files.append(db[k])

        if files:
            break
        elif k in db:
            output = [i for i in db[k]]
            old_db += [db.copy()]
            db = db[k].copy()
        else:
            output = [k for k in db]
        output += ['..'] if old_db else []

        with open(FIFO, 'w') as fifo:
            fifo.write('\n'.join(output))

    with open(FZF_PID, 'r') as fp:
        os.kill(int(fp.read().strip()), signal.SIGTERM)

    with open(DL_FILE, 'w') as fp:
        fp.write('\n'.join(url for url in files))

    sp.run([
        'aria2c', '-j', '2',
        '--dir', DL_DIR, f'--input-file={DL_FILE}'
    ])


if __name__ == '__main__':
    try:
        main()
    finally:
        for i in [DL_FILE, FIFO, PREVIEW_FIFO, FZF_FIFO, FZF_PID]:
            if os.path.exists(i):
                os.remove(i)
