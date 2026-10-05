"""Drives the real mand-gui.py under an offscreen Qt platform, against a fake `mand` binary.

Run by tests/test_gui.py in a subprocess (Qt wants one QApplication per process):
    QT_QPA_PLATFORM=offscreen python3 tests/gui_driver.py <scratch dir>
Exits 0 only if every check passes; prints one line per check.
"""
import os
import runpy
import shutil
import stat
import sys
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
tmp = os.path.abspath(sys.argv[1])
os.makedirs(os.path.join(tmp, 'pix'), exist_ok=True)
shutil.copy(os.path.join(ROOT, 'pix', 'whole.bmp'), os.path.join(tmp, 'pix', 'whole.bmp'))
saves = os.path.join(tmp, 'saves')
os.makedirs(saves, exist_ok=True)
log = os.path.join(tmp, 'mand.log')
fake = os.path.join(tmp, 'mand')
with open(fake, 'w') as fp:
    fp.write('''#!/bin/sh
# fake renderer: record the arguments (and whether the reference file existed), copy a stock image
echo "$@" >> "%s"
if [ -n "$6" ]; then [ -f "$6" ] && echo "REF_EXISTED" >> "%s"; fi
if [ -f "%s/fail" ]; then exit 1; fi
cp "%s/pix/whole.bmp" "$4"
''' % (log, log, tmp, tmp))
os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
ini = os.path.join(tmp, 'test.ini')
with open(ini, 'w') as fp:
    fp.write('[paths]\nsave_dir=%s\nbin_dir=%s\n' % (saves, tmp))

sys.path.insert(0, ROOT)
sys.argv = [os.path.join(ROOT, 'mand-gui.py'), '-i', ini]
os.chdir(tmp)

from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: E402

failures = []


def check(name, cond, detail=''):
    print('%s  %s %s' % ('ok  ' if cond else 'FAIL', name, '' if cond else detail))
    if not cond:
        failures.append(name)


def release(g, x, y, w):
    """Simulate dragging a rubber band of width w with lower-left at pixel (x, y from top)."""
    h = int(w * 800 / 1200)
    g['reg'].rubberBand.setGeometry(QtCore.QRect(x, y, w, h))
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(x, y), QtCore.Qt.LeftButton,
                           QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    g['reg'].mouseReleaseEvent(ev)


def calls():
    return open(log).read().split('\n') if os.path.exists(log) else []


def drive():
    frame = sys._getframe(1)
    while 'MAP' not in frame.f_globals:
        frame = frame.f_back
    g = frame.f_globals
    MAP, window = g['MAP'], g['window']
    dialogs = []
    QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: dialogs.append(a))

    # -- the view starts on the full set
    check('starts at the reset view', (g['xbox'].text(), g['wbox'].text()) == ('-2.0', '4.0'),
          (g['xbox'].text(), g['wbox'].text()))

    # -- a selection becomes exact Decimal coordinates
    release(g, 300, 500, 600)
    x, w = Decimal(g['xbox'].text()), Decimal(g['wbox'].text())
    check('selection maps to exact coordinates', (x, w) == (Decimal('-1'), Decimal('2')), (x, w))
    check('reset constant is not mutated by selections', str(g['LOG_RESET'].w) == '4.0', g['LOG_RESET'].w)

    # -- Run calls mand with the selection and adds a history entry
    n_before = len(list(MAP))
    g['on_run']()
    first = calls()[0].split()
    check('mand called with x y w file multiplier', len(first) == 5 and Decimal(first[0]) == -1 and Decimal(first[2]) == 2, first)
    check('history entry added', len(list(MAP)) == n_before + 1)
    check('rendered file exists', os.path.exists(MAP.curr.fname), MAP.curr.fname)

    # -- a mand failure adds nothing
    open(os.path.join(tmp, 'fail'), 'w').close()
    release(g, 300, 500, 600)
    count = len(list(MAP))
    g['on_run']()
    check('failed render adds no history entry', len(list(MAP)) == count)
    os.remove(os.path.join(tmp, 'fail'))

    # -- zoom until the view is deep enough to need a reference orbit
    deep = False
    for i in range(30):
        release(g, 541, 441, 120)
        g['on_run']()
        if Decimal(g['wbox'].text()) < Decimal('1e-9'):
            deep = True
            break
    last = calls()
    check('reached a deep view', deep, g['wbox'].text())
    deep_call = [c for c in last if c.strip() and len(c.split()) == 6]
    check('deep render passes a reference orbit file', len(deep_call) >= 1, last[-3:])
    check('reference orbit existed when mand ran', 'REF_EXISTED' in last)
    refs = [c.split()[5] for c in deep_call]
    check('reference orbit file is cleaned up afterwards', refs and not any(os.path.exists(r) for r in refs), refs)
    check('coordinates keep their digits (not rounded through a float)',
          len(g['xbox'].text().replace('-', '').replace('.', '')) > 20, g['xbox'].text())

    # -- Back / thumbnails / Reset
    depth = len(list(MAP))
    g['on_back']()
    check('Back moves to the parent view', Decimal(g['wbox'].text()) > Decimal('1e-9'), g['wbox'].text())
    g['on_reset']()
    check('Reset returns to the full set', g['wbox'].text() == '4.0' and len(list(MAP)) == 1, g['wbox'].text())
    check('history was non-trivial before Reset', depth > 5, depth)

    # -- Save failure is reported to the user rather than swallowed
    class FakeDlg(object):
        AnyFile = 0

        def __init__(self, *a):
            pass

        def setFileMode(self, *a):
            pass

        def exec_(self):
            return True

        def selectedFiles(self):
            return [os.path.join(tmp, 'no-such-dir', 'out.bmp')]
    g['QFileDialog'] = FakeDlg
    g['on_save']()
    check('failed save shows a warning dialog', len(dialogs) == 1, dialogs)

    # -- the rubber band's pixel coordinates line up with the image
    reg = g['reg']
    check('image is anchored at the label origin', bool(reg.alignment() & QtCore.Qt.AlignLeft) and
          bool(reg.alignment() & QtCore.Qt.AlignTop), int(reg.alignment()))
    pm = QtGui.QPixmap(1200, 800)
    pm.fill(QtGui.QColor('red'))
    lab = type(reg)()
    lab.setPixmap(pm)
    lab.resize(1400, 1000)
    img = lab.grab().toImage()
    check('pixmap draws from the label top-left even if the label is larger',
          QtGui.QColor(img.pixel(2, 2)).name() == '#ff0000' and QtGui.QColor(img.pixel(1300, 900)).name() != '#ff0000',
          (QtGui.QColor(img.pixel(2, 2)).name(), QtGui.QColor(img.pixel(1300, 900)).name()))
    return 0


QtWidgets.QApplication.exec_ = lambda self: drive()
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
except SystemExit as e:
    pass
sys.exit(1 if failures else 0)
