#!/usr/bin/env python3
from time import sleep
from sys import argv, stdout
import re
PREVIEW_FIFO = '/tmp/anitsu.preview.fifo'
RE_EXT = re.compile(r'.*\.(mkv|avi|mp4|webm|ogg|mov|rmvb|mpg|mpeg)$')

with open(PREVIEW_FIFO, 'w') as fifo:
    fifo.write(f'{argv[1]}\n')

with open(PREVIEW_FIFO, 'r') as fifo:
    data = fifo.read()
    for i in [i.strip() for i in data.split('\n') if i]:
        if RE_EXT.match(i):
            stdout.write(f'\033[1;35m{i}\033[m\n')
        else:
            stdout.write(f'\033[1;34m{i}\033[m\n')
