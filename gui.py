import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

from gui_utils import ImageView, FlagsDialog, MessageDialog, PickerDialog
from programs import Program, InfoProgram


class MainWindow(QMainWindow):

    def __init__(self, db):
        super(MainWindow, self).__init__()
        self.setWindowTitle('PTools')
        self.db = db

        image = ImageView()
        self.setCentralWidget(image)
        self.image = image

        self.picker_dialog = PickerDialog(self.db)
        self.flags_dialog = FlagsDialog(self.db)

        self.programs = []
        Program(self)

    def register(self, program):
        self.programs.append(program)
        program.make_current(self)

    def unregister(self):
        self.programs.pop()
        self.programs[-1].make_current(self)

    def get_picker(self):
        if self.picker_dialog.exec_() == QDialog.Accepted:
            return self.picker_dialog.get_picker()

    def get_flags(self):
        if self.flags_dialog.exec_() == QDialog.Accepted:
            return self.flags_dialog.get_flags()

    def show_image(self, pic):
        self.current_pic = pic
        self.image.load(pic)

    def show_message(self, msg, align='center'):
        if isinstance(msg, str):
            msg = [msg]
        text = ''.join('<p align="{}">{}</p>'.format(align, m) for m in msg)
        MessageDialog(text)

    def start_timer(self, delay, callback):
        timer = QTimer(self)
        timer.timeout.connect(lambda: callback(self, timer))
        timer.start(delay)
        return timer

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_I:
            InfoProgram(self)
            return
        if event.key() == Qt.Key_Q or event.key() == Qt.Key_Escape:
            self.close()
            return
        self.programs[-1].key(self, event)


def run_gui(db, msg=None):
    app = QApplication(sys.argv)
    win = MainWindow(db)
    win.showMaximized()
    if msg:
        print(msg)
        win.show_message(msg)
    return app.exec_()
