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


def save_side_states(shots):
    """docs/images/side-column.png: the three states of the side column next to each other, each with a caption."""
    from PIL import Image, ImageDraw, ImageFont
    gap, head = 16, 46
    tiles = []
    for label, pix in shots:
        path = os.path.join(tmp, 'side.png')
        pix.save(path, 'PNG')
        tiles.append((label, Image.open(path).convert('RGB')))
    height = max(t.height for _, t in tiles)
    sheet = Image.new('RGB', (sum(t.width for _, t in tiles) + gap * (len(tiles) + 1), height + head + gap), (45, 45, 45))
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 24)
    d = ImageDraw.Draw(sheet)
    x = gap
    for label, t in tiles:
        box = d.textbbox((0, 0), label, font=font)
        d.text((x + (t.width - (box[2] - box[0])) // 2, 8), label, font=font, fill=(235, 235, 235))
        sheet.paste(t, (x, head))
        x += t.width + gap
    sheet.save(os.path.join(HERE, 'images', 'side-column.png'), optimize=True)


def take(self):
    g = sys._getframe(1)
    while 'MAP' not in g.f_globals:
        g = g.f_back
    G = g.f_globals
    window, reg = G['window'], G['reg']
    window.resize(1900, 1150)
    QtWidgets.QApplication.processEvents()
    for w in STEPS:
        with localcontext() as ctx:
            ctx.prec = 60
            x, y = SEAHORSE[0] - w / 2, SEAHORSE[1] - w * deepzoom.HEIGHT / (2 * deepzoom.WIDTH)
        reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w = x, y, w
        G['show_coords'](x, y, w)
        G['inter'].setCurrentIndex(2)
        G['on_run']()
        QtWidgets.QApplication.processEvents()
    split, cb, ib = G['split'], G['controls_btn'], G['images_btn']
    total = sum(split.sizes())
    need = G['controls_panel'].sizeHint().height() + 4
    split.setSizes([need, total - need])    # the controls get all the height they need, so every control shows
    QtWidgets.QApplication.processEvents()
    window.grab().save(OUT, 'PNG')
    # the side column in its three states: both parts, the controls alone, the images alone
    shots = []
    for label, controls, images in (('both parts', True, True), ('Controls only', True, False), ('Images only', False, True)):
        for turning_on in (True, False):                  # open what is wanted first: the last open part cannot be hidden
            for button, on in ((cb, controls), (ib, images)):
                if on == turning_on and button.isChecked() != on:
                    button.click()
        QtWidgets.QApplication.processEvents()
        shots.append((label, G['side'].grab()))
    for button in (cb, ib):
        if not button.isChecked():
            button.click()
    save_side_states(shots)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


QtWidgets.QApplication.exec_ = take
QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: print('warning:', a[1:], file=sys.stderr))
sys.argv = [os.path.join(ROOT, 'mand-gui.py'), '-i', ini]
os.chdir(tmp)
runpy.run_path(sys.argv[0], run_name='__main__')
