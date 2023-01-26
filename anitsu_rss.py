#!/usr/bin/env python3
from time import sleep
import os
import re
import requests

URL = 'https://anitsu.moe/feed/'
HOME = os.getenv('HOME')
FILE = os.path.join(HOME, '.cache/anitsu.rss')
COOKIE_FILE = os.path.join(HOME, '.config/anitsu.cookie')
INTERVAL = 15 * 60

with open(COOKIE_FILE, 'r') as fp:
    cookie = fp.read()

wp = re.match(r'.*(wordpress_logged_in[^=]*).([^;]*)', cookie)
s = requests.Session()
s.cookies.set(
    wp.group(1),
    wp.group(2).strip(),
    domain=URL.split('/')[2]
)

error_msg = '''<rss version="2.0">
<channel>
    <title>Anitsu - 404</title>
    <item>
        <title>Error</title>
        <description>{}</description>
    </item>
</channel>
</rss>'''

try:
    while True:
        try:
            r = s.get(URL)
            rss = r.text
        except Exception as err:
            rss = error_msg.format(err)

        assert '<rss version' in rss
        with open(FILE, 'w') as fp:
            fp.write(rss)

        sleep(INTERVAL)
except KeyboardInterrupt:
    __import__('sys').exit(130)
