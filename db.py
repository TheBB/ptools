from os import listdir, sep
from os.path import abspath, basename, expanduser, isfile, join
from random import choice, uniform
from subprocess import run
from yaml import dump, load

from sqlalchemy import create_engine, Boolean, Column, Integer, MetaData, String, Table
from sqlalchemy.orm import mapper, create_session
from sqlalchemy.sql import func


class Picture:

    @property
    def filename(self):
        return join(self.root, '{idx:0>8}.{ext}'.format(idx=self.id, ext=self.extension))


class ListPicker:

    def __init__(self, name, db, *filters):
        self.filters = filters
        self.db = db
        self.name = name

    def get(self):
        return self.db.query().filter(*self.filters).order_by(func.random()).first()


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


class Status:

    def __init__(self, db, config):
        self.local = abspath(expanduser(config['local']))
        self.remote = config['remote']

        run(['rsync', '-av', self.remote, self.local])
        with open(self.local, 'r') as f:
            self.data = load(f)

        self.pickers = {name: db.picker_from_filters(name, filters)
                        for name, filters in config['pickers'].items()}

    def put(self):
        with open(self.local, 'w') as f:
            dump(self.data, f, default_flow_style=False)
        run(['rsync', '-av', self.local, self.remote])

    def picker(self):
        if self.data['points'] > 0:
            return self.pickers['plus']
        elif self.data['points'] < 0:
            return self.pickers['minus']
        return self.pickers['standard']


class DB:

    def __init__(self, config):
        columns = [Column('id', Integer, primary_key=True),
                   Column('extension', String, nullable=False)]
        for c in config['columns']:
            if isinstance(c, str):
                type_ = Integer if c.startswith('num_') else Boolean
                name = c.replace('_', ' ').title()
                key = c
            else:
                type_ = {'int': Integer, 'bool': Boolean}[c['type']]
                name = c['title']
                key = c['key']
            default = {Integer: 0, Boolean: False}[type_]
            col = Column(key, type_=type_, nullable=False, default=default)
            col.title = name
            columns.append(col)
        self.custom_columns = columns[2:]

        self.staging = abspath(expanduser(config['pics']['staging']))
        self.remote = config['pics']['remote']
        Picture.root = abspath(expanduser(config['pics']['local']))

        path = abspath(join(Picture.root, 'plib.db'))
        self.engine = create_engine('sqlite:///{}'.format(path))
        metadata = MetaData(bind=self.engine)
        table = Table('pictures', metadata, *columns)
        metadata.create_all()
        mapper(Picture, table)

        self.pickers = [self.picker()]
        for p in config['pickers']:
            name, filters = next(iter(p.items()))
            self.pickers.append(self.picker_from_filters(name, filters))

        self.status = Status(self, config['status'])
        self.update_session()

    def update_session(self):
        if hasattr(self, 'session'):
            self.session.close()
        self.session = create_session(bind=self.engine, autocommit=False, autoflush=True)

    def query(self):
        return self.session.query(Picture)

    def picker_from_filters(self, name='All', filters=[]):
        filters = [eval(s, None, Picture.__dict__) for s in filters]
        return self.picker(name, *filters)

    def picker(self, name='All', *filters):
        return ListPicker(name, self, *filters)

    def get(self):
        run(['rsync', '-av', '--delete', self.remote, Picture.root + sep])
        self.update_session()

    def put(self):
        run(['rsync', '-av', '--delete', Picture.root + sep, self.remote])

    def sync_local(self):
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
