#!/usr/bin/env python3
"""Takes the GUI screenshot used in README.md (docs/images/gui.png) from the real program and the real renderer.

    make cpu && QT_QPA_PLATFORM=offscreen python3 docs/make_screenshot.py

It works in a scratch folder (the repository's pix/ is not touched), zooms twice into seahorse valley,
and grabs the window.
"""
import os
import runpy
import shutil
import sys
import tempfile
from decimal import Decimal, localcontext

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'images', 'gui.png')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, ROOT)
from PyQt5 import QtCore, QtWidgets                                  # noqa: E402
import deepzoom                                                      # noqa: E402

SEAHORSE = (Decimal('-0.743643887037158704752191506114774'), Decimal('0.131825904205311970493132056385139'))
STEPS = [Decimal('0.3'), Decimal('0.012')]                           # widths of the two zooms
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'pix'))
shutil.copy(os.path.join(ROOT, 'pix', 'whole.bmp'), os.path.join(tmp, 'pix', 'whole.bmp'))
for tool in ('mand-cpu', 'colorize'):
    os.symlink(os.path.join(ROOT, tool), os.path.join(tmp, tool))
ini = os.path.join(tmp, 'screenshot.ini')
with open(ini, 'w') as fp:
    fp.write('[paths]\nsave_dir=%s\nbin_dir=%s\nrenderer=mand-cpu\n' % (tmp, tmp))


def take(self):
    g = sys._getframe(1)
    while 'MAP' not in g.f_globals:
        g = g.f_back
    G = g.f_globals
    window, reg = G['window'], G['reg']
    window.resize(1700, 1000)
    QtWidgets.QApplication.processEvents()
    G['pal_box'].setCurrentText('twilight')
    for w in STEPS:
        with localcontext() as ctx:
            ctx.prec = 60
            x, y = SEAHORSE[0] - w / 2, SEAHORSE[1] - w * deepzoom.HEIGHT / (2 * deepzoom.WIDTH)
        reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w = x, y, w
        G['show_coords'](x, y, w)
        G['inter'].setCurrentIndex(2)
        G['on_run']()
        QtWidgets.QApplication.processEvents()
    G['split'].setSizes([700, 250])         # give the controls most of the column so the whole Colors box shows
    QtWidgets.QApplication.processEvents()
    G['controls_scroll'].verticalScrollBar().setValue(G['controls_scroll'].verticalScrollBar().maximum())
    QtWidgets.QApplication.processEvents()
    window.grab().save(OUT, 'PNG')
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


QtWidgets.QApplication.exec_ = take
QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: print('warning:', a[1:], file=sys.stderr))
sys.argv = [os.path.join(ROOT, 'mand-gui.py'), '-i', ini]
os.chdir(tmp)
runpy.run_path(sys.argv[0], run_name='__main__')
