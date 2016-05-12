from os.path import abspath, expanduser, join
from random import choice

from sqlalchemy import create_engine, Boolean, Column, Integer, MetaData, String, Table
from sqlalchemy.orm import mapper, create_session


class Picture:

    @property
    def filename(self):
        return join(self.root, '{idx:0>8}.{ext}'.format(idx=self.id, ext=self.extension))


class DB:

    def __init__(self, config):
        columns = [Column('id', Integer, primary_key=True),
                   Column('extension', String, nullable=False)]
        for c in config['columns']:
            type_ = Integer if c.startswith('num_') else Boolean
            default = {Integer: 0, Boolean: False}[type_]
            columns.append(Column(c, type_, nullable=False, default=default))

        Picture.root = abspath(expanduser(config['location']))
        path = abspath(join(Picture.root, 'plib.db'))
        engine = create_engine('sqlite:///{}'.format(path))
        metadata = MetaData(bind=engine)
        table = Table('pictures', metadata, *columns)
        metadata.create_all()
        mapper(Picture, table)

        self.session = create_session(bind=engine, autocommit=False, autoflush=True)

    def query(self):
        return self.session.query(Picture)

    def random_pic(self):
        pics = list(self.query())
        pic = choice(pics)
        return pic
