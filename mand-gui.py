#!/usr/bin/env python
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from sys import argv, exit
from subprocess import call
from shutil import copyfile
from collections import namedtuple
from math import ceil
from configparser import ConfigParser

config = ConfigParser()
config.read('gpu-mand.ini')
paths = config['paths']

TITLE = 'Mandelbrot Set Viewer'
STARTFILE = '{}/whole.bmp'.format(paths['bmp_dir'])
NAMEPATT = '{}/mandapp%s.bmp'.format(paths['bmp_dir'])
RESET_COORDS = (-2.0, -1.333333, 4.0, 0)
MAX_MULT = 30
PIX_WID = 1200
PIX_HGT = 800
WIN_WID = 1460
WIN_HGT = 950
TN_WID = 160
TN_HGT = 120

XYWD = namedtuple('XYWD', ('x', 'y', 'w', 'd'))
PGINFO = namedtuple('PGINFO', ('xywd', 'fname', 'icon', 'parent'))


class LogXYW(object):
    def __init__(self, x, y, w, d):
        self.x = x
        self.y = y
        self.w = w
        self.d = d


LOG_RESET = LogXYW(*RESET_COORDS)
XYWD_RESET = XYWD(*RESET_COORDS)


def get_tnail(fname):
    button = QPushButton()
    button.setIcon(QIcon(fname))
    button.setIconSize(QSize(TN_WID,TN_HGT))
    button.clicked.connect(on_tnclick(fname))
    return button


class MTree(object):
    def __init__(self):
        self.reset()

    def __getitem__(self, fname):
        return self._map.get(fname)

    def __iter__(self):
        return iter(self._map.values())

    def reset(self):
        global INITPG  
        self._count = 0
        self._map = {INITPG.fname:INITPG}
        self._current = INITPG
        return self._current

    def add(self, xywd):
        pg = PGINFO(xywd, self.fname, get_tnail(self.fname), self._current.fname)
        self._map[pg.fname] = self._current = pg
        self._count += 1
        return self._current

    def set(self, pg):
        if pg.fname in self._map:
            self._current = self._map[pg.fname]
        return self._current

    def rem(self, pg):
        if pg.parent and self._map.has_key(pg.fname):
            self._current = self._map[pg.parent]
            del(self._map[pg.fname])
        return self._current

    @property
    def fname(self):
        return NAMEPATT % self._count

    @property
    def back(self):
        if self._current.parent:
            self._current = self._map[self._current.parent]
        return self._current

    @property
    def curr(self):
        return self._current


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
        self.cand_xyw = LOG_RESET 
    
    def mousePressEvent(self, event):
        self.rubberBand.hide()
        if event.button() == Qt.LeftButton:
            self.origin = QPoint(event.pos())
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
    
    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            width = event.pos().x() - self.origin.x()
            height = ceil(abs(width) * (1.0 * PIX_HGT) / PIX_WID)
            sign = 1 if self.origin.y() < event.pos().y() else -1
            self.rubberBand.setGeometry(QRect(self.origin, QSize(width, sign*height)).normalized())
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            geom = self.rubberBand.geometry();
            pixx = geom.bottomLeft().x()
            pixy = PIX_HGT - geom.bottomLeft().y()
            pixw = geom.width() 
            log_height = (MAP.curr.xywd.w * PIX_HGT) / PIX_WID
            if pixw > 10: 
                self.cand_xyw.x = MAP.curr.xywd.x + pixx * MAP.curr.xywd.w / PIX_WID
                self.cand_xyw.y = MAP.curr.xywd.y + pixy * log_height / PIX_HGT
                self.cand_xyw.w = MAP.curr.xywd.w * pixw / PIX_WID 
                self.cand_xyw.d = inter.currentIndex()
                xbox.setText(str(self.cand_xyw.x))
                ybox.setText(str(self.cand_xyw.y))
                wbox.setText(str(self.cand_xyw.w))


def fset(item):
    reg.rubberBand.hide()
    xbox.setText(str(item.xywd.x))
    ybox.setText(str(item.xywd.y))
    wbox.setText(str(item.xywd.w))
    reg.cand_xyw.x = item.xywd.x
    reg.cand_xyw.y = item.xywd.y
    reg.cand_xyw.w = item.xywd.w
    reg.cand_xyw.d = int(item.xywd.d)
    inter.setCurrentIndex(int(item.xywd.d))
    reg.setPixmap(QPixmap(str(item.fname)))
    for mem in MAP:
        mem.icon.setFlat(True)
    item.icon.setFlat(False)
    MAP.set(item)


@pyqtSlot()
def on_reset():
    with WaitCurs():
        for i in reversed(range(scr_layout.count()-1)): 
            scr_layout.itemAt(i).widget().setParent(None)
        fset(MAP.reset())


@pyqtSlot()
def on_run():
    global MAP
    with WaitCurs():
        reg.cand_xyw.d = inter.currentIndex()
        xval = xbox.text()
        yval = ybox.text()
        wval = wbox.text()
        ival = inter.currentText()
        call(['{}/mand'.format(paths['bin_dir']), xval, yval, wval, MAP.fname, ival])
        added = MAP.add(XYWD(reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w, int(reg.cand_xyw.d)))
        scr_layout.insertWidget(0, MAP.curr.icon)
        fset(MAP.curr) 


@pyqtSlot()
def on_save():
        start = paths['save_dir']
        dlg = QFileDialog(window, 'Save File', start, 'Images (*.bmp)')
        dlg.setFileMode(QFileDialog.AnyFile)
        if dlg.exec_():
            with WaitCurs():
                filenames = dlg.selectedFiles()
                fname = str(filenames[0])
                if not fname.endswith('.bmp'):
                    fname = '%s.bmp' % fname
                try:
                    copyfile(MAP.curr.fname, fname)
                except Exception as e:
                    print(str(e))


def on_tnclick(logxyw):
    @pyqtSlot()
    def wrapped():
        fset(MAP[logxyw])
    return wrapped
    

@pyqtSlot()
def on_back():
    fset(MAP.back)


if __name__ == '__main__':
    app = QApplication(argv)
    INITPG = PGINFO(XYWD_RESET, STARTFILE, get_tnail(STARTFILE), None)
    MAP = MTree()
    window = QWidget()
    buttonbox = QLabel()
    reg = PicRegion()
    reg.setPixmap(QPixmap(STARTFILE))
    run = QPushButton('Run') 
    run.clicked.connect(on_run)
    reset = QPushButton('Reset') 
    reset.clicked.connect(on_reset)
    back = QPushButton('Back') 
    back.clicked.connect(on_back) 
    save = QPushButton('Save')
    save.clicked.connect(on_save)
    xbox = QLineEdit()
    xbox.setReadOnly(True) 
    ybox = QLineEdit()
    ybox.setReadOnly(True) 
    wbox = QLineEdit()
    wbox.setReadOnly(True) 
    inter = QComboBox()
    inter.addItems([str(n) for n in range(1,MAX_MULT+1)])
    vbox = QVBoxLayout()
    vbox.addWidget(reg)
    hbox = QHBoxLayout() 
    hbox.addWidget(xbox)
    hbox.addWidget(ybox)
    hbox.addWidget(wbox)
    hbox.addWidget(inter)
    hbox.addWidget(run)
    hbox.addWidget(back)
    hbox.addWidget(save)
    hbox.addWidget(reset)
    buttonbox.setLayout(hbox)
    vbox.addWidget(buttonbox)
    lside = QWidget()
    lside.setLayout(vbox) 
    rside = QWidget()
    scr_layout = QVBoxLayout()
    rside.setLayout(scr_layout) 
    scroll = QScrollArea()
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidgetResizable(True)
    scroll.setWidget(rside)
    scr_layout.insertWidget(0, INITPG.icon)
    wholescr = QHBoxLayout()
    wholescr.addWidget(lside)
    wholescr.addWidget(scroll)
    window.setLayout(wholescr) 
    window.setWindowTitle(TITLE)
    fset(MAP.curr)
    window.resize(WIN_WID,WIN_HGT)
    window.setMaximumSize(QSize(WIN_WID,WIN_HGT))
    window.setMinimumSize(QSize(WIN_WID,WIN_HGT))
    window.show()
    exit(app.exec_())

