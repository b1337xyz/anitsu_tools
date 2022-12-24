#!/usr/bin/env python3
from aiohttp import ClientSession, BasicAuth
from urllib.parse import unquote
from collections import defaultdict
from xml.dom import minidom
import random
import asyncio
import json
import re
import os

HOME = os.getenv('HOME')
DB = os.path.join(HOME, '.cache/anitsu.json')
Q_SIZE = 20
MAX_ATTEMPTS = 3


async def random_sleep():
    await asyncio.sleep(random.random() * .5)


def tree():
    return defaultdict(tree)


def set_value(root, path, value):
    for d in path[:-1]:
        root = root[unquote(d)]
    root[unquote(path[-1])] = value


def get_psize(size):
    units = ["KB", "MB", "GB", "TB", "PB"]
    psize = f"{size} B"
    for i in units:
        if size < 1000:
            break
        size /= 1000
        psize = f"{size:.2f} {i}"
    return psize


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
        prop = e.getElementsByTagName('d:prop')[0]
        fsize = prop.getElementsByTagName('d:getcontentlength')
        dsize = prop.getElementsByTagName('d:quota-used-bytes')

        if fsize: # is a file
            size = fsize[0].firstChild.data
        elif dsize:
            size = dsize[0].firstChild.data

        size = get_psize(int(size))

        if not path:
            # hopefully the first item of this loop... :-)
            total = size
            continue

        if path.endswith('/'):
            continue

        dl_link = f'https://{user}:{password}@{webdav}/{path}'
        path = path.split('/')
        path[-1] = f'{path[-1]} (size-{size}) (total-{total})'

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
        size = get_psize(int(size))
        filename = re.search(r'filename=\"([^\"]*)', content).group(1)
        filename = unquote(filename)
        root[f'{filename} (size-{size}) (total-{size})'] = dl_link

    db[k]['nextcloud'][url] = root


async def q_handler(queue: asyncio.Queue):
    while True:
        k, url = await queue.get()
        pw = ''
        if 'password' in db[k]:
            pw = db[k]['password']
        await nextcloud(k, url, pw)
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


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
