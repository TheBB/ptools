from PyQt5.QtCore import Qt

from db import Picture


class Program:

    def __init__(self, main, name='PTools'):
        self.name = 'PTools'
        self.picker = None
        main.register(self)

    def make_current(self, main):
        if not self.picker:
            self.picker = main.db.pickers[0]
        main.show_image(self.picker.get())
        main.setWindowTitle(self.name)

    def key(self, main, event):
        if event.key() == Qt.Key_P:
            self.picker = (main.get_picker() or self.picker)
            main.show_image(self.picker.get())
        elif event.key() == Qt.Key_S:
            SyncProgram(main)
        else:
            main.show_image(self.picker.get())


class SyncProgram:

    def __init__(self, main):
        self.name = 'Synchronize'
        self.staged = main.db.synchronize()
        main.register(self)

    def next(self, main):
        if self.staged:
            fn = self.staged[-1]
            main.show_image(self.staged[-1])
        else:
            main.unregister()

    def make_current(self, main):
        self.next(main)

    def key(self, main, event):
        flags = main.get_flags()
        if flags:
            fn = self.staged.pop()
            print(fn, flags)
            self.next(main)
