from sys import exit
from yaml import load

from gui import run_gui
from db import DB


if __name__ == '__main__':
    with open('config.yaml', 'r') as f:
        config = load(f)
    db = DB(config['db'])
    exit(run_gui(db))
