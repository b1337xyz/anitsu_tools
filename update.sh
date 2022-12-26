#!/usr/bin/env bash

set -xe

cd ~/.scripts/python/anitsu || exit 1

./get_posts.py
./get_files.py
./gen_anitsu_files.py
./download_images.py
