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

    def load(self, filename):
        self.orig_pixmap = QPixmap(filename)

    def resize(self):
        pixmap = self.orig_pixmap.scaled(self.width(), self.height(), 1, 1)
        self.setPixmap(pixmap)

    def resizeEvent(self, event):
        self.resize()



class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle('PTools')

        self.label = ImageView()
        self.label.load(sys.argv[1])
        self.setCentralWidget(self.label)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    win = MainWindow()
    win.show()

    sys.exit(app.exec_())
