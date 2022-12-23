#!/usr/bin/env python3
from aiohttp import ClientSession
import aiofiles
import asyncio
import json
import os
import subprocess as sp

HOME = os.getenv('HOME')
DB = os.path.join(HOME, '.cache/anitsu.json')
Q_SIZE = 15


async def download(queue):
    while True:
        url, image_path = await queue.get()
        print(image_path)
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(image_path, mode='wb')
                await f.write(await resp.read())
                await f.close()
            else:
                print(f'error {resp.status}')

        if os.path.exists(image_path):
            try:
                p = sp.run(['file', '-bi', image_path], stdout=sp.PIPE)
                out = p.stdout.decode().strip()
                if out.startswith('image/gif'):
                    print(f'converting {out} to jpeg...')
                    sp.run(['convert', f'{image_path}[0]', image_path])
                elif not out.startswith('image/jpeg'):
                    print(f'converting {out} to jpeg...')
                    sp.run(['convert', image_path, image_path])
            except:
                os.remove(image_path)
                print(f'convert failed: "{image_path}" removed')

        queue.task_done()


async def main():
    global session

    with open(DB, 'r') as fp:
        db = json.load(fp)

    async with ClientSession() as session:
        queue = asyncio.Queue()
        for k in db:
            image_path = db[k]['image']
            if not os.path.exists(image_path):
                url = db[k]['image_url']
                queue.put_nowait((url, image_path))
            qsize = queue.qsize()
            tasks = []
            for _ in range(Q_SIZE):
                tasks += [asyncio.create_task(download(queue))]
            await queue.join()
            for task in tasks:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
