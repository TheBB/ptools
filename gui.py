import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow


class ImageView(QLabel):

    def __init__(self):
        super(ImageView, self).__init__()
        self.setMinimumSize(1,1)
        self.setAlignment(Qt.Alignment(0x84))
        self.setStyleSheet('QLabel { background-color: black; }')

        self.orig_pixmap = None

    def load(self, pic):
        self.orig_pixmap = QPixmap(pic.filename)
        self.resize()

    def resize(self):
        pixmap = self.orig_pixmap.scaled(self.width(), self.height(), 1, 1)
        self.setPixmap(pixmap)

    def resizeEvent(self, event):
        self.resize()


class MainWindow(QMainWindow):

    def __init__(self, db):
        super(MainWindow, self).__init__()
        self.setWindowTitle('PTools')
        self.db = db
        self.picker = db.picker()

        image = ImageView()
        image.load(self.picker.get())
        self.setCentralWidget(image)
        self.image = image

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q:
            self.close()
        elif event.key() == Qt.Key_Space:
            self.image.load(self.picker.get())


def run_gui(db):
    app = QApplication(sys.argv)
    win = MainWindow(db)
    win.showMaximized()
    return app.exec_()
