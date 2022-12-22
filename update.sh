#!/usr/bin/env bash

set -xe

cd ~/.scripts/python/anitsu || exit 1

./get_posts.py -m 1
./get_files.py
./gen_anitsu_files.py
