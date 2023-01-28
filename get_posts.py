#!/usr/bin/env python3
from utils import *
from datetime import datetime
from aiohttp import ClientSession, BasicAuth
from html import unescape
from getpass import getpass
import asyncio
import json
import random

CONFIG = os.path.join(ROOT, '.config')
LAST_RUN = os.path.join(ROOT, '.last_run')
WP_URL = 'https://anitsu.moe/wp-json/wp/v2/posts?per_page=100&page={}\
&modified_after={}&_fields=id,date,modified,link,title,content'
RE_IMG = re.compile(r'src=\"([^\"]*\.(?:png|jpe?g|webp|gif))')
RE_MAL = re.compile(r'myanimelist\.net/\w*/(\d*)')
RE_ANI = re.compile(r'anilist\.co/\w*/(\d*)')
RE_NXC = re.compile(r'//([^/]*/nextcloud/\w/[^\?\"]+)')
RE_GDR = re.compile(r'href=\"(https://drive\.google[^\"]*)')
RE_PASS = re.compile(r'Senha: <span[^>]*>(.*)</span')
MAX_ATTEMPTS = 3
Q_SIZE = 10


def get_auth():
    try:
        with open(CONFIG, 'r') as fp:
            config = json.load(fp)
    except FileNotFoundError:
        config = {
            'user': input('User: ').strip(),
            'passwd': getpass()
        }
        with open(CONFIG, 'w') as fp:
            json.dump(config, fp, indent=4)
    return config['user'], config['passwd']


def clean_text(s):
    return unescape(s).encode('ascii', 'ignore').decode().strip()


def regex(expr, text):
    try:
        return expr.search(text).group(1)
    except AttributeError:
        return ''


async def random_sleep():
    await asyncio.sleep(random.random() * .5)


async def update_db(posts):
    global db
    for post in posts:
        post_id = str(post['id'])
        modified = post['modified']
        content = post['content']['rendered']
        title = clean_text(post['title']['rendered'])

        if post_id not in db:
            print(f'[{GRN}{modified}{END}] {title}')
            db[post_id] = dict()
            db[post_id]['nextcloud'] = dict()
            db[post_id]['gdrive'] = dict()

        if 'modified' in db[post_id]:
            mod = db[post_id]['modified']
            if modified != mod:
                print(f'[{RED}{mod}{END} > {GRN}{modified}{END}] {title}')
                db[post_id]['nextcloud'] = dict()
                db[post_id]['gdrive'] = dict()

        pw = RE_PASS.search(content)
        pw = '' if not pw else pw.group(1)
        if pw:
            print(f'{RED}Password: {pw}{END}')

        db[post_id]['password'] = pw
        db[post_id]['title'] = title
        db[post_id]['url'] = post['link']
        db[post_id]['date'] = post['date']
        db[post_id]['modified'] = modified
        db[post_id]['is_release'] = '[em lançamento' in content.lower()
        db[post_id]['image'] = os.path.join(IMG_DIR, f'{post_id}.jpg')
        db[post_id]['image_url'] = regex(RE_IMG, content)
        db[post_id]['malid'] = regex(RE_MAL, content)
        db[post_id]['anilist'] = regex(RE_ANI, content)

        nextcloud_links = RE_NXC.findall(content)
        has_files = bool(nextcloud_links)
        for i in nextcloud_links:
            if i not in db[post_id]['nextcloud']:
                db[post_id]['nextcloud'][i] = dict()

        gdrive_links = RE_GDR.findall(content)
        has_files = bool(gdrive_links) if not has_files else has_files
        for i in gdrive_links:
            if i not in db[post_id]['gdrive']:
                db[post_id]['gdrive'][i] = dict()

        if not has_files:
            # https://anitsu.moe/wp-json/wp/v2/posts?include={post_id}
            print(f'nothing found, post {post_id} deleted')
            del db[post_id]


async def get_posts(queue):
    while True:
        page = await queue.get()
        url = WP_URL.format(page, last_run)
        att = 0
        while att < MAX_ATTEMPTS:
            try:
                async with session.get(url) as r:
                    if r.status == 200:
                        posts = await r.json()
                        break
            except Exception as err:
                print(f'{RED}{err}{END}\n{url}')
            att += 1
            await random_sleep()
        await update_db(posts)
        await random_sleep()
        queue.task_done()


async def main():
    global session, db, last_run
    try:
        with open(DB, 'r') as fp:
            db = json.load(fp)
    except FileNotFoundError:
        db = dict()

    if os.path.exists(LAST_RUN) and db:
        with open(LAST_RUN, 'r') as fp:
            last_run = fp.read()
    else:
        last_run = '2000-01-01T00:00:00'

    now = datetime.isoformat(datetime.now())
    open(LAST_RUN, 'w').write(now)

    user, passwd = get_auth()
    auth = BasicAuth(user, passwd)
    async with ClientSession(auth=auth) as session:
        print('requesting first page, please wait...')
        url = WP_URL.format(1, last_run)
        async with session.get(url, timeout=30) as r:
            if r.status != 200:
                print(f'{r.status}, check your user and password')
                __import__('sys').exit(1)

            total_pages = int(r.headers['x-wp-totalpages'])
            total_posts = int(r.headers['x-wp-total'])
            posts = await r.json()

        if not posts:
            return

        print(f'total pages: {total_pages}\ntotal posts: {total_posts}')
        await update_db(posts)
        queue = asyncio.Queue()
        for p in range(2, total_pages + 1):
            queue.put_nowait(p)

        tasks = []
        for _ in range(Q_SIZE):
            tasks += [asyncio.create_task(get_posts(queue))]
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
