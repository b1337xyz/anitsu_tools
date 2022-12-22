#!/usr/bin/env python3
from urllib.parse import unquote
import os

FIFO = os.getenv('QUTE_FIFO')
URL = os.getenv('QUTE_URL')
URL = URL.split('=')[-1]
URL = unquote(URL)
with open(FIFO, 'w') as fp:
    fp.write('open {}'.format(URL))
