#!/usr/bin/env python3
from utils import *
from aiohttp import ClientSession
import aiofiles
import asyncio
import json
import subprocess as sp

Q_SIZE = 15
counter = 0


async def download(queue):
    global counter
    while True:
        url, image_path = await queue.get()
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(image_path, mode='wb')
                await f.write(await resp.read())
                await f.close()
            else:
                print(f'error: {resp.status}, {url}')

        if os.path.exists(image_path):
            try:
                sp.run([
                    'convert', f'{image_path}[0]',
                    '-resize', '424x600>', image_path
                ])
            except Exception:
                os.remove(image_path)

        counter += 1
        pbar(counter, qsize)
        queue.task_done()


async def main():
    global session, qsize

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
        if qsize == 0:
            return
        print(f'{qsize} images to download, please wait...')
        pbar(counter, qsize)
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
    finally:
        print()
