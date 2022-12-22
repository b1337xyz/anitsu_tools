#!/usr/bin/env python3
from aiohttp import ClientSession, BasicAuth
from urllib.parse import unquote
from collections import defaultdict
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

    root = tree()
    file_count = 0
    for i in re.findall(r'/nextcloud/public.php/webdav/([^<]*)', xml):
        if i.endswith('/') or not i:
            continue

        dl_link = f'https://{user}:{password}@{webdav}/{i}'
        path = i.split('webdav')[-1].split('/')
        set_value(root, path, dl_link)
        file_count += 1

    if not root and 'contenttype>video/' in xml:
        try:
            async with session.request(method='HEAD', url=f'https://{webdav}', auth=auth) as r:
                content = r.headers['content-disposition']
                filename = re.search(r'filename=\"([^\"]*)', content).group(1)
        except Exception as err:
            print(f'\033[1;31m{err}\033[m\n{url}')
            return
        dl_link = f'https://{user}:{password}@{webdav}/'
        root[unquote(filename)] = dl_link
        file_count += 1

    print(db[k]['title'], f'{file_count} files')
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
