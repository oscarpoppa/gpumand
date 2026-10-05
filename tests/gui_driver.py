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


def exact(g, name):
    """The full-precision value behind a coordinate box (the box itself may show it abbreviated)."""
    return g[name].property('exact')


def release(g, x, y, w):
    """Simulate dragging a rubber band of width w with lower-left at image pixel (x, y from top); the picture
    may be drawn scaled and cropped, so the band is placed where those pixels appear on screen."""
    QtWidgets.QApplication.processEvents()
    h = int(w * 800 / 1200)
    left, top, scale = g['reg'].view()
    g['reg'].rubberBand.setGeometry(QtCore.QRect(left + round(x * scale), top + round(y * scale), round(w * scale), round(h * scale)))
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(x, y), QtCore.Qt.LeftButton,
                           QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    g['reg'].mouseReleaseEvent(ev)


# A point on the set's boundary: views centred on it keep showing structure at every depth.
TARGET = (Decimal('-0.743643887037158704752191506114774'), Decimal('0.131825904205311970493132056385139'))


def aim(g, box=120):
    """Rubber-band (left, top, width) of a box centred on TARGET in the current view."""
    x, y, w = (Decimal(exact(g, n)) for n in ('xbox', 'ybox', 'wbox'))
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
    # Reset and quitting offer to delete files; flows below that reset freely keep them, unless a test says otherwise
    real_ask = g['ask_cleanup']
    g['ask_cleanup'] = lambda parent, count, size, reset=False: 'keep'
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
    run_pos = g['run'].mapTo(window, QtCore.QPoint(0, 0))
    check('the buttons sit under the coordinate boxes', run_pos.y() > pos('wbox').y(), (run_pos, pos('wbox')))
    ip = g['reg'].mapTo(window, QtCore.QPoint(0, 0))
    row = [g[n].mapTo(window, QtCore.QPoint(0, 0)) for n in ('run', 'back', 'save', 'reset')]
    check('Run, Back, Save and Reset are in one row in that order', len({p.y() for p in row}) == 1 and
          [p.x() for p in row] == sorted(p.x() for p in row), row)
    check('the buttons are small and fit the column', all(g[n].width() < 80 for n in ('reset', 'run', 'back', 'save')) and
          row[3].x() + g['reset'].width() <= pos('xbox').x() + g['xbox'].width() + 2, [g[n].width() for n in ('reset', 'run', 'back', 'save')])
    check('the picture has the whole window height', g['reg'].height() >= window.height() - 20, (g['reg'].height(), window.height()))
    side_x = g['side'].mapTo(window, QtCore.QPoint(0, 0)).x()
    check('all the controls are in one column right of the picture', ip.x() + g['reg'].width() <= side_x and
          all(pos(n).x() >= side_x for n in ('xbox', 'run', 'back', 'save', 'iter_dial', 'pal_box')), side_x)
    fm = g['xbox'].fontMetrics()
    check('multiplier box shows 8-digit values', g['inter'].width() >= fm.horizontalAdvance('20000000'), g['inter'].width())
    dial = g['iter_dial']
    check('there is an iteration dial, big enough to use, beside the image', dial.width() >= 80 and
          dial.mapTo(window, QtCore.QPoint(0, 0)).x() > g['reg'].mapTo(window, QtCore.QPoint(0, 0)).x() + g['reg'].width() - 1, dial.size())
    check('the dial has one notch per multiplier', dial.minimum() == 0 and dial.maximum() == g['inter'].count() - 1, (dial.minimum(), dial.maximum()))
    check('the readout shows the iteration limit', g['iter_label'].text() == '\u00d71 = 2,000 iterations', g['iter_label'].text())
    # turning the dial moves the multiplier box and the readout; the next render uses it
    dial.setValue(10)
    mult10 = g['MULTIPLIERS'][10]
    check('turning the dial sets the multiplier box', g['inter'].currentText() == str(mult10), g['inter'].currentText())
    check('turning the dial updates the readout', g['iter_label'].text() == '\u00d7%d = {:,} iterations'.format(2000 * mult10) % mult10, g['iter_label'].text())
    g['inter'].setCurrentText('20000000')
    check('picking a multiplier in the box turns the dial', dial.value() == g['inter'].count() - 1, dial.value())
    check('the readout handles the largest value', g['iter_label'].text() == '\u00d720000000 = 40,000,000,000 iterations', g['iter_label'].text())
    check('the multipliers go up to 20 million, in increasing order', g['MULTIPLIERS'][-1] == 20000000 and g['MULTIPLIERS'] == sorted(set(g['MULTIPLIERS'])))
    g['inter'].setCurrentIndex(0)
    check('the dial returns to the start', dial.value() == 0)
    check('window is at least as big as its layout needs', window.width() >= window.minimumSizeHint().width() and
          window.height() >= window.minimumSizeHint().height(), (window.size(), window.minimumSizeHint()))

    # -- the view starts on the full set
    check('starts at the reset view', (exact(g, 'xbox'), exact(g, 'wbox')) == ('-2.75', '4.0'),
          (exact(g, 'xbox'), exact(g, 'wbox')))

    # -- a selection becomes exact Decimal coordinates
    release(g, 300, 500, 600)
    x, w = Decimal(exact(g, 'xbox')), Decimal(exact(g, 'wbox'))
    check('selection maps to exact coordinates', (x, w) == (Decimal('-1.75'), Decimal('2')), (x, w))
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
        check('mand called with x y w file multiplier', len(first) >= 5 and Decimal(first[0]) == Decimal('-1.75') and Decimal(first[2]) == 2, first)
        check('mand is told the color settings and where to save the counts',
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
        if Decimal(exact(g, 'wbox')) < Decimal('1e-9'):
            deep = True
            break
    check('reached a deep view', deep, exact(g, 'wbox'))
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
    xfull, wfull = exact(g, 'xbox'), exact(g, 'wbox')
    if not REAL:
        check('the render was given the full digits, not the short form',
              xfull in deep_call[-1].split() and wfull in deep_call[-1].split(), (xfull, wfull, deep_call[-1:]))
    check('long values are readable in full from the tooltip', g['xbox'].toolTip() == xfull and len(xfull) > 20, g['xbox'].toolTip())
    check('coordinates keep their digits (not rounded through a float)', len(xfull.replace('-', '').replace('.', '')) > 20, xfull)
    # the boxes show a short form that still tells the scale: leading digits, an ellipsis, trailing digits, power of ten
    fm = g['xbox'].fontMetrics()
    for name in ('xbox', 'ybox', 'wbox'):
        shown, full = g[name].text(), exact(g, name)
        check('%s shows an abbreviated form when long' % name, ('\u2026' in shown and len(shown) < len(full)) or shown == full.lower(), (shown, full))
        check('%s abbreviation fits in its box' % name, fm.horizontalAdvance(shown) < g[name].width() - 16, (shown, g[name].width()))
    wshown = g['wbox'].text()
    check('the width shows its power of ten', wshown.rsplit('e', 1)[-1].lstrip('+-').isdigit() and
          int(wshown.rsplit('e', 1)[-1]) == Decimal(wfull).adjusted(), (wshown, wfull))
    check('a long coordinate really is abbreviated in its box', '\u2026' in g['xbox'].text(), g['xbox'].text())
    check('the renderer setting is honoured', g['RENDERER'] == ('mand-cpu' if REAL else 'mand'), g['RENDERER'])

    # -- Back / thumbnails / Reset
    depth = len(list(MAP))
    g['on_back']()
    check('Back moves to the parent view', Decimal(exact(g, 'wbox')) > Decimal('1e-9'), exact(g, 'wbox'))
    g['on_reset']()
    check('Reset returns to the full set', exact(g, 'wbox') == '4.0' and len(list(MAP)) == 1, exact(g, 'wbox'))
    check('history was non-trivial before Reset', depth > 5, depth)

    # -- color controls
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']
    names = {pal.itemText(i) for i in range(pal.count())}
    check('palette list offers the styles', {'twilight', 'fire', 'classic', 'rainbow'} <= names, names)
    check('default palette is twilight and mapping histogram', pal.currentText() == 'twilight' and mapping.currentText() == 'histogram')
    if not REAL:
        shown = len(dialogs)
        pal.setCurrentText('ice')                      # nothing saved to recolor: must be harmless
        check('recoloring with no saved counts is harmless', len(dialogs) == shown)
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
        check('choosing a palette recolors the view on screen', shown_file != item.fname and os.path.exists(shown_file), shown_file)
        check('the recolored image is exactly what colorize makes from the saved counts',
              open(shown_file, 'rb').read() == make_expected(nu_file, '--palette=fire', '--mapping=histogram'))
        check('recoloring did not render again', os.path.getmtime(nu_file) == mtime and len(list(MAP)) == entries)
        check('the thumbnail was recolored too', icon_pixels(item) != icons)
        check('the label shows the recolored image', g['reg'].source.toImage() == QtGui.QImage(shown_file))

        mapping.setCurrentText('linear')
        scale.setValue(40.0)
        shift.setValue(0.25)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--scale=40', '--shift=0.25')
        check('mapping, scale and shift all recolor', open(g['image_path'](item), 'rb').read() == want)
        scale.setValue(0.0)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--shift=0.25')
        check('a scale of 0 means the default', open(g['image_path'](item), 'rb').read() == want)

        # the settings also go to the next render
        release(g, *aim(g))
        g['on_run']()
        newer = MAP.curr
        check('new renders use the chosen colors', open(g['image_path'](newer), 'rb').read() ==
              make_expected(newer.fname + '.nu', '--palette=fire', '--mapping=linear', '--shift=0.25'))

        # Save writes what is on screen, recolored
        pal.setCurrentText('ocean')
        saved = os.path.join(saves, 'recolored.bmp')

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
        check('Save writes the recolored image', os.path.exists(saved) and open(saved, 'rb').read() == open(g['image_path'](newer), 'rb').read())

        # Reset forgets recolorings of the history, then a new render with the same file name shows fresh colors
        g['on_reset']()
        check('Reset clears per-view recoloring', list(g['SHOWN']) == [g['STARTFILE']] or list(g['SHOWN']) == [], list(g['SHOWN']))
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

    # -- the image grows with the window, never stretched (a little may be cropped), and selections map to image pixels
    reg = g['reg']
    MAXC = g['MAX_CROP']
    check('image is centred in its label', bool(reg.alignment() & QtCore.Qt.AlignCenter) == True, int(reg.alignment()))
    pm = QtGui.QPixmap(1200, 800)
    pm.fill(QtGui.QColor('red'))
    lab = type(reg)()
    lab.setPixmap(pm)
    lab.show()
    settle = QtWidgets.QApplication.processEvents

    def shown(w, h):
        lab.resize(w, h)
        settle()
        return lab.view() + (lab.pixmap().width(), lab.pixmap().height())

    left, top, scale, pw, ph = shown(1200, 800)
    check('at its own size the image is drawn 1:1', (left, top, scale, pw, ph) == (0, 0, 1.0, 1200, 800), (left, top, scale, pw, ph))
    left, top, scale, pw, ph = shown(1800, 1200)        # the same shape, bigger: scales up evenly
    check('a bigger label of the same shape scales the image up evenly', (left, top, scale, pw, ph) == (0, 0, 1.5, 1800, 1200),
          (left, top, scale, pw, ph))
    left, top, scale, pw, ph = shown(1620, 1000)        # wider than 3:2: a little (80 of 1080 px) is cropped off top and bottom
    check('a wider label crops the top and bottom a little, not stretching',
          pw == 1620 and ph == 1000 and abs(scale - 1.35) < 0.01 and top == -40 and scale * 800 - ph <= MAXC * scale * 800 + 1,
          (left, top, scale, pw, ph))
    check('the crop is symmetric', abs(top + (round(800 * scale) - ph) // 2) <= 1 and left == 0, (left, top))
    left, top, scale, pw, ph = shown(3000, 1000)        # far wider: crop limited, so there are side margins
    check('the crop is limited', abs(scale * 800 * (1 - MAXC) - 1000) < 1.5 and ph == 1000 and pw == round(1200 * scale) and left == (3000 - pw) // 2,
          (left, top, scale, pw, ph))
    left, top, scale, pw, ph = shown(600, 1200)         # far taller: whole width fits, margins above and below
    check('a tall label crops the sides only as far as allowed',
          abs(scale * 1200 * (1 - MAXC) - 600) < 1.5 and pw == 600 and left < 0, (left, top, scale, pw, ph))
    left, top, scale, pw, ph = shown(3000, 1000)
    img = lab.grab().toImage()
    red = lambda x, y: QtGui.QColor(img.pixel(x, y)).name() == '#ff0000'
    check('the picture is drawn centred in the label', red(left + 5, 5) and red(left + pw - 5, 995) and not red(left - 5, 500) and not red(left + pw + 5, 500))
    # the selection box keeps the image's own shape
    ev = lambda kind, x, y: QtGui.QMouseEvent(kind, QtCore.QPointF(x, y), QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    lab.mousePressEvent(ev(QtCore.QEvent.MouseButtonPress, left + 100, 100))
    lab.mouseMoveEvent(ev(QtCore.QEvent.MouseMove, left + 100 + 400, 300))
    band = lab.rubberBand.geometry()
    check('the selection box has the image\'s shape', abs(band.width() / band.height() - 1.5) < 0.02, (band.width(), band.height()))
    # in the real window, with a shape that crops: a band must choose the region it covers
    window.resize(window.size() + QtCore.QSize(600, 400))
    settle()
    left, top, scale = g['reg'].view()
    check('enlarging the window enlarges the picture', scale > 1.2, scale)
    check('the real window gives the image most of its width', g['reg'].width() > window.width() // 2, (g['reg'].width(), window.width()))
    g['reg'].rubberBand.setGeometry(QtCore.QRect(left + round(300 * scale), top + round(500 * scale), round(600 * scale), round(400 * scale)))
    g['reg'].mouseReleaseEvent(ev(QtCore.QEvent.MouseButtonRelease, 0, 0))
    check('a selection on the enlarged picture maps to the right region',
          abs(Decimal(exact(g, 'xbox')) - Decimal('-1.75')) < Decimal('0.01') and abs(Decimal(exact(g, 'wbox')) - 2) < Decimal('0.01'),
          (exact(g, 'xbox'), exact(g, 'wbox')))
    check('the controls column does not grow with the window',
          g['color_group'].width() < 500, g['color_group'].width())

    # -- Enter presses Run
    from PyQt5 import QtTest
    g['on_reset']()
    release(g, 300, 500, 600)
    window.activateWindow()
    QtWidgets.QApplication.processEvents()
    before = len(list(MAP))
    QtTest.QTest.keyClick(window, QtCore.Qt.Key_Return)
    check('the Return key runs the selection', len(list(MAP)) == before + 1, (before, len(list(MAP))))
    release(g, 100, 100, 400)
    before = len(list(MAP))
    QtTest.QTest.keyClick(window, QtCore.Qt.Key_Enter)
    check('the keypad Enter key runs it too', len(list(MAP)) == before + 1, (before, len(list(MAP))))
    check('the Run button says so', 'Enter' in g['run'].toolTip(), g['run'].toolTip())
    check('holding Enter does not repeat the run', len(g['run_keys']) == 2 and all(not k.autoRepeat() for k in g['run_keys']))

    # -- Reset offers to delete the files of the views it throws away (but keeps the opening view's)
    pix_dir = g['PIX_DIR']
    g['on_reset']()
    for _ in range(2):
        release(g, 300, 500, 600)
        g['on_run']()
    g['on_color_change']()
    opening = [os.path.join(pix_dir, n) for n in ('whole-start.bmp', 'whole.bmp.nu')]
    opening = [f for f in opening if os.path.exists(f)]
    old = [f for f in g['generated_files'](pix_dir, opening=False)]
    check('there are old views to clean', len(old) >= 4 and not any(os.path.basename(f).startswith('whole') for f in old), len(old))
    depth = len(list(MAP))
    asked = []

    def answer_reset(choice):
        def fake(parent, count, size, reset=False):
            asked.append((count, size, reset))
            return choice
        g['ask_cleanup'] = fake

    answer_reset('cancel')
    g['on_reset']()
    check('Cancel leaves the history and every file alone', len(list(MAP)) == depth and all(os.path.exists(f) for f in old),
          (depth, len(list(MAP))))
    check('the reset prompt says it is a reset and counts only old views', asked and asked[-1][2] is True and asked[-1][0] == len(old), asked)
    answer_reset('keep')
    g['on_reset']()
    check('Keep all resets but deletes nothing', len(list(MAP)) == 1 and all(os.path.exists(f) for f in old))
    for _ in range(2):
        release(g, 300, 500, 600)
        g['on_run']()
    old = g['generated_files'](pix_dir, opening=False)
    answer_reset('delete')
    g['on_reset']()
    check('Delete all resets and removes the old views', len(list(MAP)) == 1 and not any(os.path.exists(f) for f in old),
          [f for f in old if os.path.exists(f)])
    check('the opening view\'s files and whole.bmp survive a reset', all(os.path.exists(f) for f in opening + [os.path.join(pix_dir, 'whole.bmp')]))
    g['pal_box'].setCurrentText('fire')
    check('the opening view can still be recolored after a reset', g['reg'].source.toImage() == QtGui.QImage(g['image_path'](MAP.curr)))
    g['pal_box'].setCurrentText('twilight')
    asked.clear()
    g['on_reset']()
    check('with nothing old to delete a reset does not ask', not asked, asked)
    g['ask_cleanup'] = lambda parent, count, size, reset=False: 'keep'

    # -- quitting: the user decides what to do with the generated files (never saved copies, never whole.bmp)
    pix_dir = g['PIX_DIR']
    for _ in range(3):         # (the reset tests above cleaned up, so draw some views to clean again)
        release(g, 300, 500, 600)
        g['on_run']()
    g['on_color_change']()
    guard = [os.path.join(pix_dir, n) for n in ('keepme.bmp', 'mandapp9x.bmp', 'whole.bmp')]
    for path in guard:
        if not os.path.exists(path):
            open(path, 'wb').write(b'precious')
    saved_copy = os.path.join(saves, 'saved-by-me.bmp')
    open(saved_copy, 'wb').write(b'precious')
    old_ref = os.path.join(pix_dir, 'mandapp77.bmp.ref')
    open(old_ref, 'wb').write(b'stale')
    os.utime(old_ref, (1, 1))
    gen = [f for f in g['generated_files'](pix_dir) if f != old_ref]
    check('there are generated files to offer', len(gen) >= 3, len(gen))
    asked = []

    def answer(choice):
        def fake(parent, count, size, reset=False):
            asked.append((count, size, reset))
            return choice
        g['ask_cleanup'] = fake

    answer('cancel')
    check('Cancel keeps the window open', window.close() is False and window.isVisible())
    check('Cancel deletes nothing', all(os.path.exists(f) for f in gen))
    check('the quit prompt reports the count and size', asked and asked[-1][0] == len(gen) and asked[-1][2] is False and asked[-1][1] > 0, (asked, len(gen)))
    check('stale reference orbits are swept before asking', not os.path.exists(old_ref))
    answer('keep')
    check('Keep all closes the window', window.close() is True and not window.isVisible())
    check('Keep all deletes nothing', all(os.path.exists(f) for f in gen))
    window.show()
    answer('delete')
    check('Delete all closes the window', window.close() is True and not window.isVisible())
    check('Delete all removes every generated file', not g['generated_files'](pix_dir) and not any(os.path.exists(f) for f in gen),
          [f for f in gen if os.path.exists(f)])
    check('saved copies, whole.bmp and unrelated files survive', all(os.path.exists(f) for f in guard + [saved_copy]),
          [f for f in guard + [saved_copy] if not os.path.exists(f)])
    window.show()
    asked.clear()
    check('with nothing to delete there is no prompt', window.close() is True and not asked, asked)

    # -- the real dialog: its three buttons give the three answers
    g['ask_cleanup'] = real_ask
    window.show()
    for label, want in (('Keep all', 'keep'), ('Delete all', 'delete'), ('Cancel', 'cancel')):
        def click(label=label):
            box = QtWidgets.QApplication.activeModalWidget()
            [b for b in box.buttons() if b.text() == label][0].click()
        QtCore.QTimer.singleShot(300, click)
        got = real_ask(window, 3, 5 << 20)
        check('the %s button answers %r' % (label, want), got == want, got)
    box_text = []
    QtCore.QTimer.singleShot(300, lambda: (box_text.append(QtWidgets.QApplication.activeModalWidget().text()),
                                           QtWidgets.QApplication.activeModalWidget().reject()))
    check('Escape or closing the dialog cancels', real_ask(window, 3, 5 << 20) == 'cancel')
    check('the dialog states the count and size', '3 generated files' in box_text[0] and '5.0 MB' in box_text[0], box_text)
    return 0


QtWidgets.QApplication.exec_ = lambda self: drive()
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
except SystemExit as e:
    pass
sys.exit(1 if failures else 0)
