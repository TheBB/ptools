from datetime import datetime, date, timedelta
from itertools import groupby
from math import ceil, sqrt
from os.path import join
from random import random, choice
from string import ascii_lowercase
from subprocess import run
import re
import numpy as np

from PyQt5.QtCore import Qt

from db import Picture, UnionPicker


class AbstractProgram:

    def key(self, m, event):
        pass

    def make_current(self, m, *args, **kwargs):
        pass

    def pause(self, m):
        pass

    def unpause(self, m):
        pass


class ShowProgram(AbstractProgram):

    def __init__(self, m):
        self.picker = None
        m.register(self)
        self.make_current(m)

    def pic(self, m):
        picker = self.picker or m.st.picker()
        m.show_image(picker.get())

    def make_current(self, m, *args, **kwargs):
        self.pic(m)

    def key(self, m, event):
        if event.key() == Qt.Key_P:
            self.picker = m.get_picker() or self.picker
            self.pic(m)
        elif event.key() == Qt.Key_S:
            SyncProgram(m)
        elif event.key() == Qt.Key_T:
            StatusProgram(m)
        elif event.key() == Qt.Key_M:
            msg = m.st.mas()
            m.show_message(msg)
        elif event.key() == Qt.Key_N:
            msg = m.st.mas(skip=True)
            m.show_message(msg)
        elif event.key() == Qt.Key_G:
            if m.st.pts == 0:
                BestOfGame(m)
            elif m.st.you_leading or not m.st.can_ask_permission():
                StatusProgram(m)
            elif m.st.can_ask_permission():
                m.st.block_until(m.st.perm_break)
                PermissionProgram(m)
        else:
            self.pic(m)


class MessageProgram(AbstractProgram):

    def __init__(self, m, text):
        self.text = text
        m.register(self)

    def key(self, m, event):
        m.show_message(self.text)
        m.unregister()


class SyncProgram(AbstractProgram):

    def __init__(self, m):
        self.del_ids = m.db.get_delete_ids()
        ret = m.db.get_remote()
        ndel, nmov, self.staged = m.db.sync_local()

        self.data = {
            'new_loc': int(re.search(r'Number of created files: (?P<n>\d+)', ret).group('n')),
            'del_loc': int(re.search(r'Number of deleted files: (?P<n>\d+)', ret).group('n')),
            'del_inc': ndel,
            'mov_inc': nmov,
            'del_loc': len(self.del_ids),
        }

        self.moves = {}
        m.register(self)
        self.next(m)

    def next(self, m):
        if self.staged:
            fn = self.staged[-1]
            m.show_image(self.staged[-1])
        else:
            if self.del_ids:
                for pic in m.db.query().filter(Picture.id.in_(self.del_ids)):
                    m.db.delete(pic)
            m.db.session.add_all(self.moves.values())
            m.db.session.commit()

            for fn, pic in self.moves.items():
                run(['mv', fn, pic.filename])

            ret = m.db.put_remote()
            self.data['new_rem'] = int(re.search(r'Number of created files: (?P<n>\d+)', ret).group('n'))
            self.data['del_rem'] = int(re.search(r'Number of deleted files: (?P<n>\d+)', ret).group('n'))
            m.show_message("""New from remote: {new_loc}<br>
                                 Previously deleted remotely: {del_loc}<br>
                                 Deleted from DB: {del_inc}<br>
                                 Deleted locally: {del_loc}<br>
                                 Re-staged: {mov_inc}<br>
                                 New on remote: {new_rem}<br>
                                 Newly deleted remotely: {del_rem}""".format(**self.data),
                              align='left')

            m.unregister()

    def key(self, m, event):
        flags = m.get_flags()
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
            self.next(m)


class BestOfGame(ShowProgram):

    def __init__(self, m):
        self.picker = m.st.bestof_picker

        self.pts = {True: [0, 0, 0], False: [0, 0, 0]}
        self.max_pts = [5, 5, 10]
        self.current = choice([True, False])
        self.prev_winner = None
        self.speed = 0.7
        self.bias = 0.0
        self.done = False

        m.show_message('Best of: ' + ', '.join(str(s) for s in self.max_pts))

        m.register(self)
        self.next(m)

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

    def next(self, m):
        if self.done:
            m.unregister()
            return

        p = lambda b: max(min((1.020**b) / (1.020**b + 1), 0.93), 0.07)
        conv = lambda p: self.speed * p
        threshold = conv(p(self.bias) if self.current else 1 - p(self.bias))
        win = random() <= threshold
        pic = self.picker.get()
        while m.st.bestof_trigger(pic) != win:
            pic = self.picker.get()
        m.show_image(pic)

        if not win:
            self.current = not self.current
            return

        npts = m.st.bestof_value(pic)
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
            MessageProgram(m, msg)
            self.done = True
            m.st.update_points_leader('us' if self.current else 'you', total)
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
        MessageProgram(m, msg)

        self.prev_winner = self.current

    def make_current(self, m, *args, **kwargs):
        self.next(m)

    def key(self, m, event):
        self.next(m)


class StatusProgram(AbstractProgram):

    def __init__(self, m):
        m.register(self)
        if m.st.pts == 0:
            m.show_message('Undecided')
        else:
            leader = 'our' if m.st.we_leading else 'your'
            msg = ['{} points in {} favour'.format(m.st.pts, leader)]
            if m.st.we_leading:
                if m.st.perm_until > datetime.now():
                    diff = m.st.perm_until - datetime.now()
                    msg.append('Permission for {} minutes'.format(diff.seconds//60))
                else:
                    if m.st.ask_blocked_until > datetime.now():
                        diff = m.st.ask_blocked_until - datetime.now()
                        msg.append('Can ask permission in {} minutes'.format(diff.seconds//60 + 1))
                    else:
                        msg.append('Can ask permission')
            m.show_message(msg)

    def key(self, m, event):
        m.unregister()


class PermissionProgram(AbstractProgram):

    @staticmethod
    def num_our(dist_our, dist_you, num_you, prob):
        max_num = max(dist_our[-1], dist_you[-1])
        your_cumdist = np.zeros((max_num+1,), dtype=float)
        for n, g in groupby(dist_you):
            your_cumdist[n:] += len(list(g)) / len(dist_you)
        your_cumdist = 1.0 - your_cumdist ** num_you

        our_cumdist = np.zeros((max_num+1,), dtype=float)
        for n, g in groupby(dist_our):
            our_cumdist[n:] += len(list(g)) / len(dist_you)

        def prob_you(num_our):
            our = our_cumdist.copy() ** num_our
            prob = our[0] * your_cumdist[0]
            prob += sum((our[1:] - our[:-1]) * your_cumdist[1:])
            return prob

        minus, plus = 1, num_you
        while prob_you(plus) > prob:
            minus = plus
            plus *= 2
        while plus > minus + 1:
            test = (minus + plus) // 2
            if prob_you(test) > prob:
                minus = test
            else:
                plus = test

        return plus

    def __init__(self, m):
        self.picker_you = m.st.perm_yours
        self.picker_our = m.st.perm_ours

        dist_our = sorted([m.st.perm_value(p) for p in self.picker_our.get_all()])
        dist_you = sorted([m.st.perm_value(p) for p in self.picker_you.get_all()])
        self.num_our = PermissionProgram.num_our(dist_our, dist_you,
                                                 m.st.perm_num,
                                                 m.st.perm_prob)
        self.remaining = m.st.perm_num
        self.picker = self.picker_you
        self.your_turn = True
        self.total_added = 0
        self.prev_val = 0
        self.your_pts = 0
        self.our_pts = 0

        m.show_message(['You get to pick from {}'.format(self.remaining),
                           'We get to pick from {}'.format(self.num_our)])

        m.register(self)
        self.next(m)

    def finish(self, m):
        if self.your_turn:
            pts = m.st.perm_value(self.pic)
            m.show_message('You pick {} points, our turn'.format(self.your_pts))
            self.remaining = self.num_our
            self.your_turn = False
            self.picker = self.picker_our
            self.next(m)
            return

        conf = choice(ascii_lowercase)
        ret = m.show_message([
            '{} – {}'.format(self.our_pts, self.your_pts),
            'Permission {}'.format('granted' if self.your_pts > self.our_pts else 'denied'),
            'Confirm with {}'.format(conf.upper()),
        ])
        if conf == ret.lower():
            m.st.give_permission(self.your_pts > self.our_pts,
                                           reduced=min(55, self.total_added/3))
            m.st.block_until(self.total_added/4)
        else:
            m.st.block_until(m.st.perm_break + self.total_added/4)
        m.unregister()

    def pause(self, m):
        now = datetime.now()
        if hasattr(self, 'until'):
            self.delta_until = self.until - now
            self.delta_before = self.before - now

    def unpause(self, m):
        now = datetime.now()
        if hasattr(self, 'delta_until'):
            self.until = now + self.delta_until
            self.before = now + self.delta_before

    def next(self, m):
        now = datetime.now()
        self.pic = self.picker.get()
        m.show_image(self.pic)

        self.remaining -= 1

        val = m.st.perm_value(self.pic)
        if self.your_turn:
            self.your_pts = max(self.your_pts, val)
            if self.remaining == 0:
                self.finish(m)
        else:
            self.our_pts = max(self.our_pts, val)
            self.prev_val = max(self.prev_val - 1, val)
            if (self.remaining == 0 and self.prev_val == 1) or val >= self.your_pts:
                self.finish(m)
                return
            if hasattr(self, 'until') and now < self.until:
                add = int(ceil((self.until - now).total_seconds()))
                print('too soon', add)
                self.remaining += add
                self.total_added += add
            elif hasattr(self, 'before') and now > self.before:
                add = int(ceil((now - self.before).total_seconds()))
                print('too late', add)
                self.remaining += add
                self.total_added += add

            until = self.prev_val - (1.0 - m.st.perm_m_until) * sqrt(self.prev_val)
            before = self.prev_val + (m.st.perm_m_before - 1.0) * sqrt(self.prev_val)
            self.until = now + timedelta(seconds=until)
            self.before = now + timedelta(seconds=before)

    def key(self, m, event):
        self.next(m)


class InfoProgram(AbstractProgram):

    def __init__(self, m):
        m.register(self)
        pic = m.current_pic
        message = ['ID: {}'.format(pic.id)]
        m.show_message(message)

    def key(self, m, event):
        m.unregister()
