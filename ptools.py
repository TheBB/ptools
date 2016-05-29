from sys import exit
from yaml import load
import atexit

from gui import run_gui
from db import DB


if __name__ == '__main__':
    with open('config.yaml', 'r') as f:
        config = load(f)
    db = DB(config['db'])
    msg = db.status.update()
    atexit.register(db.status.put)
    exit(run_gui(db, msg))
