import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLayout, QMainWindow, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget
)

from db import UnionPicker

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


class PickerWidget(QWidget):

    def __init__(self, picker):
        super(PickerWidget, self).__init__()

        self.picker = picker

        layout = QHBoxLayout()
        self.setLayout(layout)

        checkbox = QCheckBox(picker.name)
        checkbox.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
        checkbox.setMinimumWidth(100)
        checkbox.stateChanged.connect(self.check)
        layout.addWidget(checkbox)
        self.checkbox = checkbox

        slider = QSlider(Qt.Horizontal)
        slider.setMinimumWidth(300)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(100)
        slider.valueChanged.connect(self.slide)
        layout.addWidget(slider)
        self.slider = slider

        label = QLabel('0%')
        label.setMinimumWidth(40)
        label.setAlignment(Qt.AlignRight)
        layout.addWidget(label)
        self.label = label

        layout.setSizeConstraint(QLayout.SetFixedSize)

    def check(self, state):
        self.slider.setVisible(state == Qt.Checked)
        self.label.setVisible(state == Qt.Checked)
        if state == Qt.Checked:
            self.slide(self.slider.value())
        else:
            self.slide(0)

    def slide(self, value):
        self.label.setText('{}%'.format(value))

    @property
    def checked(self):
        return self.checkbox.checkState() == Qt.Checked

    @property
    def frequency(self):
        return self.slider.value()


class PickerDialog(QDialog):

    def __init__(self, db):
        super(PickerDialog, self).__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.setWindowTitle('Pickers')
        self.db = db
        self.widgets = [PickerWidget(p) for p in db.pickers]
        for w in self.widgets:
            layout.addWidget(w)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setDefault(False)
        cancel_btn.setAutoDefault(False)

        ok_btn = QPushButton('OK')
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btns = QWidget()
        btns.setLayout(QHBoxLayout())
        btns.layout().addWidget(cancel_btn)
        btns.layout().addWidget(ok_btn)
        layout.addWidget(btns)

        self.setFixedSize(self.sizeHint())
        for w in self.widgets:
            w.check(False)

    def make_picker(self):
        union = UnionPicker()
        for w in self.widgets:
            if w.checked and w.frequency:
                union.add(w.picker, w.frequency)
        if not union.pickers:
            return self.db.picker()
        return union
