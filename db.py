from os.path import abspath, expanduser, join
from random import choice, uniform

from sqlalchemy import create_engine, Boolean, Column, Integer, MetaData, String, Table
from sqlalchemy.orm import mapper, create_session
from sqlalchemy.sql import func

from utils import replace_all


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
            if r <= 0.0:
                break
            r -= f

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
            filters = [eval(replace_all(s, replacements)) for s in p['filters']]
            self.pickers.append(self.picker(p['name'], *filters))

    def query(self):
        return self.session.query(Picture)

    def picker(self, name='All', *filters):
        return ListPicker(name, self.query().filter(*filters))

    def random_pic(self):
        pics = list(self.query())
        pic = choice(pics)
        return pic

