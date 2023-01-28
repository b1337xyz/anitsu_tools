#!/usr/bin/env python3
import os

ROOT = os.path.realpath(os.path.dirname(__file__))
HOME = os.getenv('HOME')
DL_DIR = os.path.join(HOME, 'Downloads')
DB_PATH = os.path.join(ROOT, 'db')
DB = os.path.join(DB_PATH, 'anitsu.json')
FILES_DB = os.path.join(DB_PATH, 'anitsu_files.json')
IMG_DIR = os.path.join(ROOT, 'images')
RED = '\033[1;31m'
GRN = '\033[1;32m'
END = '\033[m'

for dir in [DB_PATH, IMG_DIR]:
    if not os.path.exists(dir):
        os.mkdir(dir)
