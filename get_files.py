#!/usr/bin/env python3
from utils import *
from aiohttp import ClientSession, BasicAuth
from urllib.parse import unquote
from html import unescape
from collections import defaultdict
from xml.dom import minidom
from shutil import which
import random
import asyncio
import json

Q_SIZE = 20
MAX_ATTEMPTS = 3
RE_GD_FOLDERID = re.compile(r'/folders/([^\?$/]*)')
RE_GD_FILEID = re.compile(r'(?:[\?&]id=([^&$]*)|/file/d/([^/\?$]*))')
UNITS = {"B": 1, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}
HAS_GDRIVE = which('gdrive')
HAS_RCLONE = which('rclone')


async def random_sleep():
    await asyncio.sleep(random.random() * .5)


def tree():
    return defaultdict(tree)


def set_value(root, path, value):
    for d in path[:-1]:
        root = root[unquote(d).strip()]
    root[path[-1]] = value


def parse_size(size):
    unit = size[-1]
    number = size[:-1]
    return int(float(number) * UNITS[unit])


async def google_drive(k, url):
    if '/folders/' in url and HAS_RCLONE:
        ID = RE_GD_FOLDERID.search(url).group(1)
        try:
            p = await asyncio.create_subprocess_shell(' '.join([
                'rclone', 'lsjson', '-R', '--fast-list',
                '--files-only', '--no-modtime', '--no-mimetype',
                '--drive-root-folder-id', ID, 'Anitsu:'
            ]), stdout=asyncio.subprocess.PIPE)
            stdout, _ = await p.communicate()
            data = json.loads(stdout.decode())
        except Exception as err:
            print(f'Key: {k}, Error: {err}\n{url}')
            return

        root = tree()
        for file in data:
            size = file['Size']
            dl_link = f'https://drive.google.com/uc?id={file["ID"]}&export=download&confirm=t'
            path = file['Path'].split('/')
            path[-1] = f'{path[-1]} (size-{size})'
            set_value(root, path, dl_link)
    else:
        if '/file/' in url:
            ID = RE_GD_FILEID.search(url).group(2)
        elif 'id=' in url:
            ID = RE_GD_FILEID.search(url).group(1)

        if not ID:
            print(f'ID not found: {url}')
            return

        if HAS_GDRIVE:
            # if you know how to do this with rclone please tell me T_T
            try:
                p = await asyncio.create_subprocess_shell(' '.join([
                    'gdrive', 'info', '--bytes', ID
                ]), stdout=asyncio.subprocess.PIPE)
                stdout, _ = await p.communicate()
                stdout = stdout.decode()
            except Exception as err:
                print(f'Key: {k}, Error: {err}\n{url}')
                return

            root = tree()
            try:
                filename = re.search(r'(?:^|\n)Name: ([^\n]*)', stdout).group(1)
                size = re.search(r'(?:^|\n)Size: (\d+)', stdout).group(1)
                dl_link = re.search(r'(?:^|\n)DownloadUrl: ([^\n]*)', stdout).group(1)
            except Exception as err:
                print(f'Key: {k}, Error: {err}\n{url}')
                return
            filename = f'{filename} (size-{size})'
        else:
            url = f'https://drive.google.com/uc?id={ID}&export=download'
            async with session.get(url) as r:
                out = await r.text()

            if 'Too many users have viewed or downloaded this file recently' in out:
                print(f'429, {url}')
                return

            try:
                # filename = re.search(r'>([^<]*\.(?:mkv|mp4|avi))', out).group(1)
                # size = re.search(r' \(((?:\d+|\d+\.\d+)[BMKGT])\)</span>', out).group(1)
                filename, size = re.search(
                    r'href\=\"\/open.*?>([^<]+)\<\/a\> \((\d+.)\)', out
                ).group(1, 2)

                # https://stackoverflow.com/questions/42865724/parse-human-readable-filesizes-into-bytes
                size = parse_size(size)
            except Exception as err:
                print(out)
                print(f'Key: {k}, Error: {err}\n{url}')
                return

        dl_link = f'https://drive.google.com/uc?id={ID}&export=download&confirm=t'
        filename = f'{unescape(filename)} (size-{size})'
        root[filename] = dl_link

    # print(json.dumps(root, indent=2))
    db[k]['gdrive'][url] = root


async def nextcloud(k, url, password=''):
    user = url.split('/')[-1]
    domain = url.split("/")[0]
    webdav = f'{domain}/nextcloud/public.php/webdav'
    auth = BasicAuth(user, password)
    att = 0
    while att < MAX_ATTEMPTS:
        try:
            async with session.request(method='PROPFIND', url=f'https://{webdav}', auth=auth, headers={'Depth': 'infinity'}) as r:
                xml = await r.text()
                if r.status in [200, 207]:
                    break
        except Exception as err:
            print(f'\033[1;31m{err}\033[m\n{url}')
        att += 1
        await random_sleep()
    else:
        return

    dom = minidom.parseString(xml)

    root = tree()
    for e in dom.getElementsByTagName('d:response'):
        href = e.getElementsByTagName('d:href')
        if not href:
            continue
        path = href[0].firstChild.data.split('webdav')[-1][1:]

        if not path:
            # hopefully the first item of this loop... :-)
            # total = size
            continue

        if path.endswith('/'):
            continue

        prop = e.getElementsByTagName('d:prop')[0]
        size = prop.getElementsByTagName('d:getcontentlength')
        size = size[0].firstChild.data

        dl_link = f'https://{user}:{password}@{webdav}/{path}'
        path = path.split('/')
        path[-1] = unquote(f'{path[-1]} (size-{size})')
        set_value(root, path, dl_link)

    if not root and 'contenttype>video/' in xml:
        try:
            async with session.request(method='HEAD', url=f'https://{webdav}', auth=auth) as r:
                content = r.headers['content-disposition']
        except Exception as err:
            print(f'\033[1;31m{err}\033[m\n{url}')
            return
        dl_link = f'https://{user}:{password}@{webdav}/'
        size = re.search(r'd:getcontentlength>(\d+)<', xml).group(1)
        filename = re.search(r'filename=\"([^\"]*)', content).group(1)
        filename = f'{unquote(filename)} (size-{size})'
        root[filename] = dl_link

    db[k]['nextcloud'][url] = root


async def q_handler(queue: asyncio.Queue):
    while True:
        k, url = await queue.get()
        pw = ''
        if 'password' in db[k]:
            pw = db[k]['password']

        if '/nextcloud/' in url:
            await nextcloud(k, url, pw)
        elif 'drive.google' in url:
            await google_drive(k, url)

        await random_sleep()
        queue.task_done()


async def main():
    global session, db, qsize
    with open(DB, 'r') as fp:
        db = json.load(fp)

    queue = asyncio.Queue()
    async with ClientSession() as session:
        for k, v in db.items():
            for url in v['nextcloud']:
                if not v['nextcloud'][url] or db[k]['is_release']:
                    queue.put_nowait((k, url))
            for url in v['gdrive']:
                if not v['gdrive'][url] or db[k]['is_release']:
                    queue.put_nowait((k, url))

        qsize = queue.qsize()
        print(f'{qsize} items to update, please wait...')
        tasks = []
        for _ in range(Q_SIZE):
            tasks += [asyncio.create_task(q_handler(queue))]
        await queue.join()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    with open(DB, 'w') as fp:
        json.dump(db, fp)

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
            t += count(data[k]) if isinstance(data[k], dict) else 1
        return t

    print(count(files))
    files = {k: files[k] for k in sorted(list(files.keys()))}
    with open(FILES_DB, 'w') as fp:
        json.dump(files, fp)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
