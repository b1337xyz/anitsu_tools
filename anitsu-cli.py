#!/usr/bin/env python3
from utils import *
from sys import argv, exit
from threading import Thread
from shutil import which
import json
import signal
import subprocess as sp
import re

has_ueberzug = False
try:
    if os.getenv('DISPLAY'):
        import ueberzug.lib.v0 as ueberzug
        has_ueberzug = True
except ImportError:
    pass
has_viu = which('viu')
has_chafa = which('chafa')

PID = os.getpid()
SCRIPT = os.path.realpath(__file__)
NAME = SCRIPT.split('/')[-1]
DL_FILE = f'/tmp/anitsu.{PID}'
FIFO = f'/tmp/anitsu.{PID}.fifo'
PREVIEW_FIFO = f'/tmp/anitsu.preview.{PID}.fifo'
UB_FIFO = f'/tmp/anitsu.ueberzug.{PID}.fifo'
FZF_PID = f'/tmp/anitsu.{PID}.fzf'

PROMPT = f'{NAME}> '
HEADER = '''ctrl-d download ctrl-a toggle selection
ctrl-g bottom   ctrl-t top
ctrl-h back     ctrl-l foward'''
FZF_ARGS = [
    '-m', '--cycle',
    '--border', 'none',
    '--prompt', PROMPT,
    '--header', HEADER,
    '--preview-window', 'left:52%:border-none',
    '--preview', f"printf '%s' {{}} > {PREVIEW_FIFO} && cat {PREVIEW_FIFO}",
    '--bind', f"enter:reload(printf '%s\\n' {{+}} > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-h:reload(printf .. > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-l:reload(printf '%s' {{}} > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-d:execute(printf '%s\\n' download_folder {{+}} > {FIFO})",
    '--bind', 'ctrl-a:toggle-all',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-t:last',
]
ARIA2_ARGS = ['-j', '2']

WIDTH = 36  # preview width
HEIGHT = 24


def get_psize(size):
    psize = f"{size} B"
    for i in 'BMG':
        if size < 1000:
            break
        size /= 1000
        psize = f"{size:8.2f} {i}"
    return psize


def fzf(args):
    try:
        proc = sp.Popen(
            ["fzf"] + FZF_ARGS,
            stdin=sp.PIPE, stdout=sp.PIPE,
            universal_newlines=True
        )
        open(FZF_PID, 'w').write(str(proc.pid))
        proc.communicate('\n'.join(args))
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()  # kill the preview


def kill_fzf():
    if not os.path.exists(FZF_PID):
        return

    try:
        with open(FZF_PID, 'r') as fp:
            pid = int(fp.read())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    finally:
        os.remove(FZF_PID)


def kill_fifo(fifo: str):
    if not os.path.exists(fifo):
        return

    with open(fifo, 'w') as fp:
        fp.write('')

    try:
        os.remove(fifo)
    except FileNotFoundError:
        pass


def cleanup():
    """ Make sure that every FIFO dies and temporary files are deleted """

    for i in [UB_FIFO, PREVIEW_FIFO, FIFO]:
        t = Thread(target=kill_fifo, args=(i,))
        t.start()
        threads.append(t)


def ueberzug_fifo():
    """ Ueberzug fifo listener """

    # https://github.com/b1337xyz/ueberzug#python
    with ueberzug.Canvas() as canvas:
        pv = canvas.create_placement(
            'pv', x=0, y=0, width=WIDTH, height=HEIGHT,
            scaler=ueberzug.ScalerOption.DISTORT.value
        )
        while os.path.exists(UB_FIFO):
            with open(UB_FIFO, 'r') as fifo:
                img = fifo.read().strip()

            if len(img) == 0:
                break

            pv.path = img
            pv.visibility = ueberzug.Visibility.VISIBLE


def clean_string(string: str) -> str:
    return re.sub(r' \((?:size|post)-.*$', '', string)


def preview(key: str, files: list):
    """ List files and send to fzf preview and the post image to ueberzug """
    try:
        post_id = re.search(r' \(post-(\d+)\)$', key).group(1)
        img = os.path.join(IMG_DIR, f'{post_id}.jpg')
    except AttributeError:
        img = ''

    output = []
    if os.path.exists(img):
        if has_ueberzug:
            output = ['\n' * 21]
            with open(UB_FIFO, 'w') as ub_fifo:
                ub_fifo.write(img)
        elif has_viu:
            output += [sp.run(['viu', '-w', str(WIDTH), '-h', str(HEIGHT), img],
                              stdout=sp.PIPE).stdout.decode()]
        elif has_chafa:
            output += [sp.run(['chafa', f'--size={WIDTH}x{HEIGHT}', img],
                              stdout=sp.PIPE).stdout.decode()]

    total = 0
    files = sorted(files, key=lambda x: isinstance(
        re.match(r'.*\(size-\d+\)', x), re.Match
    ))  # directories first
    for i, v in enumerate(files):
        try:
            size = int(re.search(r' \(size-(\d+)\)$', v).group(1))
            total += size
            s = f'{get_psize(size)} {MAG}{clean_string(v)}{END}'
        except AttributeError:  # is a directory
            s = f'{BLU}{clean_string(v)}{END}'
        files[i] = s

    if total > 0:
        output += [f'Total size: {get_psize(total).strip()}']

    with open(PREVIEW_FIFO, 'w') as fifo:
        fifo.write('\n'.join(output + files))


def preview_fifo():
    """ Preview fifo listener """
    while os.path.exists(PREVIEW_FIFO):
        with open(PREVIEW_FIFO, 'r') as fifo:
            k = fifo.read()

        if len(k) == 0:
            return
        elif k == '..':  # show nothing
            open(PREVIEW_FIFO, 'w').write('')
            continue
        elif isinstance(db[k], dict):  # is a directory
            output = [i for i in db[k]]
        else:  # is a file
            output = [k]

        preview(k, output[:80])


def find_files(data):
    """ Recursively find "files" and return them """
    files = []
    for k in data:
        files += find_files(data[k]) if isinstance(data[k], dict) else [data[k]]
    return files


def main():
    global db, threads
    with open(FILES_DB, 'r') as fp:
        db = json.load(fp)

    keys = sorted(db, reverse=True,
                  key=lambda x: int(re.search(r'post-(\d+)', x).group(1)))

    for i in [FIFO, PREVIEW_FIFO]:
        os.mkfifo(i)

    if has_ueberzug:
        os.mkfifo(UB_FIFO)
        t = Thread(target=ueberzug_fifo)
        t.start()
        threads.append(t)

    t = Thread(target=preview_fifo)
    t.start()
    threads.append(t)

    t = Thread(target=fzf, args=(keys,))
    t.start()
    threads.append(t)

    old_db = []
    files = []
    while os.path.exists(FIFO):
        with open(FIFO, 'r') as fifo:
            data = fifo.read()

        if len(data) == 0:
            break

        data = [i for i in data.split('\n') if i]
        if 'download_folder' in data:
            for k in data[1:]:
                files += find_files(db[k])
            break

        for k in data:
            if k == '..' and len(data) == 1:
                if len(old_db) > 0:
                    db = old_db[-1].copy()
                    del old_db[-1]
                break
            elif k in db and not isinstance(db[k], dict) and k != '..':
                files.append(db[k])  # ignore .. if selected

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

    try:
        os.remove(FIFO)
    except FileNotFoundError:
        pass

    kill_fzf()  # kill fzf and the preview

    if files:
        with open(DL_FILE, 'w') as fp:
            fp.write('\n'.join(files))

        try:
            p = sp.run([
                'aria2c', '--dir', DL_DIR, f'--input-file={DL_FILE}'
            ] + ARIA2_ARGS)
            if p.returncode == 0:
                os.remove(DL_FILE)
        except KeyboardInterrupt:
            pass


def update(args):
    os.chdir(ROOT)
    for script in ['get_posts.py', 'get_files.py']:
        print(f'>>> Running {script}')
        p = sp.run(['python3', script])
        if p.returncode != 0:
            exit(p.returncode)

    if '-i' in args or '--download-images' in args:
        sp.run(['python3', 'download_images.py'])


if __name__ == '__main__':
    args = argv[1:]
    if not args:
        if not os.path.exists(FILES_DB):
            print(f'{FILES_DB} not found, creating it...')
            update(args)

        threads = []
        try:
            main()
        finally:
            for i in threads:
                if i.is_alive():
                    print(f'waiting for {i.name} ...')
                    i.join()
            print('bye ^-^')
    elif 'update' in args:
        update(args)
    else:
        print(f'Usage: {NAME} [update -i --download-images]')
