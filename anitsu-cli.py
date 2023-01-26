#!/usr/bin/env python3
from sys import argv, stdout
from threading import Thread
from time import sleep
import json
import os
import re
import signal
import subprocess as sp

has_ueberzug = False
try:
    if os.getenv('DISPLAY'):
        import ueberzug.lib.v0 as ueberzug
        has_ueberzug = True
except ImportError:
    pass

SCRIPT = os.path.realpath(__file__)
ROOT = os.path.dirname(SCRIPT)
HOME = os.getenv('HOME')
IMG_DIR = os.path.join(HOME, '.cache/anitsu_covers')
DL_DIR = os.path.join(HOME, 'Downloads')
DB = os.path.join(HOME, '.local/share/anitsu_files.json')
PID = os.getpid()

DL_FILE = f'/tmp/anitsu.{PID}'
FIFO = '/tmp/anitsu.fifo'
PREVIEW_FIFO = '/tmp/anitsu.preview.fifo'
UB_FIFO = '/tmp/anitsu.ueberzug.fifo'
FZF_PID = '/tmp/anitsu.fzf'
RE_EXT = re.compile(r'.*\.(?:mkv|avi|mp4|webm|ogg|mov|rmvb|mpg|mpeg)$')

FZF_ARGS = [
    '-m',
    '--border', 'none',
    '--header', 'ctrl-d ctrl-a ctrl-g ctrl-t shift+left shift+right',
    '--preview', f'python3 {SCRIPT} preview {{}}',
    '--preview-window', 'left:52%:border-none',
    '--bind', f'enter:reload(python3 {SCRIPT} reload {{+}})+clear-query',
    '--bind', f'ctrl-d:execute(python3 {SCRIPT} download_folder {{+}})',
    '--bind', 'ctrl-a:toggle-all+last+toggle+first',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-t:last',
    '--bind', f'shift-left:reload(python3 {SCRIPT} reload ..)+clear-query',
    '--bind', f'shift-right:reload(python3 {SCRIPT} reload {{}})+clear-query'
]


def get_psize(size):
    units = ["KB", "MB", "GB", "TB", "PB"]
    psize = f"{size} B"
    for i in units:
        if size < 1000:
            break
        size /= 1000
        psize = f"{size:.2f} {i}"
    return psize


def fzf(args):
    try:
        proc = sp.Popen(
            ["fzf"] + FZF_ARGS,
            stdin=sp.PIPE,
            stdout=sp.PIPE,
            universal_newlines=True
        )
        open(FZF_PID, 'w').write(str(proc.pid))
        proc.communicate('\n'.join(args))
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()  # kill the preview


def kill_fzf():
    if os.path.exists(FZF_PID):
        try:
            with open(FZF_PID, 'r') as fp:
                pid = int(fp.read().strip())
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        finally:
            os.remove(FZF_PID)


def cleanup():
    """ Make sure that every FIFO dies and temporary files are deleted """
    sleep(0.3)
    def kill(fifo):
        if os.path.exists(fifo):
            with open(fifo, 'w') as fp:
                fp.write('')
            try:
                os.remove(fifo)
            except FileNotFoundError:
                pass

    for i in [UB_FIFO, PREVIEW_FIFO, FIFO]:
        t = Thread(target=kill, args=(i,))
        t.start()
        threads.append(t)


def download_folder(args):
    with open(FIFO, 'w') as fifo:
        fifo.write('\n'.join(args))


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

    total = 0
    data = sorted(data, key=lambda x: isinstance(
        re.match(r'.*\(size-\d+\)', x), re.Match
    ))  # directories first
    for i in range(len(data)):
        s = data[i].strip()
        try:
            size = int(re.search(r' \(size-(\d+)\)$', s).group(1))
            total += size
            size = get_psize(size)
            s = re.sub(r' \((?:size|post)-.*$', '', s)
            s = f'{size:<9} \033[1;35m{s}\033[m'
        except AttributeError:  # is a directory
            s = re.sub(r' \((?:size|post)-.*$', '', s)
            s = f'\033[1;34m{s}\033[m'
        data[i] = s

    if total > 0:
        stdout.write(f'Total size: {get_psize(total)}\n')
    stdout.write('\n'.join(data))
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


def find_files(data):
    """ Recursively find "files" and return them """
    files = []
    for k in data:
        if isinstance(data[k], str):
            files += [data[k]]
        else:
            files += find_files(data[k])
    return files


def main():
    global db, threads
    threads = list()

    for i in [PREVIEW_FIFO, FIFO]:
        if os.path.exists(i):
            os.remove(i)
        os.mkfifo(i)

    if has_ueberzug:
        os.mkfifo(UB_FIFO)
        t = Thread(target=ueberzug_fifo)
        t.start()
        threads.append(t)

    with open(DB, 'r') as fp:
        db = json.load(fp)

    t = Thread(target=preview_fifo)
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

        if 'download_folder' in data:
            data = data[1:]
            files = []
            try:
                for k in data:
                    files += find_files(db[k])
            except Exception as err:
                print(err)
            break

        for k in data:
            if k == '..':
                if len(old_db) > 0:
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

    kill_fzf()  # kill fzf and the preview

    if files:
        with open(DL_FILE, 'w') as fp:
            fp.write('\n'.join(url for url in files))

        try:
            sp.run([
                'aria2c', '-j', '2',
                '--dir', DL_DIR, f'--input-file={DL_FILE}'
            ])
        except KeyboardInterrupt:
            pass
        finally:
            os.remove(DL_FILE)


if __name__ == '__main__':
    args = argv[1:]
    threads = []
    if not args:
        if os.path.exists(FIFO):
            raise FileExistsError(FIFO)

        try:
            main()
        finally:
            for i in threads:
                if i.is_alive():
                    print(i.name)
                    i.join()

    elif 'download_folder' in args:
        download_folder(args)
    elif 'update' in args:
        script = os.path.join(ROOT, 'update.sh')
        sp.run(['bash', script])
    elif 'preview' in args:
        preview(args[1])
    elif 'reload' in args:
        reload(args[1:])
