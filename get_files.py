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
import re
import traceback
from sys import stderr

Q_SIZE = 20
MAX_ATTEMPTS = 3
RE_GD_FOLDERID = re.compile(r'/folders/([^\?$/]*)')
RE_GD_FILEID = re.compile(r'(?:[\?&]id=([^&$]*)|/file/d/([^/\?$]*))')
UNITS = {"B": 1, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}
HAS_GDRIVE = which('gdrive')
HAS_RCLONE = which('rclone')
GD_LINK = 'https://drive.google.com/uc?id={}&export=download&confirm=t'
counter = 1


def tree():
    return defaultdict(tree)


def set_value(root, path, value):
    for d in path[:-1]:
        root = root[unquote(d).strip()]
    root[path[-1]] = value


def parse_size(size: str) -> int:
    # https://stackoverflow.com/questions/42865724/parse-human-readable-filesizes-into-bytes
    unit = size[-1]
    number = size[:-1]
    return int(float(number) * UNITS[unit])


async def random_sleep():
    await asyncio.sleep(random.random() * .5)


async def gd_get_folder(folder_id: str) -> dict:
    p = await asyncio.create_subprocess_shell(' '.join([
        'rclone', 'lsjson', '-R', '--fast-list',
        '--files-only', '--no-modtime', '--no-mimetype',
        '--drive-root-folder-id', folder_id, 'Anitsu:'
    ]), stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    return json.loads(out.decode())


async def gd_get_file(file_id: str) -> str:
    if HAS_GDRIVE:
        # if you know how to do this with rclone please tell me T_T
        p = await asyncio.create_subprocess_shell(' '.join([
            'gdrive', 'info', '--bytes', file_id
        ]), stdout=asyncio.subprocess.PIPE)
        out, _ = await p.communicate()
        return out.decode()

    url = f'https://drive.google.com/uc?id={file_id}&export=download'
    async with session.get(url) as r:
        return await r.text()


async def google_drive(key: str, url: str):
    root = tree()
    if '/folders/' in url:
        if not HAS_RCLONE:
            stderr.write(f'{RED}Install rclone!!\nSkipping {url = }...{END}\n')
            return

        folder_id = RE_GD_FOLDERID.search(url).group(1)
        try:
            data = await gd_get_folder(folder_id)
        except Exception:
            traceback.print_exc(file=stderr)
            print(f'{RED}{key = }\n{url = }{END}')
            return

        for file in data:
            size = file['Size']
            dl_link = GD_LINK.format(file["ID"])
            path = file['Path'].split('/')
            path[-1] = f'{path[-1]} (size-{size})'
            set_value(root, path, dl_link)
    else:
        file_id = RE_GD_FILEID.search(url).group(1 if 'id=' in url else 2)
        try:
            content = await gd_get_file(file_id)
        except Exception:
            traceback.print_exc(file=stderr)
            print(f'{RED}{key = }\n{url = }{END}')
            return

        if HAS_GDRIVE:
            try:
                filename = re.search(r'(?:^|\n)Name: ([^\n]*)', content).group(1)
                size = re.search(r'(?:^|\n)Size: (\d+)', content).group(1)
            except Exception:
                traceback.print_exc(file=stderr)
                print(f'{RED}{key = }\n{url = }{END}')
                return
        else:
            try:
                filename, size = re.search(
                    r'href\=\"\/open.*?>([^<]+)\<\/a\> \((\d+.)\)', content
                ).group(1, 2)
                size = parse_size(size)
            except Exception:
                traceback.print_exc(file=stderr)
                print(f'{RED}{content = }\n{key = }\n{url = }{END}')
                return

        dl_link = GD_LINK.format(file_id)
        filename = f'{unescape(filename)} (size-{size})'
        root[filename] = dl_link

    # print(json.dumps(root, indent=2))
    db[key]['gdrive'][url] = root


async def nextcloud(key: str, url: str, password=''):
    user = url.split('/')[-1]
    domain = url.split("/")[0]
    webdav = f'{domain}/nextcloud/public.php/webdav'
    auth = BasicAuth(user, password)
    att = 0
    while att < MAX_ATTEMPTS:
        try:
            async with session.request(method='PROPFIND',
                                       url=f'https://{webdav}', auth=auth,
                                       headers={'Depth': 'infinity'}) as r:
                xml = await r.text()
                if r.status in [200, 207]:
                    break
        except Exception:
            traceback.print_exc(file=stderr)
            print(f'{RED}{url}{END}')
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
        if not path or path.endswith('/'):
            continue  # hopefully the first item of this loop... :-)

        prop = e.getElementsByTagName('d:prop')[0]
        size = prop.getElementsByTagName('d:getcontentlength')
        size = int(size[0].firstChild.data)

        dl_link = f'https://{user}:{password}@{webdav}/{path}'
        path = path.split('/')
        path[-1] = unquote(f'{path[-1]} (size-{size})')
        set_value(root, path, dl_link)

    if not root and 'contenttype>video/' in xml:
        try:
            async with session.request(method='HEAD', url=f'https://{webdav}',
                                       auth=auth) as r:
                content = r.headers['content-disposition']
                size = r.headers['content-length']
        except Exception:
            traceback.print_exc(file=stderr)
            print(f'{RED}{key = }\n{url}{END}')
            return
        dl_link = f'https://{user}:{password}@{webdav}/'
        # size = re.search(r'd:getcontentlength>(\d+)<', xml).group(1)
        filename = re.search(r'filename=\"([^\"]*)', content).group(1)
        filename = f'{unquote(filename)} (size-{size})'
        root[filename] = dl_link

    # print(json.dumps(root, indent=2))
    db[key]['nextcloud'][url] = root


async def q_handler(queue: asyncio.Queue):
    global counter
    while True:
        k, url = await queue.get()

        if '/nextcloud/' in url:
            pw = '' if 'password' not in db[k] else db[k]['password']
            await nextcloud(k, url, pw)
        elif 'drive.google' in url:
            await google_drive(k, url)

        counter += 1
        pbar(counter, qsize)
        await random_sleep()
        queue.task_done()


def gen_only_files(db: dict):
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

    print(count(files), 'files')
    with open(FILES_DB, 'w') as fp:
        json.dump(files, fp)


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
        pbar(counter, qsize)
        tasks = []
        for _ in range(Q_SIZE):
            tasks += [asyncio.create_task(q_handler(queue))]
        await queue.join()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    print()
    with open(DB, 'w') as fp:
        json.dump(db, fp)

    gen_only_files(db)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
