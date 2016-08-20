from datetime import datetime, date, timedelta
from os import listdir, sep
from os.path import abspath, basename, expanduser, isfile, join
from random import choice, uniform
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
        self.perm_ours = db.picker_from_filters(config['games']['permission']['our_picker'])
        self.perm_yours = db.picker_from_filters(config['games']['permission']['your_picker'])

    def update(self):
        msg = None

        today = date.today()
        ndays = (today - self.last_checkin).days - 1
        if ndays > 0:
            if self.points < 0:
                new_pts = min(self.points + 2 * ndays, 0)
            else:
                new_pts = self.points + ndays
            if new_pts != self.points:
                msg = 'Added {} points for missing days'.format(new_pts - self.points)
                self.points = new_pts

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
        if self.points <= 0:
            return False
        if datetime.now() < self.ask_blocked_until:
            return False
        return True

    def put(self):
        data = {key: getattr(self, key)
                for key in ['points', 'last_mas', 'last_checkin', 'streak',
                            'perm_until', 'ask_blocked_until']}
        with open(self.local, 'w') as f:
            dump(data, f, default_flow_style=False)
        run(['rsync', '-av', self.local, self.remote])

    def mas(self):
        if self.points < 0:
            self.points += 1
            self.last_mas = date.today()
            return 'One point removed from your lead'
        elif self.points > 0:
            if self.perm_until >= datetime.now():
                self.points -= 1
                self.perm_until = datetime.now() - timedelta(hours=2)
                self.last_mas = date.today()
                return 'You have permission, one point removed from our lead'
            else:
                self.points += 1
                self.ask_blocked_until = datetime.now() + timedelta(hours=1)
                return 'Permission not given, one point added to our lead'
        else:
            return 'Undecided position, you should play'

    def picker(self):
        if self.points > 0:
            return self.pickers['plus']
        elif self.points < 0:
            return self.pickers['minus']
        return self.pickers['standard']

    def set_pts(self, pts):
        sign = -1 if pts < 0 else 1
        if sign * self.streak > 0:
            s = abs(self.streak)
            pts += sign * s * (s + 1) // 2
            self.streak += sign
        else:
            self.streak = sign
        self.points = pts


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

    def get(self):
        ret = run(['rsync', '-a', '--info=stats2', '--delete',
                   self.remote, Picture.root + sep], stdout=PIPE)
        self.update_session()
        return ret.stdout.decode()

    def put(self):
        self.session.commit()
        ret = run(['rsync', '-a', '--info=stats2', '--delete',
                   Picture.root + sep, self.remote], stdout=PIPE)
        self.update_session()
        return ret.stdout.decode()

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
