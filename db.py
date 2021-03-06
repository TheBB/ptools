from datetime import datetime, date, timedelta
from os import listdir, sep
from os.path import abspath, basename, expanduser, isfile, join
from random import random, choice, uniform
from subprocess import run, PIPE
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

    def get_all(self):
        return self.db.query()


class UnionPicker:

    def __init__(self, name='Union'):
        self.pickers = []
        self.name = name

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
            self.__dict__.update(load(f))

        self.pickers = {name: db.picker_from_filters(filters, name)
                        for name, filters in config['pickers'].items()}
        self.bestof_picker = db.picker_from_filters(config['games']['bestof']['picker'])
        self.bestof_trigger = lambda pic: eval(config['games']['bestof']['trigger'], None, pic.__dict__)
        self.bestof_value = lambda pic: eval(config['games']['bestof']['value'], None, pic.__dict__)

        self.perm_value = (
            lambda pic: eval(config['games']['permission']['value'], None, pic.__dict__)
        )
        self.perm_num = int(config['games']['permission']['num'])
        self.perm_prob = float(config['games']['permission']['prob'])
        self.perm_break = int(config['games']['permission']['break'])
        self.perm_m_until, self.perm_m_before = config['games']['permission']['margins']
        self.perm_ours = db.picker_from_filters(config['games']['permission']['our_picker'])
        self.perm_yours = db.picker_from_filters(config['games']['permission']['your_picker'])

    @property
    def pts(self):
        return self.points

    @property
    def signed_pts(self):
        return -self.pts if self.leader == 'you' else self.pts

    @property
    def we_leading(self):
        return self.leader == 'us'

    @property
    def you_leading(self):
        return self.leader == 'you'

    def update_points(self, new=None, delta=None, sdelta=None):
        if new is not None:
            self.points = new
            return
        if delta is not None:
            self.points += delta
            self.points = max(self.points, 0)
            return
        sdelta = -sdelta if self.you_leading else sdelta
        self.points += sdelta
        self.points = max(self.points, 0)

    def update_points_leader(self, leader, points):
        assert leader in {'us', 'you'}
        if self.leader == leader:
            points += self.streak * (self.streak + 1) / 2
            self.streak += 1
        else:
            self.streak = 0
        self.leader = leader
        self.points = points
        self.next_mas_add = 0

    def update(self):
        msg = None

        today = date.today()
        ndays = (today - self.last_checkin).days - 1
        if ndays > 0:
            if self.you_leading:
                self.update_points(sdelta=2*ndays)
            else:
                self.update_points(sdelta=ndays)
            if new_pts != self.points:
                msg = 'Added up to {} points for missing days'.format(ndays)

        self.last_checkin = today
        return msg

    def give_permission(self, permission, reduced=0):
        if permission:
            self.perm_until = datetime.now() + timedelta(minutes=60-reduced)

    def block_until(self, delta=None):
        if delta is None:
            delta = self.perm_break
        self.ask_blocked_until = datetime.now() + timedelta(minutes=delta)

    def can_ask_permission(self):
        return self.we_leading and datetime.now() > self.ask_blocked_until

    def put(self):
        data = {key: getattr(self, key)
                for key in ['points', 'leader', 'last_mas', 'last_checkin', 'streak',
                            'next_mas_add', 'perm_until', 'ask_blocked_until']}
        with open(self.local, 'w') as f:
            dump(data, f, default_flow_style=False)
        run(['rsync', '-av', self.local, self.remote])

    def mas(self, skip=False):
        chg = 0

        if self.you_leading and self.points > 0:
            pos = 'You are leading'
            chg = -2 if skip else -1
        elif self.we_leading:
            if self.perm_until >= datetime.now():
                pos = 'You have permission'
                chg = -1 if skip else self.next_mas_add
                if not skip:
                    self.next_mas_add += 1
                self.perm_until = datetime.now() - timedelta(hours=2)
                self.last_mas = date.today()
            elif not skip:
                pos = "You don't have permission"
                chg = 2 * (self.next_mas_add + 1)
                self.ask_blocked_until = datetime.now() + timedelta(hours=1)
            else:
                return "That doesn't make sense"

        self.update_points(delta=chg)
        return '{}. Delta {:+}. New {}.'.format(pos, chg, self.points)

    def picker(self):
        return self.pickers['plus'] if self.we_leading else self.pickers['minus']


class DB:

    def __init__(self, config):
        columns = [Column('id', Integer, primary_key=True),
                   Column('extension', String, nullable=False),
                   Column('delt', Boolean, nullable=False, default=False)]
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
        self.custom_columns = columns[3:]

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
            self.pickers.append(self.picker_from_filters(filters, name))

        self.status = Status(self, config['status'])
        self.update_session()

    def update_session(self):
        if hasattr(self, 'session'):
            self.session.close()
        self.session = create_session(bind=self.engine, autocommit=False, autoflush=True)

    def query(self):
        return self.session.query(Picture)

    def picker_from_filters(self, filters=[], name='&All'):
        if not filters:
            return self.picker(name)
        elif isinstance(filters[0], list):
            picker = UnionPicker(name)
            for f in filters:
                freq = 1.0
                if f and isinstance(f[0], float):
                    freq = f[0]
                    f = f[1:]
                picker.add(self.picker_from_filters(f), freq)
            return picker

        filters = [eval(s, None, Picture.__dict__) for s in filters]
        return self.picker(name, *filters)

    def picker(self, name='&All', *filters):
        return ListPicker(name, self, *filters)

    def get_remote(self):
        ret = run(['rsync', '-a', '--info=stats2', '--delete',
                   self.remote, Picture.root + sep], stdout=PIPE)
        self.update_session()
        return ret.stdout.decode()

    def put_remote(self):
        self.session.commit()
        ret = run(['rsync', '-a', '--info=stats2', '--delete',
                   Picture.root + sep, self.remote], stdout=PIPE)
        self.update_session()
        return ret.stdout.decode()

    def mark_delete(self, pic):
        if pic.id:
            pic.delt = True
            self.session.commit()

    def get_delete_ids(self):
        return {p.id for p in self.query().filter(Picture.delt == True)}

    def delete(self, pic):
        run(['rm', pic.filename])
        self.session.delete(pic)

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

        return (len(delete_ids), len(move_files),
                [join(self.staging, fn) for fn in listdir(self.staging)])
