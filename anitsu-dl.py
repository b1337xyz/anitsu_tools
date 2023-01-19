#!/usr/bin/env python3
from optparse import OptionParser
from urllib.parse import unquote, quote
from tempfile import mktemp
import subprocess as sp
import requests
import re
import os
import sys

HOME = os.getenv('HOME')
DL_DIR = os.path.join(HOME, 'Downloads')
WEBDAV = "cloud.anitsu.moe/nextcloud/public.php/webdav"
RE_USER = re.compile(r'/nextcloud/\w/([^\?/]*)')

usage = 'Usage: %prog [options] <URL>'
parser = OptionParser(usage=usage)
parser.add_option('-p', '--password', type='string', default='')
parser.add_option('-d', '--dir', type='string', default=DL_DIR)
opts, args = parser.parse_args()
if not os.path.exists(opts.dir) or not args:
    parser.print_help()
    sys.exit(1)

for url in args:
    user = RE_USER.search(url).group(1)
    if '?path=' in url:
        path = unquote(re.search(r'\?path=([^&]*)', url).group(1))
        path = quote(path)
        webdav = f'https://{WEBDAV}/{path}'
    else:
        webdav = f'https://{WEBDAV}'

    r = requests.request(
        method='PROPFIND', url=webdav, auth=(user, opts.password),
        headers={'Depth': 'infinity'}
    )
    files = re.findall(r'public.php/webdav/([^<]*)', r.text)
    print(f'{len(files)} files found')

    tmpfile = mktemp()
    try:
        with open(tmpfile, 'w') as fp:
            for i in files:
                url = f'https://{user}:{opts.password}@{WEBDAV}/{i}'
                fp.write(url + '\n')

        p = sp.run([
            'aria2c', '-j', '2',
            '--dir', opts.dir, f'--input-file={tmpfile}'
        ])
    except KeyboardInterrupt:
        break
    finally:
        os.remove(tmpfile)
