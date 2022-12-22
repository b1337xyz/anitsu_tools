#!/usr/bin/env python3
from time import sleep
from sys import argv
import re
FIFO = '/tmp/anitsu.fifo'
RE_EXT = re.compile(r'.*\.(mkv|avi|mp4|webm|ogg|mov|rmvb|mpg|mpeg)$')

with open(FIFO, 'w') as fifo:
    fifo.write(f'{argv[1]}\n')

with open(FIFO, 'r') as fifo:
    data = fifo.read()
    for i in [i.strip() for i in data.split('\n') if i]:
        if RE_EXT.match(i):
            print(f'\033[1;35m{i}\033[m')
        else:
            print(f'\033[1;34m{i}\033[m')
