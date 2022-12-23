#!/usr/bin/env python3
from time import sleep
from sys import argv, stdout
import re

FIFO = '/tmp/anitsu.fifo'

with open(FIFO, 'w') as fifo:
    for i in argv[1:]:
        fifo.write(f'{i}\n')

with open(FIFO, 'r') as fifo:
    data = fifo.read()
    for i in [i.strip() for i in data.split('\n') if i]:
        stdout.write(f'{i}\n')
