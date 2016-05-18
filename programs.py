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
        self.bias = 0.0

        self.pts = {True: [0, 0, 0], False: [0, 0, 0]}
        self.max_pts = [5, 5, main.db.status.bestof_width]
        self.next_message = 'Best of: ' + ', '.join(str(s) for s in self.max_pts)
        self.current = choice([True, False])

        main.register(self)

    def add_pts(self, winner, npts):
        winner = self.pts[winner]
        loser = self.pts[loser]
        while npts > 0 and target[-1] < self.max_pts[-1]:
            i = 0
            winner[i] += 1
            while target[i] > self.max_pts[i] and target[-1] < self.max_pts[-1]:
                winner[i] = loser[i] = 0
                winner[i+1] += 1
                i += 1
            npts -= 1

    def next(self, main):
        if self.next_message:
            main.show_message(self.next_message)
            self.next_message = None

        win = random() <= 0.5
        pic = self.picker.get()
        while main.db.status.bestof_trigger(pic) != win:
            pic = self.picker.get()
        main.show_image(pic)

        if win:
            npts = main.db.status.bestof_value(pic)
            self.add_pts(self.current, npts)
            self.next_message = ['{} points for {}'.format(npts, 'us' if self.current else 'you')]
            for a, b in zip(self.pts[True], self.pts[False]):
                self.next_message.append('{} – {}'.format(a, b))

        self.current = not self.current

    def make_current(self, main):
        self.next(main)

    def key(self, main, event):
        self.next(main)
