#!/usr/bin/python
#$Id: mand_gui.py,v 1.18 2017/12/07 20:39:27 dan Exp dan $
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from subprocess import call
from collections import namedtuple

STARTFILE = '/home/dan/mandelbrot/whole.bmp'
NAMEBASE = '/home/dan/mandelbrot/pix/FIRST'

XYW = namedtuple('XYW', ('x', 'y', 'width'))
RESET = XYW(-2.0, -1.333333, 4.0)
COUNT = 1
HEIGHT = 800
WIDTH = 1200


class LogXYW(object):
    def __init__(self, x, y, w):
        self.x = x
        self.y = y
        self.width = w


class WaitCurs(object):
    def __enter__(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def __exit__(*args, **kwargs):
        QApplication.restoreOverrideCursor()


class PicRegion(QLabel):
    def __init__(self, parent = None):
        QLabel.__init__(self, parent)
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.curr_xyw = LogXYW(*RESET) 
        self.cand_xyw = LogXYW(*RESET) 
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = QPoint(event.pos())
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
    
    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            geom = self.rubberBand.geometry();
            pixx = geom.bottomLeft().x()
            pixy = HEIGHT - geom.bottomLeft().y()
            pixw = geom.width() 
            log_height = (self.curr_xyw.width * HEIGHT) / WIDTH
            if pixw > 10: 
                self.cand_xyw.x = self.curr_xyw.x + pixx * self.curr_xyw.width / WIDTH
                self.cand_xyw.y = self.curr_xyw.y + pixy * log_height / HEIGHT
                self.cand_xyw.width = self.curr_xyw.width * pixw / WIDTH 
                xbox.setText(str(self.cand_xyw.x))
                ybox.setText(str(self.cand_xyw.y))
                wbox.setText(str(self.cand_xyw.width))
            print('%s %s %s' % (self.cand_xyw.x, self.cand_xyw.y, self.cand_xyw.width))
            self.rubberBand.hide()


def freset():
    global COUNT
    reg.setPixmap(QPixmap(STARTFILE))
    reg.curr_xyw = LogXYW(*RESET) 
    reg.cand_xyw = LogXYW(*RESET) 
    xbox.setText(str(RESET.x))
    ybox.setText(str(RESET.y))
    wbox.setText(str(RESET.width))
    inter.setCurrentIndex(0)
    COUNT = 1


@pyqtSlot()
def on_reset():
    freset()
    

@pyqtSlot()
def on_click():
    global COUNT
    with WaitCurs():
        name = '%s%s' % (NAMEBASE, COUNT)
        reg.curr_xyw.x = reg.cand_xyw.x
        reg.curr_xyw.y = reg.cand_xyw.y
        reg.curr_xyw.width = reg.cand_xyw.width
        xval = xbox.text()
        yval = ybox.text()
        wval = wbox.text()
        ival = inter.currentText()
        print('Calling mand %s %s %s %s %s' % (xval, yval, wval, name, ival))
        call(['/home/dan/mandelbrot/mand', xval, yval, wval, name, ival])
        print('Done')
        reg.setPixmap(QPixmap('%s.bmp' % name))
        COUNT += 1


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QWidget()
    buttonbox = QLabel()
    reg = PicRegion()
    reg.setPixmap(QPixmap(STARTFILE))
    go = QPushButton('Go') 
    reset = QPushButton('Reset') 
    go.clicked.connect(on_click)
    reset.clicked.connect(on_reset)
    xbox = QLineEdit()
    xbox.setReadOnly(True) 
    ybox = QLineEdit()
    ybox.setReadOnly(True) 
    wbox = QLineEdit()
    wbox.setReadOnly(True) 
    inter = QComboBox()
    inter.addItems(['1','2','3','4','5','6','7','8','9'])
    vbox = QVBoxLayout()
    vbox.addWidget(reg)
    hbox = QHBoxLayout() 
    hbox.addWidget(xbox)
    hbox.addWidget(ybox)
    hbox.addWidget(wbox)
    hbox.addWidget(inter)
    hbox.addWidget(go)
    hbox.addWidget(reset)
    buttonbox.setLayout(hbox)
    vbox.addWidget(buttonbox)
    window.setLayout(vbox) 
    window.setWindowTitle("Mandelbrot Set Viewer")
    freset()
    window.resize(1200,880)
    window.show()
    sys.exit(app.exec_())

