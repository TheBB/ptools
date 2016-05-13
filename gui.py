import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow

from gui_utils import ImageView, PickerDialog
from programs import Program


class MainWindow(QMainWindow):

    def __init__(self, db):
        super(MainWindow, self).__init__()
        self.setWindowTitle('PTools')
        self.db = db

        image = ImageView()
        self.setCentralWidget(image)
        self.image = image

        self.picker_dialog = PickerDialog(self.db)

        self.programs = []
        Program(self)

    def register(self, program):
        self.programs.append(program)
        program.make_current(self)

    def unregister(self):
        self.programs.pop()
        self.programs[-1].make_current(self)

    def make_picker(self):
        if self.picker_dialog.exec_() == QDialog.Accepted:
            return self.picker_dialog.make_picker()

    def show_image(self, pic):
        self.image.load(pic)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q or event.key() == Qt.Key_Escape:
            self.close()
            return

        self.programs[-1].key(self, event)


def run_gui(db):
    app = QApplication(sys.argv)
    win = MainWindow(db)
    win.showMaximized()
    return app.exec_()
