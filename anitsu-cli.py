#!/usr/bin/env python3
from utils import *
from sys import argv, exit
from threading import Thread
from shutil import which
import xmlrpc.client
import signal
import json
import subprocess as sp

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
FZF_PID = f'/tmp/anitsu.fzf.{PID}'
DL_FILE = f'/tmp/anitsu.{PID}'
FIFO = f'/tmp/anitsu.{PID}.fifo'
PREVIEW_FIFO = f'/tmp/anitsu.preview.{PID}.fifo'
UB_FIFO = f'/tmp/anitsu.ueberzug.{PID}.fifo'

PROMPT = f'{NAME}> '
HEADER = '''^d ^a ^f ^g ^t ^h ^l ^c'''
FZF_ARGS = [
    '-m',
    '--delimiter=:', '--with-nth=3..',
    '--border', 'none',
    '--prompt', PROMPT,
    '--header', HEADER,
    '--preview-window', 'left:52%:border-none',
    '--preview', f"printf '%s' {{}} > {PREVIEW_FIFO} && cat {PREVIEW_FIFO}",
    '--bind', f"enter:reload(printf '%s\\n' {{+}} > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-h:reload(printf ::.. > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-l:reload(printf '%s' {{}} > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"ctrl-f:reload(printf 'files_only\\n' > {FIFO} && cat {FIFO})",
    '--bind', f"ctrl-d:execute(printf '%s\\n' download_folder {{+}} > {FIFO}; cat {FIFO})+clear-selection",
    '--bind', 'ctrl-a:toggle-all',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-t:last',
    '--bind', 'end:preview-bottom',
    '--bind', 'home:preview-top'
]
WIDTH = 36  # preview width
HEIGHT = 24
PORT = 6800  # RPC port
ARIA2_CONF = {  # RPC config
    'dir': DL_DIR,
    'force-save': 'false',
    'check-integrity': 'true',
    'max-concurrent-downloads': 2
}
ARIA2_ARGS = [
    '-j', '2',
    '--dir', DL_DIR,
    f'--input-file={DL_FILE}'
]


def get_psize(size: int):
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
        os.remove(FZF_PID)
        cleanup()


def kill_fzf():
    if not os.path.exists(FZF_PID):
        return

    try:
        with open(FZF_PID, 'r') as f:
            pid = int(f.read())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


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
                img = [i for i in fifo.read().split('\n') if i]

            if len(img) == 0:
                break

            pv.path = img[-1]
            pv.visibility = ueberzug.Visibility.VISIBLE


def preview(key: str, files: list):
    """ List files and send to fzf preview and the post image to ueberzug """
    post_id, size = key.split(':')[:2]
    img = os.path.join(IMG_DIR, f'{post_id}.jpg')
    output = [] if not has_ueberzug else ['\n' * HEIGHT]
    if os.path.exists(img):
        if has_ueberzug:
            with open(UB_FIFO, 'w') as ub_fifo:
                ub_fifo.write(f'{img}\n')
        elif has_viu:
            output += [sp.run([
                'viu', '-w', str(WIDTH), '-h', str(HEIGHT), img
            ], stdout=sp.PIPE).stdout.decode()]
        elif has_chafa:
            output += [sp.run(['chafa', f'--size={WIDTH}x{HEIGHT}', img],
                              stdout=sp.PIPE).stdout.decode()]

    files = sorted(files,
                   key=lambda x: int(x.split(':')[1]) > 0)  # dirs first
    total = 0
    for i, v in enumerate(files):
        filename = ':'.join(v.split(':')[2:])
        _, size = v.split(':')[:2]
        size = int(size)
        total += size
        if size > 0:
            psize = get_psize(size)
            files[i] = f'{psize} {MAG}{filename}{END}'
        else:
            files[i] = f'{BLU}{filename}{END}'

    if total > 0:
        psize = get_psize(total).strip()
        output += [f'Total size: {psize}']

    with open(PREVIEW_FIFO, 'w') as fifo:
        fifo.write('\n'.join(output + files))


def preview_fifo():
    """ Preview fifo listener """
    while os.path.exists(PREVIEW_FIFO):
        with open(PREVIEW_FIFO, 'r') as fifo:
            data = [i for i in fifo.read().split('\n') if i]

        if len(data) == 0:
            return

        k = data[-1]
        if k == '::..':  # show nothing
            open(PREVIEW_FIFO, 'w').write('go back')
            continue
        elif isinstance(db[k], dict):  # is a directory
            output = [i for i in db[k]]
        else:  # is a file
            output = [k]

        preview(k, output[:80])


def find_files(data) -> list:
    """ Recursively find "files" and return there values """
    if isinstance(data, str):
        return [data]

    files = []
    for k in data:
        files += find_files(data[k]) if isinstance(data[k], dict) else [data[k]]
    return files


def files_only(d: dict) -> dict:
    """ Recursively find "files" and return them as {key: value, ...} """
    out = dict()
    for k in d:
        if isinstance(d[k], dict):
            out.update(files_only(d[k]))
        else:
            out[k] = d[k]
    return out


def download(files: list):
    session = xmlrpc.client.ServerProxy(f'http://localhost:{PORT}/rpc')
    try:
        for uri in files:
            session.aria2.addUri([uri], ARIA2_CONF)
        return
    except ConnectionRefusedError:
        pass

    os.remove(FIFO)
    kill_fzf()

    with open(DL_FILE, 'w') as fp:
        fp.write('\n'.join(files))

    try:
        p = sp.run(['aria2c'] + ARIA2_ARGS)
        if p.returncode == 0:
            os.remove(DL_FILE)
    except KeyboardInterrupt:
        pass


def fzf_reload(keys: list):
    """ Handles fzf reload() """

    # This part of the code needs to be here otherwise
    # preview_fifo() won't be able to access changes in `db`
    global db

    back = '::..'
    old_db = []
    files_only_on = False
    output = keys
    while os.path.exists(FIFO):
        with open(FIFO, 'r') as fifo:
            data = [i for i in fifo.read().split('\n') if i]

        if len(data) == 0:
            break

        files = []
        if 'download_folder' in data:
            for k in data[1:]:
                files += find_files(db[k])
            download(files)
        elif 'files_only' in data:
            if files_only_on:
                db = old_db[-1].copy()
            else:
                old_db += [db.copy()]
                db = files_only(db.copy())
            files_only_on = not files_only_on
            output = list(db.keys())
        else:
            for k in data:
                if k == back and len(data) == 1:
                    if len(old_db) > 0:
                        db = old_db[-1].copy()
                        del old_db[-1]
                    break
                elif k in db and not isinstance(db[k], dict):
                    files.append(db[k])

            if files:
                download(files)
            elif k in db:
                output = [i for i in db[k]]
                old_db += [db.copy()]
                db = db[k].copy()
            else:
                output = list(db.keys())

            output += [back] if old_db and back not in output else []

        if not os.path.exists(FIFO):
            break

        with open(FIFO, 'w') as fifo:
            fifo.write('\n'.join(output))


def main():
    global db, threads
    with open(FILES_DB, 'r') as fp:
        db = json.load(fp)
    keys = sorted(db)

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

    fzf_reload(keys)


def update(args):
    os.chdir(ROOT)
    for script in ['get_posts.py', 'get_files.py']:
        print(f'>>> Running {script}')
        p = sp.run(['python3', script])
        if p.returncode != 0:
            exit(p.returncode)
        print()

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
