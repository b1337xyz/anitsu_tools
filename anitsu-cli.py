#!/usr/bin/env python3
from sys import argv, stdout, stderr
from threading import Thread
from time import sleep
import json
import os
import re
import signal
import subprocess as sp
import sys

has_ueberzug = False
try:
    if os.getenv('DISPLAY'):
        import ueberzug.lib.v0 as ueberzug
        has_ueberzug = True
except ImportError:
    pass

SCRIPT = os.path.realpath(__file__)
HOME = os.getenv('HOME')
ROOT = os.path.dirname(os.path.realpath(__file__))
IMG_DIR = os.path.join(HOME, '.cache/anitsu_covers')
DL_DIR = os.path.join(HOME, 'Downloads')
DB = os.path.join(HOME, '.local/share/anitsu_files.json')

DL_FILE = '/tmp/anitsu'
PREVIEW_FIFO = '/tmp/anitsu.preview.fifo'
FIFO = '/tmp/anitsu.fifo'
FZF_PID = '/tmp/anitsu.fzf.pid'
UB_FIFO = '/tmp/anitsu.ueberzug'
# PID = os.getpid()
RE_EXT = re.compile(r'.*\.(mkv|avi|mp4|webm|ogg|mov|rmvb|mpg|mpeg)$')

FZF_ARGS = [
    '-m',
    '--border', 'none',
    '--preview-window', 'left:52%:border-none',
    '--bind', f'enter:reload(python3 {SCRIPT} reload {{+}})+clear-query',
    '--preview', f'python3 {SCRIPT} preview {{}}',
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
    if proc.returncode != 0:
        sleep(0.3)
        cleanup()


def cleanup():
    """ Make sure that every FIFO dies and temporary files are deleted """

    os.system('clear')

    if os.path.exists(FZF_PID):
        try:
            with open(FZF_PID, 'r') as fp:
                pid = int(fp.read().strip())
            os.kill(pid, signal.SIGTERM)
            os.remove(FZF_PID)
        except Exception as err:
            pass

    for i in [UB_FIFO, PREVIEW_FIFO, FIFO]:
        if os.path.exists(i):
            with open(i, 'w') as fp:
                fp.write('')
            os.remove(i)

    # kill ueberzug
    # sp.run(['pkill', '-9', '-f', 'ueberzug'])

    # kill it self
    # os.kill(PID, signal.SIGTERM)


def reload(args):
    """ Receive a key from the FIFO and output it's items to fzf """

    with open(FIFO, 'w') as fifo:
        fifo.write('\n'.join(args))

    with open(FIFO, 'r') as fifo:
        data = fifo.read()

    for i in [i.strip() for i in data.split('\n') if i]:
        stdout.write(f'{i}\n')


def preview(arg):
    """ List files and send the post image to ueberzug FIFO """

    with open(PREVIEW_FIFO, 'w') as fifo:
        fifo.write(f'{arg}\n')

    with open(PREVIEW_FIFO, 'r') as fifo:
        data = fifo.read().split('\n')

    if has_ueberzug:
        stdout.write('\n' * 22)

    try:
        post_id = re.search(r' \(post-(\d+)\)$', arg).group(1)
        img = os.path.join(IMG_DIR, f'{post_id}.jpg')
    except AttributeError:
        img = ''

    try:
        total = re.search(r' \(total-([^\)]*)\)', data[-1]).group(1)
        stdout.write(f'Total size: {total}\n')
    except AttributeError:
        pass

    for i in data:
        try:
            size = re.search(r' \(size-(\d+[^\)]*)', i).group(1)
        except AttributeError:
            size = ''

        i = re.sub(r' \((?:size|total|post)-.*$', '', i)
        if RE_EXT.match(i.lower()):
            stdout.write(f'{size:<9} \033[1;35m{i}\033[m\n')
        else:
            stdout.write(f'{size:<9} \033[1;34m{i}\033[m\n')
    stdout.flush()

    if os.path.exists(img) and has_ueberzug:
        open(UB_FIFO, 'w').write(img)


def ueberzug_fifo():
    """ Ueberzug fifo listener """

    # https://github.com/b1337xyz/ueberzug#python
    with ueberzug.Canvas() as canvas:
        pv = canvas.create_placement(
            'pv', x=0, y=0, width=32, height=20,
            scaler=ueberzug.ScalerOption.DISTORT.value
        )
        while os.path.exists(UB_FIFO):
            with open(UB_FIFO, 'r') as fifo:
                img = fifo.read().strip()

            if len(img) == 0:
                break

            pv.path = img
            pv.visibility = ueberzug.Visibility.VISIBLE


def preview_fifo():
    """ Preview fifo listener """

    def rec(q, data):
        """ Recursively find "directories" and return them """

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

        if not output and k != '..':
            output = [k]

        with open(PREVIEW_FIFO, 'w') as fp:
            fp.write('\n'.join(output[:80]))


def main():
    global db, threads
    threads = list()

    for i in [FIFO, UB_FIFO, PREVIEW_FIFO]:
        if os.path.exists(i):
            os.remove(i)

    if has_ueberzug:
        os.mkfifo(UB_FIFO)

    for i in [PREVIEW_FIFO, FIFO]:
        os.mkfifo(i)

    with open(DB, 'r') as fp:
        db = json.load(fp)

    t = Thread(target=preview_fifo)
    t.start()
    threads.append(t)

    t = Thread(target=ueberzug_fifo)
    t.start()
    threads.append(t)

    keys = list(db.keys())
    t = Thread(target=fzf, args=(keys,))
    t.start()
    threads.append(t)

    files = list()
    old_db = list()
    while os.path.exists(FIFO):
        with open(FIFO, 'r') as fifo:
            data = fifo.read()
            data = [i.strip() for i in data.split('\n') if i]

        if len(data) == 0:
            break

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

    if os.path.exists(FIFO):
        os.remove(FIFO)

    if files:
        cleanup()

        with open(DL_FILE, 'w') as fp:
            fp.write('\n'.join(url for url in files))

        try:
            p = sp.run([
                'aria2c', '-j', '2',
                '--dir', DL_DIR, f'--input-file={DL_FILE}'
            ])
        except KeyboardInterrupt:
            pass
        finally:
            os.remove(DL_FILE)


if __name__ == '__main__':
    if len(argv) == 1:
        try:
            main()
        finally:
            print('\nbye')
            for i in threads:
                if i.is_alive():
                    # print(i.name)
                    i.join()

    elif 'preview' == argv[1]:
        preview(argv[2])
    elif 'reload'  == argv[1]:
        reload(argv[2:])
