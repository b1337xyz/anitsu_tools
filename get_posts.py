#!/usr/bin/env python3
from datetime import datetime
from aiohttp import ClientSession, BasicAuth
from html import unescape
import asyncio
import json
import os
import random
import re

# orderby = author, date, id, modified, relevance, slug, title, rand

USER = '' # anitsu login user and password
PASS = ''
HOME = os.getenv('HOME')
ROOT = os.path.realpath(os.path.dirname(__file__))
LAST_RUN = os.path.join(ROOT, '.last_run')
DB = os.path.join(HOME, '.cache/anitsu.json')
IMG_DIR = os.path.join(HOME, '.cache/anitsu_covers')
WP_URL =  'https://anitsu.moe/wp-json/wp/v2/posts?per_page=100&page={}&modified_after={}&_fields=id,date,modified,link,title,content'
RE_IMG  = re.compile(r'src=\"([^\"]*\.(?:png|jpe?g|webp|gif))')
RE_MAL  = re.compile(r'myanimelist\.net/\w*/(\d*)')
RE_ANI  = re.compile(r'anilist\.co/\w*/(\d*)')
RE_GDR  = re.compile(r'href=\"(https://drive\.google[^\"]*)')
RE_PASS = re.compile(r'Senha: <span[^>]*>(.*)</span')
MAX_ATTEMPTS = 3
Q_SIZE = 10
NOW = datetime.isoformat(datetime.now())


clean_text = lambda s: unescape(s).encode('ascii', 'ignore').decode().strip()


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
        post_id  = str(post['id'])
        modified = post['modified']
        content  = post['content']['rendered']
        title    = clean_text(post['title']['rendered'])

        if post_id not in db:
            print(f'[{modified}] {title}')
            db[post_id] = dict()
            db[post_id]['nextcloud'] = dict()

        if 'modified' in db[post_id]:
            mod = db[post_id]['modified']
            if modified != mod:
                print(f'[\033[1;31m{mod}\033[m > \033[1;32m{modified}\033[m] {title}')
                db[post_id]['nextcloud'] = dict()

        pw = RE_PASS.search(content)
        pw = '' if not pw else pw.group(1)

        if pw:
            print(f'\033[1;31mPassword: {pw}\033[m')

        db[post_id]['password']   = pw
        db[post_id]['title']      = title
        db[post_id]['url']        = post['link']
        db[post_id]['date']       = post['date']
        db[post_id]['modified']   = modified
        db[post_id]['is_release'] = '[em lançamento' in content.lower()
        db[post_id]['image']      = os.path.join(IMG_DIR, f'{post_id}.jpg')
        db[post_id]['image_url']  = regex(RE_IMG, content)
        db[post_id]['malid']      = regex(RE_MAL, content)
        db[post_id]['anilist']    = regex(RE_ANI, content)
        db[post_id]['gdrive']     = regex(RE_GDR, content)
        links = re.findall(r'//([^/]*/nextcloud/\w/[^\?\"]+)', content)
        for i in links:
            if i not in db[post_id]['nextcloud']:
                db[post_id]['nextcloud'][i] = dict()

        if not db[post_id]['nextcloud']:
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
                print(f'\033[1;31m{err}\033[m\n{url}')
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

    try:
        with open(LAST_RUN, 'r') as fp:
            last_run = fp.read()
    except FileNotFoundError:
        last_run = NOW

    open(LAST_RUN, 'w').write(NOW)

    auth = BasicAuth(USER, PASS)
    async with ClientSession(auth=auth) as session:
        print('requesting first page, please wait...')
        url = WP_URL.format(1, last_run)
        async with session.get(url) as r:
            total_pages = int(r.headers['x-wp-totalpages'])
            total_posts = int(r.headers['x-wp-total'])
            posts = await r.json()

        if not posts:
            return

        print(f'total pages: {total_pages}\ntotal posts: {total_posts}')
        await update_db(posts)
        queue = asyncio.Queue()
        for p in range(2, total_pages+1):
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
