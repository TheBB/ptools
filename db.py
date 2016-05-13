from os import listdir
from os.path import abspath, basename, expanduser, isfile, join
from random import choice, uniform
from subprocess import run

from sqlalchemy import create_engine, Boolean, Column, Integer, MetaData, String, Table
from sqlalchemy.orm import mapper, create_session
from sqlalchemy.sql import func


class Picture:

    @property
    def filename(self):
        return join(self.root, '{idx:0>8}.{ext}'.format(idx=self.id, ext=self.extension))


class ListPicker:

    def __init__(self, name, query):
        self.query = query
        self.name = name

    def get(self):
        return self.query.order_by(func.random()).first()


class UnionPicker:

    def __init__(self):
        self.pickers = []
        self.name = 'Union'

    def add(self, picker, frequency=1.0):
        self.pickers.append((picker, float(frequency)))

    def get(self):
        max = sum(f for _, f in self.pickers)
        r = uniform(0.0, max)

        for p, f in self.pickers:
            r -= f
            if r <= 0.0:
                break

        return p.get()


class DB:

    def __init__(self, config):
        columns = [Column('id', Integer, primary_key=True),
                   Column('extension', String, nullable=False)]
        replacements = []
        for c in config['columns']:
            type_ = Integer if c.startswith('num_') else Boolean
            default = {Integer: 0, Boolean: False}[type_]
            columns.append(Column(c, type_, nullable=False, default=default))
            replacements.append((c, 'Picture.{}'.format(c)))

        self.staging = abspath(expanduser(config['staging']))

        Picture.root = abspath(expanduser(config['location']))
        path = abspath(join(Picture.root, 'plib.db'))
        engine = create_engine('sqlite:///{}'.format(path))
        metadata = MetaData(bind=engine)
        table = Table('pictures', metadata, *columns)
        metadata.create_all()
        mapper(Picture, table)

        self.session = create_session(bind=engine, autocommit=False, autoflush=True)

        self.pickers = [self.picker()]
        for p in config['pickers']:
            name, filters = next(iter(p.items()))
            filters = [eval(s, None, Picture.__dict__) for s in filters]
            self.pickers.append(self.picker(name, *filters))

    def query(self):
        return self.session.query(Picture)

    def picker(self, name='All', *filters):
        return ListPicker(name, self.query().filter(*filters))

    def synchronize(self):
        existing_db = {p.filename for p in self.query()}
        existing_hd = {join(Picture.root, fn) for fn in listdir(Picture.root) if fn != 'plib.db'}
        existing_hd = {fn for fn in existing_hd if isfile(fn)}

        delete_ids = {int(basename(f).split('.')[-2]) for f in existing_db - existing_hd}
        if delete_ids:
            self.query().filter(Picture.id.in_(delete_ids)).delete(synchronize_session='fetch')

        move_files = existing_hd - existing_db
        for fn in move_files:
            run(['mv', fn, join(self.staging, basename(fn))])

        return [join(self.staging, fn) for fn in listdir(self.staging)]
