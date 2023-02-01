#!/usr/bin/env python3
from utils import *
from sys import argv, stdout, exit
from threading import Thread
from time import sleep
import json
import signal
import subprocess as sp
import re
import traceback

SCRIPT = os.path.realpath(__file__)
FIFO = '/tmp/anitsu.fifo'
PREVIEW_FIFO = '/tmp/anitsu.preview.fifo'
UB_FIFO = '/tmp/anitsu.ueberzug.fifo'
RE_EXT = re.compile(r'.*\.(?:mkv|avi|mp4|webm|ogg|mov|rmvb|mpg|mpeg)$')

has_ueberzug = False
try:
    if os.getenv('DISPLAY'):
        import ueberzug.lib.v0 as ueberzug
        has_ueberzug = True
except ImportError:
    pass

PID = os.getpid()
DL_FILE = os.path.join(f'/tmp/anitsu.{PID}')
FZF_PID = '/tmp/anitsu.fzf'
FZF_ARGS = [
    '-m', '--cycle',
    '--border', 'none',
    '--header', 'ctrl-d ctrl-a ctrl-g ctrl-t shift+left shift+right',
    '--preview-window', 'left:52%:border-none',
    '--preview', f"printf '%s' {{}} > {PREVIEW_FIFO} && cat {PREVIEW_FIFO}",
    '--bind', f"enter:reload(printf '%s\\n' {{+}} > {FIFO} && cat {FIFO})+clear-query",
    '--bind', f"shift-left:reload(printf .. > {FIFO})+clear-query",
    '--bind', f"shift-right:reload(printf '%s' {{}} > {FIFO})+clear-query",
    '--bind', f"ctrl-d:execute(printf '%s\\n' download_folder {{+}} > {FIFO})",
    '--bind', 'ctrl-a:toggle-all',
    '--bind', 'ctrl-g:first',
    '--bind', 'ctrl-t:last',

]
ARIA2_ARGS = ['-j', '2']


def get_psize(size):
    units = ["KB", "MB", "GB", "TB", "PB"]
    psize = f"{size} B"
    for i in units:
        if size < 1000:
            break
        size /= 1000
        psize = f"{size:8.2f} {i}"
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
        with open(fifo, 'w') as fp:
            fp.write('')
        try:
            os.remove(fifo)
        except FileNotFoundError:
            pass

    for i in [UB_FIFO, PREVIEW_FIFO, FIFO]:
        if os.path.exists(i):
            t = Thread(target=kill, args=(i,))
            t.start()
            threads.append(t)


def preview(arg: str, files: list):
    """ List files and send back to fzf and the post image to ueberzug """
    output = ['\n' * 22] if has_ueberzug else [] 

    try:
        post_id = re.search(r' \(post-(\d+)\)$', arg).group(1)
        img = os.path.join(IMG_DIR, f'{post_id}.jpg')
        if os.path.exists(img) and has_ueberzug:
            open(UB_FIFO, 'w').write(img)
    except AttributeError:
        pass

    total = 0
    files = sorted(files, key=lambda x: isinstance(
        re.match(r'.*\(size-\d+\)', x), re.Match
    ))  # directories first
    for i in range(len(files)):
        s = files[i].strip()
        try:
            size = int(re.search(r' \(size-(\d+)\)$', s).group(1))
            total += size
            size = get_psize(size)
            s = re.sub(r' \((?:size|post)-.*$', '', s)
            s = f'{size} {MAG}{s}{END}'
        except AttributeError:  # is a directory
            s = re.sub(r' \((?:size|post)-.*$', '', s)
            s = f'{BLU}{s}{END}'
        files[i] = s

    if total > 0:
        output += [f'Total size: {get_psize(total)}\n']
    with open(PREVIEW_FIFO, 'w') as fifo:
        fifo.write('\n'.join(output + files))


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
            k = fifo.read()

        if len(k) == 0:
            return

        output = list()
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

        try:
            preview(k, output[:80])
        except Exception:
            with open('error.log', 'w') as fp:
                traceback.print_exc(file=fp)


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

    for i in [FIFO, PREVIEW_FIFO]:
        if os.path.exists(i):
            os.remove(i)
        os.mkfifo(i)

    if has_ueberzug:
        os.mkfifo(UB_FIFO)
        t = Thread(target=ueberzug_fifo)
        t.start()
        threads.append(t)

    with open(FILES_DB, 'r') as fp:
        db = json.load(fp)

    t = Thread(target=preview_fifo)
    t.start()
    threads.append(t)

    # keys = sorted(db)
    keys = sorted(db, reverse=True,
                  key=lambda x: int(re.search(r'post-(\d+)', x).group(1)))
    t = Thread(target=fzf, args=(keys[::-1],))
    t.start()
    threads.append(t)

    files = list()
    old_db = list()
    while os.path.exists(FIFO):
        with open(FIFO, 'r') as fifo:
            data = fifo.read()
            data = [i for i in data.split('\n') if i]

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
            if k == '..' and len(data) == 1:
                if len(old_db) > 0:
                    db = old_db[-1].copy()
                    del old_db[-1]
                break
            elif k in db and k != '..':
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
    import subprocess as sp
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
        threads = []
        if os.path.exists(FIFO):
            raise FileExistsError(FIFO)

        if not os.path.exists(FILES_DB):
            update(args)

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
        script = SCRIPT.split('/')[-1]
        print(f'Usage: {script} [update -i --download-images]')
