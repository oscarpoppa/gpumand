"""Drives the real mand-gui.py under an offscreen Qt platform, against a fake `mand` binary.

Run by tests/test_gui.py in a subprocess (Qt wants one QApplication per process):
    QT_QPA_PLATFORM=offscreen python3 tests/gui_driver.py <scratch dir> [--real]
With --real the GUI drives the real mand-cpu renderer (must be built) instead of a fake one.
Exits 0 only if every check passes; prints one line per check.
"""
import os
import runpy
import shutil
import stat
import sys
from decimal import Decimal, localcontext

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
REAL = '--real' in sys.argv
if REAL:
    sys.argv.remove('--real')
tmp = os.path.abspath(sys.argv[1])
os.makedirs(os.path.join(tmp, 'pix'), exist_ok=True)
shutil.copy(os.path.join(ROOT, 'pix', 'whole.bmp'), os.path.join(tmp, 'pix', 'whole.bmp'))
saves = os.path.join(tmp, 'saves')
os.makedirs(saves, exist_ok=True)
log = os.path.join(tmp, 'mand.log')
fake = os.path.join(tmp, 'mand-cpu' if REAL else 'mand')
if REAL:
    os.symlink(os.path.join(ROOT, 'mand-cpu'), fake)
    os.symlink(os.path.join(ROOT, 'colorize'), os.path.join(tmp, 'colorize'))
fp = open(os.devnull, 'w') if REAL else open(fake, 'w')
with fp:
    fp.write('''#!/bin/sh
# fake renderer: record the arguments (and whether the reference file existed), copy a stock image
echo "$@" >> "%s"
if [ -n "$6" ]; then [ -f "$6" ] && echo "REF_EXISTED" >> "%s"; fi
if [ -f "%s/fail" ]; then exit 1; fi
cp "%s/pix/whole.bmp" "$4"
''' % (log, log, tmp, tmp))
if not REAL:
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
ini = os.path.join(tmp, 'test.ini')
with open(ini, 'w') as fp:
    fp.write('[paths]\nsave_dir=%s\nbin_dir=%s\n' % (saves, tmp))
    # a trailing comment on a setting line must not become part of the value
    fp.write('renderer=%s   ; which program draws the images\n' % ('mand-cpu' if REAL else 'mand'))

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


# A point on the set's boundary: views centred on it keep showing structure at every depth.
TARGET = (Decimal('-0.743643887037158704752191506114774'), Decimal('0.131825904205311970493132056385139'))


def aim(g, box=120):
    """Rubber-band (left, top, width) of a box centred on TARGET in the current view."""
    x, y, w = (Decimal(g[n].text()) for n in ('xbox', 'ybox', 'wbox'))
    with localcontext() as ctx:
        ctx.prec = 100
        px = int((TARGET[0] - x) / w * 1200)
        py = int((TARGET[1] - y) / (w * 800 / 1200) * 800)     # pixels up from the bottom
    return px - box // 2, 800 - py - (box * 800 // 1200) // 2, box


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

    # -- layout: the selection boxes stack vertically and are wide
    QtWidgets.QApplication.processEvents()

    def pos(name):
        return g[name].mapTo(window, QtCore.QPoint(0, 0))
    ys = [pos(n).y() for n in ('xbox', 'ybox', 'wbox')]
    check('selection boxes stack top to bottom', ys == sorted(ys) and len(set(ys)) == 3, ys)
    xs = {pos(n).x() for n in ('xbox', 'ybox', 'wbox')}
    check('coordinate boxes line up in one column', len(xs) == 1, xs)
    fm = g['xbox'].fontMetrics()
    check('coordinate boxes are wide (room for 80+ digits)', g['xbox'].width() > fm.horizontalAdvance('0' * 80), g['xbox'].width())
    check('boxes do not run over the buttons', pos('xbox').x() + g['xbox'].width() <= g['run'].mapTo(window, QtCore.QPoint(0, 0)).x(),
          (pos('xbox').x() + g['xbox'].width(), g['run'].mapTo(window, QtCore.QPoint(0, 0)).x()))
    check('multiplier box shows 4-digit values', g['inter'].width() >= fm.horizontalAdvance('1000'), g['inter'].width())
    dial = g['iter_dial']
    check('there is an iteration dial, big enough to use, beside the image', dial.width() >= 80 and
          dial.mapTo(window, QtCore.QPoint(0, 0)).x() > g['reg'].mapTo(window, QtCore.QPoint(0, 0)).x() + 1100, dial.size())
    check('the dial has one notch per multiplier', dial.minimum() == 0 and dial.maximum() == g['inter'].count() - 1, (dial.minimum(), dial.maximum()))
    check('the readout shows the iteration limit', g['iter_label'].text() == '\u00d71 = 2,000 iterations', g['iter_label'].text())
    # turning the dial moves the multiplier box and the readout; the next render uses it
    dial.setValue(10)
    mult10 = g['MULTIPLIERS'][10]
    check('turning the dial sets the multiplier box', g['inter'].currentText() == str(mult10), g['inter'].currentText())
    check('turning the dial updates the readout', g['iter_label'].text() == '\u00d7%d = {:,} iterations'.format(2000 * mult10) % mult10, g['iter_label'].text())
    g['inter'].setCurrentText('1000')
    check('picking a multiplier in the box turns the dial', dial.value() == g['inter'].count() - 1, dial.value())
    check('the readout handles the largest value', g['iter_label'].text() == '\u00d71000 = 2,000,000 iterations', g['iter_label'].text())
    g['inter'].setCurrentIndex(0)
    check('the dial returns to the start', dial.value() == 0)
    check('window is at least as big as its layout needs', window.width() >= window.minimumSizeHint().width() and
          window.height() >= window.minimumSizeHint().height(), (window.size(), window.minimumSizeHint()))

    # -- the view starts on the full set
    check('starts at the reset view', (g['xbox'].text(), g['wbox'].text()) == ('-2.0', '4.0'),
          (g['xbox'].text(), g['wbox'].text()))

    # -- a selection becomes exact Decimal coordinates
    release(g, 300, 500, 600)
    x, w = Decimal(g['xbox'].text()), Decimal(g['wbox'].text())
    check('selection maps to exact coordinates', (x, w) == (Decimal('-1'), Decimal('2')), (x, w))
    check('reset constant is not mutated by selections', str(g['LOG_RESET'].w) == '4.0', g['LOG_RESET'].w)

    def image_ok(path):
        """The renderer's output loads as a full-size image with some structure (not blank)."""
        img = QtGui.QImage(path)
        if img.isNull() or (img.width(), img.height()) != (1200, 800):
            return False
        return len({img.pixel(px, py) for px in range(0, 1200, 37) for py in range(0, 800, 37)}) > 1

    # -- Run renders the selection and adds a history entry
    n_before = len(list(MAP))
    g['on_run']()
    check('history entry added', len(list(MAP)) == n_before + 1)
    check('rendered file exists', os.path.exists(MAP.curr.fname), MAP.curr.fname)
    if REAL:
        check('real renderer produced a proper image', image_ok(MAP.curr.fname), MAP.curr.fname)
    else:
        first = [c.split() for c in calls() if c.strip() and 'mandapp0.bmp' in c][0]    # (the start-up render comes before it)
        check('mand called with x y w file multiplier', len(first) >= 5 and Decimal(first[0]) == -1 and Decimal(first[2]) == 2, first)
        check('mand is told the colour settings and where to save the counts',
              '--palette=twilight' in first and '--mapping=histogram' in first and any(f.startswith('--nu-out=') for f in first), first)

    # -- the dial's choice reaches the renderer and is remembered with the view
    g['iter_dial'].setValue(5)
    mult5 = g['MULTIPLIERS'][5]
    release(g, 300, 500, 600)
    g['on_run']()
    entry = MAP.curr
    check('Run uses the dial setting (remembered with the view)', int(entry.xywd.d) == 5, entry.xywd.d)
    if not REAL:
        last_call = [c.split() for c in calls() if c.strip() and entry.fname in c][-1]
        check('the renderer is given the dial\'s multiplier', last_call[4] == str(mult5), last_call)
    g['iter_dial'].setValue(0)
    g['on_back']()
    check('going back to an earlier view restores its dial setting', g['iter_dial'].value() == int(MAP.curr.xywd.d), (g['iter_dial'].value(), MAP.curr.xywd.d))
    g['fset'](entry)
    check('picking that view again turns the dial to its setting', g['iter_dial'].value() == 5 and g['inter'].currentText() == str(mult5), g['iter_dial'].value())
    g['iter_dial'].setValue(0)

    # -- a renderer failure adds nothing
    release(g, 300, 500, 600)
    count = len(list(MAP))
    if REAL:
        pix_dir = os.path.join(tmp, 'pix')
        os.chmod(pix_dir, 0o555)          # the renderer cannot write its output
        try:
            g['on_run']()
        finally:
            os.chmod(pix_dir, 0o755)
    else:
        open(os.path.join(tmp, 'fail'), 'w').close()
        g['on_run']()
        os.remove(os.path.join(tmp, 'fail'))
    check('failed render adds no history entry', len(list(MAP)) == count)
    check('failed render tells the user', len(dialogs) == 1, dialogs)

    # -- a renderer that is missing must not crash the GUI
    release(g, 300, 500, 600)
    count = len(list(MAP))
    shown = len(dialogs)
    real_name = g['RENDERER']
    g['RENDERER'] = 'no-such-renderer'
    try:
        g['on_run']()
    finally:
        g['RENDERER'] = real_name
    check('missing renderer adds no history entry', len(list(MAP)) == count)
    check('missing renderer is reported, not a crash', len(dialogs) == shown + 1 and 'no-such-renderer' in str(dialogs[-1]), dialogs[-1:])

    # -- zoom until the view is deep enough to need a reference orbit
    g['on_reset']()
    deep = False
    for i in range(30):
        release(g, *aim(g))
        g['on_run']()
        if Decimal(g['wbox'].text()) < Decimal('1e-9'):
            deep = True
            break
    check('reached a deep view', deep, g['wbox'].text())
    if REAL:
        check('deep render produced a proper image', image_ok(MAP.curr.fname), MAP.curr.fname)
        leftovers = [f for f in os.listdir(os.path.join(tmp, 'pix')) if f.endswith('.ref')]
        check('no reference orbit files left behind', not leftovers, leftovers)
    else:
        last = calls()
        deep_call = [c for c in last if c.strip() and any(f.endswith('.ref') for f in c.split())]
        check('deep render passes a reference orbit file', len(deep_call) >= 1, last[-3:])
        check('reference orbit existed when mand ran', 'REF_EXISTED' in last)
        refs = [f for c in deep_call for f in c.split() if f.endswith('.ref')]
        check('reference orbit file is cleaned up afterwards', refs and not any(os.path.exists(r) for r in refs), refs)
    check('long values are readable in full from the tooltip', g['xbox'].toolTip() == g['xbox'].text() and len(g['xbox'].text()) > 20, g['xbox'].toolTip())
    check('coordinates keep their digits (not rounded through a float)',
          len(g['xbox'].text().replace('-', '').replace('.', '')) > 20, g['xbox'].text())
    check('the renderer setting is honoured', g['RENDERER'] == ('mand-cpu' if REAL else 'mand'), g['RENDERER'])

    # -- Back / thumbnails / Reset
    depth = len(list(MAP))
    g['on_back']()
    check('Back moves to the parent view', Decimal(g['wbox'].text()) > Decimal('1e-9'), g['wbox'].text())
    g['on_reset']()
    check('Reset returns to the full set', g['wbox'].text() == '4.0' and len(list(MAP)) == 1, g['wbox'].text())
    check('history was non-trivial before Reset', depth > 5, depth)

    # -- colour controls
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']
    names = {pal.itemText(i) for i in range(pal.count())}
    check('palette list offers the styles', {'twilight', 'fire', 'classic', 'rainbow'} <= names, names)
    check('default palette is twilight and mapping histogram', pal.currentText() == 'twilight' and mapping.currentText() == 'histogram')
    if not REAL:
        shown = len(dialogs)
        pal.setCurrentText('ice')                      # nothing saved to recolour: must be harmless
        check('recolouring with no saved counts is harmless', len(dialogs) == shown)
        pal.setCurrentText('twilight')
    else:
        import subprocess
        colorize = os.path.join(tmp, 'colorize')

        def make_expected(nu_file, *opts):
            out = os.path.join(tmp, 'expected%d.bmp' % len(os.listdir(tmp)))
            subprocess.run([colorize, nu_file, out, *opts], check=True, capture_output=True)
            return open(out, 'rb').read()

        def icon_pixels(item):
            img = item.icon.icon().pixmap(160, 120).toImage()
            return [img.pixel(x, y) for x in range(0, 160, 7) for y in range(0, 120, 7)]
        check('the opening view was drawn from saved counts', os.path.exists(os.path.join(tmp, 'pix', 'whole.bmp.nu'))
              and g['image_path'](g['INITPG']) != g['INITPG'].fname, g['image_path'](g['INITPG']))

        g['on_reset']()
        release(g, *aim(g))
        g['on_run']()
        item = MAP.curr
        nu_file = item.fname + '.nu'
        check('a render saves its smooth counts', os.path.exists(nu_file), nu_file)
        check('the render used the default palette', open(g['image_path'](item), 'rb').read() ==
              make_expected(nu_file, '--palette=twilight', '--mapping=histogram'))
        mtime, entries, icons = os.path.getmtime(nu_file), len(list(MAP)), icon_pixels(item)

        pal.setCurrentText('fire')
        shown_file = g['image_path'](item)
        check('choosing a palette recolours the view on screen', shown_file != item.fname and os.path.exists(shown_file), shown_file)
        check('the recoloured image is exactly what colorize makes from the saved counts',
              open(shown_file, 'rb').read() == make_expected(nu_file, '--palette=fire', '--mapping=histogram'))
        check('recolouring did not render again', os.path.getmtime(nu_file) == mtime and len(list(MAP)) == entries)
        check('the thumbnail was recoloured too', icon_pixels(item) != icons)
        check('the label shows the recoloured image', g['reg'].pixmap().toImage() == QtGui.QImage(shown_file))

        mapping.setCurrentText('linear')
        scale.setValue(40.0)
        shift.setValue(0.25)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--scale=40', '--shift=0.25')
        check('mapping, scale and shift all recolour', open(g['image_path'](item), 'rb').read() == want)
        scale.setValue(0.0)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--shift=0.25')
        check('a scale of 0 means the default', open(g['image_path'](item), 'rb').read() == want)

        # the settings also go to the next render
        release(g, *aim(g))
        g['on_run']()
        newer = MAP.curr
        check('new renders use the chosen colours', open(g['image_path'](newer), 'rb').read() ==
              make_expected(newer.fname + '.nu', '--palette=fire', '--mapping=linear', '--shift=0.25'))

        # Save writes what is on screen, recoloured
        pal.setCurrentText('ocean')
        saved = os.path.join(saves, 'recoloured.bmp')

        class SaveDlg(object):
            AnyFile = 0

            def __init__(self, *a):
                pass

            def setFileMode(self, *a):
                pass

            def exec_(self):
                return True

            def selectedFiles(self):
                return [saved]
        real_dialog = g['QFileDialog']
        g['QFileDialog'] = SaveDlg
        g['on_save']()
        g['QFileDialog'] = real_dialog
        check('Save writes the recoloured image', os.path.exists(saved) and open(saved, 'rb').read() == open(g['image_path'](newer), 'rb').read())

        # Reset forgets recolourings of the history, then a new render with the same file name shows fresh colours
        g['on_reset']()
        check('Reset clears per-view recolouring', list(g['SHOWN']) == [g['STARTFILE']] or list(g['SHOWN']) == [], list(g['SHOWN']))
        pal.setCurrentText('twilight')
        mapping.setCurrentText('histogram')
        shift.setValue(0.0)

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
    shown = len(dialogs)
    g['on_save']()
    check('failed save shows a warning dialog', len(dialogs) == shown + 1, dialogs)

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
