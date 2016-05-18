from os.path import join
from random import random, choice
from subprocess import run

from PyQt5.QtCore import Qt

from db import Picture, UnionPicker


class Program:

    def __init__(self, main, name='PTools'):
        self.name = 'PTools'
        self.picker = None
        main.register(self)

    def make_current(self, main):
        self.picker = main.db.status.picker()
        main.show_image(self.picker.get())
        main.setWindowTitle(self.name)

    def key(self, main, event):
        if event.key() == Qt.Key_P:
            self.picker = (main.get_picker() or self.picker)
            main.show_image(self.picker.get())
        elif event.key() == Qt.Key_S:
            SyncProgram(main)
        elif event.key() == Qt.Key_B:
            BestOfGame(main)
        else:
            main.show_image(self.picker.get())


class SyncProgram:

    def __init__(self, main):
        self.name = 'Synchronize'
        main.db.get()
        self.staged = main.db.sync_local()
        self.moves = {}
        main.register(self)

    def next(self, main):
        if self.staged:
            fn = self.staged[-1]
            main.show_image(self.staged[-1])
        else:
            main.db.session.add_all(self.moves.values())
            main.db.session.commit()

            for fn, pic in self.moves.items():
                run(['mv', fn, pic.filename])

            main.db.put()
            main.unregister()

    def make_current(self, main):
        self.next(main)

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


class BestOfGame(Program):

    def __init__(self, main):
        self.name = 'Best Of'
        self.picker = main.db.status.bestof_picker

        self.pts = {True: [0, 0, 0], False: [0, 0, 0]}
        self.max_pts = [5, 5, main.db.status.bestof_width]
        self.current = choice([True, False])
        self.prev_winner = None
        self.speed = 0.7
        self.bias = 0.0

        main.show_message( 'Best of: ' + ', '.join(str(s) for s in self.max_pts))

        main.register(self)

    def add_pts(self, winner, npts):
        loser = self.pts[not winner]
        winner = self.pts[winner]
        while npts > 0 and winner[-1] < self.max_pts[-1]:
            i = 0
            winner[i] += 1
            while winner[i] == self.max_pts[i]:
                if i == len(self.max_pts) - 1:
                    break
                winner[i+1] += 1
                winner[i] = loser[i] = 0
                i += 1
            npts -= 1

    def next(self, main):
        p = lambda b: max(min((1.020**b) / (1.020**b + 1), 0.93), 0.07)
        conv = lambda p: self.speed * p
        threshold = conv(p(self.bias) if self.current else 1 - p(self.bias))
        win = random() <= threshold
        pic = self.picker.get()
        while main.db.status.bestof_trigger(pic) != win:
            pic = self.picker.get()
        main.show_image(pic)

        if win:
            npts = main.db.status.bestof_value(pic)
            self.add_pts(self.current, npts)

            if self.prev_winner != self.current:
                self.bias = 0.0
            else:
                self.bias += (2 * int(self.current) - 1) * min(npts, 15)

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
        else:
            self.current = not self.current

    def make_current(self, main):
        self.next(main)

    def key(self, main, event):
        self.next(main)


class MessageProgram:

    def __init__(self, main, text):
        self.text = text
        main.register(self)

    def make_current(self, main):
        pass

    def key(self, main, event):
        main.show_message(self.text)
        main.unregister()
