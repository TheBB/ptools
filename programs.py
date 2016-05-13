from PyQt5.QtCore import Qt


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
            self.picker = (main.make_picker() or self.picker)
            main.show_image(self.picker.get())
        elif event.key() == Qt.Key_Space:
            main.show_image(self.picker.get())
