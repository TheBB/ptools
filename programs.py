from datetime import datetime, date, timedelta
from itertools import groupby
from os.path import join
from random import random, choice
from string import ascii_lowercase
from subprocess import run
import re
import numpy as np

from PyQt5.QtCore import Qt

from db import Picture, UnionPicker


class AbstractProgram:

    def key(self, main, event):
        pass

    def make_current(self, main, *args, **kwargs):
        pass


class ShowProgram(AbstractProgram):

    def __init__(self, main):
        self.picker = None
        main.register(self)
        self.make_current(main)

    def pic(self, main):
        picker = self.picker or main.db.status.picker()
        main.show_image(picker.get())

    def make_current(self, main, *args, **kwargs):
        self.pic(main)

    def key(self, main, event):
        if event.key() == Qt.Key_P:
            self.picker = main.get_picker() or self.picker
            self.pic(main)
        elif event.key() == Qt.Key_S:
            SyncProgram(main)
        elif event.key() == Qt.Key_T:
            StatusProgram(main)
        elif event.key() == Qt.Key_M:
            msg = main.db.status.mas()
            main.show_message(msg)
        elif event.key() == Qt.Key_R:
            if main.db.status.can_ask_permission():
                main.db.status.block_until(main.db.status.permission_break)
                PermissionProgram(main)
            else:
                main.show_message("Can't ask permission")
        elif event.key() == Qt.Key_G:
            if main.db.status.points != 0:
                StatusProgram(main)
            else:
                BestOfGame(main)
        else:
            self.pic(main)


class MessageProgram(AbstractProgram):

    def __init__(self, main, text):
        self.text = text
        main.register(self)

    def key(self, main, event):
        main.show_message(self.text)
        main.unregister()


class SyncProgram(AbstractProgram):

    def __init__(self, main):
        ret = main.db.get()
        ndel, nmov, self.staged = main.db.sync_local()

        self.data = {
            'new_loc': int(re.search(r'Number of created files: (?P<n>\d+)', ret).group('n')),
            'del_loc': int(re.search(r'Number of deleted files: (?P<n>\d+)', ret).group('n')),
            'del_inc': ndel,
            'mov_inc': nmov,
        }

        self.moves = {}
        main.register(self)
        self.next(main)

    def next(self, main):
        if self.staged:
            fn = self.staged[-1]
            main.show_image(self.staged[-1])
        else:
            main.db.session.add_all(self.moves.values())
            main.db.session.commit()

            for fn, pic in self.moves.items():
                run(['mv', fn, pic.filename])

            ret = main.db.put()
            self.data['new_rem'] = int(re.search(r'Number of created files: (?P<n>\d+)', ret).group('n'))
            self.data['del_rem'] = int(re.search(r'Number of deleted files: (?P<n>\d+)', ret).group('n'))
            main.show_message("""New from remote: {new_loc}<br>
                                 Deleted remotely: {del_loc}<br>
                                 Deleted from DB: {del_inc}<br>
                                 Re-staged: {mov_inc}<br>
                                 New on remote: {new_rem}<br>
                                 Deleted remotely: {del_rem}""".format(**self.data),
                              align='left')

            main.unregister()

    def key(self, main, event):
        flags = main.get_flags()
        if flags:
            fn = self.staged.pop()
            extension = fn.split('.')[-1].lower()
            if extension == 'jpeg':
                extension = 'jpg'

            pic = Picture()
            pic.extension = extension
            for k, v in flags.items():
                setattr(pic, k, v)

            self.moves[fn] = pic
            self.next(main)


class BestOfGame(ShowProgram):

    def __init__(self, main):
        self.picker = main.db.status.bestof_picker

        self.pts = {True: [0, 0, 0], False: [0, 0, 0]}
        self.max_pts = [5, 5, 10]
        self.current = choice([True, False])
        self.prev_winner = None
        self.speed = 0.7
        self.bias = 0.0
        self.done = False

        main.show_message('Best of: ' + ', '.join(str(s) for s in self.max_pts))

        main.register(self)
        self.next(main)

    def add_pts(self, winner, npts):
        l_pts = self.pts[not winner]
        w_pts = self.pts[winner]
        while npts > 0 and w_pts[-1] < self.max_pts[-1]:
            i = 0
            w_pts[i] += 1
            while w_pts[i] == self.max_pts[i]:
                if i == len(self.max_pts) - 1:
                    break
                w_pts[i+1] += 1
                w_pts[i] = l_pts[i] = 0
                i += 1
            npts -= 1

    def next(self, main):
        if self.done:
            main.unregister()
            return

        p = lambda b: max(min((1.020**b) / (1.020**b + 1), 0.93), 0.07)
        conv = lambda p: self.speed * p
        threshold = conv(p(self.bias) if self.current else 1 - p(self.bias))
        win = random() <= threshold
        pic = self.picker.get()
        while main.db.status.bestof_trigger(pic) != win:
            pic = self.picker.get()
        main.show_image(pic)

        if not win:
            self.current = not self.current
            return

        npts = main.db.status.bestof_value(pic)
        self.add_pts(self.current, npts)
        sign = 2 * int(self.current) - 1

        if self.prev_winner != self.current:
            self.bias = 0.0
        else:
            self.bias += (2 * int(self.current) - 1) * min(npts, 15)

        if self.pts[self.current][-1] == self.max_pts[-1]:
            winner = 'We' if self.current else 'You'
            total = self.max_pts[-1] - self.pts[not self.current][-1]
            msg = '{} win with {}'.format(winner, total)
            MessageProgram(main, msg)
            self.done = True
            main.db.status.set_pts(sign * total)
            return

        msg = ['{} points for {}'.format(npts, 'us' if self.current else 'you')]
        for a, b in zip(self.pts[True], self.pts[False]):
            msg.append('{} – {}'.format(a, b))

        p_t, p_f = conv(p(self.bias)), conv(1 - p(self.bias))
        denom = p_t + p_f - p_t * p_f
        if self.current:
            p_t /= denom
        else:
            p_t = 1 - p_f / denom
        p_f = 1 - p_t

        msg.append('{:.2f}% – {:.2f}%'.format(p_t*100, p_f*100))
        MessageProgram(main, msg)

        self.prev_winner = self.current

    def make_current(self, main, *args, **kwargs):
        self.next(main)

    def key(self, main, event):
        self.next(main)


class StatusProgram(AbstractProgram):

    def __init__(self, main):
        main.register(self)
        pts = main.db.status.points
        if pts == 0:
            main.show_message('Undecided')
        else:
            leader = 'our' if pts > 0 else 'your'
            msg = ['{} points in {} favour'.format(abs(pts), leader)]
            if main.db.status.points > 0:
                if main.db.status.permission_until > datetime.now():
                    diff = main.db.status.permission_until - datetime.now()
                    msg.append('Permission for {} minutes'.format(diff.seconds//60))
                else:
                    if main.db.status.ask_blocked_until > datetime.now():
                        diff = main.db.status.ask_blocked_until - datetime.now()
                        msg.append('Can ask permission in {} minutes'.format(diff.seconds//60 + 1))
                    else:
                        msg.append('Can ask permission')
            main.show_message(msg)

    def key(self, main, event):
        main.unregister()


class PermissionProgram(AbstractProgram):

    def __init__(self, main):
        self.picker = main.db.picker()

        num = sorted([main.db.status.permission_value(p) for p in self.picker.get_all()])
        self.cumdist = np.zeros((num[-1]+1,), dtype=float)
        for n, g in groupby(num):
            self.cumdist[n:] += len(list(g)) / len(num)

        self.remaining = main.db.status.permission_num['minus']
        self.your_turn = True

        main.show_message(['You get to pick from {}'.format(main.db.status.permission_num['minus']),
                           'We get to pick from {}'.format(main.db.status.permission_num['plus'])])

        main.register(self)
        self.next(main)

    def pick(self, main):
        pts = main.db.status.permission_value(self.pic)
        if self.your_turn:
            self.your_pts = pts
            main.show_message('You pick {} points, our turn'.format(pts))
            self.remaining = main.db.status.permission_num['plus']
            self.your_turn = False
            self.next(main)
        else:
            conf = choice(ascii_lowercase)
            ret = main.show_message(['{} – {}'.format(pts, self.your_pts),
                                     'Permission {}'.format('granted' if self.your_pts > pts else 'denied'),
                                     'Confirm with {}'.format(conf.upper())])
            if conf == ret.lower():
                main.db.status.give_permission(self.your_pts > pts)
            else:
                main.db.status.block_until(main.db.status.permission_break)
            main.unregister()

    def next(self, main):
        self.pic = self.picker.get()
        main.show_image(self.pic)

        self.remaining -= 1

        if not self.your_turn:
            val = main.db.status.permission_value(self.pic)
            if self.remaining == 0:
                self.pick(main)
                return

            cd_orig = self.cumdist ** main.db.status.permission_num['minus']
            cd_rest = self.cumdist ** self.remaining
            pd_orig = np.diff(np.hstack(([0], cd_orig)))
            pd_rest = np.diff(np.hstack(([0], cd_rest)))

            prob_wait = 0.0
            for i in range(0, pd_orig.shape[0]):
                prob_wait += pd_rest[i] * sum(pd_orig[:i+1])

            prob_pick = cd_orig[val - 1]

            if prob_pick >= prob_wait:
                self.pick(main)
        elif self.remaining == 0:
            self.pick(main)

    def key(self, main, event):
        if event.key() == Qt.Key_P and self.your_turn:
            self.pick(main)
        else:
            self.next(main)


class InfoProgram(AbstractProgram):

    def __init__(self, main):
        main.register(self)
        pic = main.current_pic
        message = ['ID: {}'.format(pic.id)]
        main.show_message(message)

    def key(self, main, event):
        main.unregister()
