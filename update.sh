#!/usr/bin/env bash

set -xe

root=$(realpath "$0") root=${root%/*}
cd "$root" || exit 1

mkdir -vp ~/.cache/anitsu_covers

./get_posts.py
./get_files.py
./gen_anitsu_files.py
./download_images.py
