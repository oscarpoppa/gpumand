"""Drives the real mand-gui.py under an offscreen Qt platform, against a fake `mand-gpu` binary.

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
log = os.path.join(tmp, 'mand-gpu.log')
fake = os.path.join(tmp, 'mand-cpu' if REAL else 'mand-gpu')
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
if [ -f "%s/slow" ]; then echo $$ > "%s/slow.pid"; exec sleep 60; fi
cp "%s/pix/whole.bmp" "$4"
for a in "$@"; do case "$a" in --nu-out=*) echo counts > "${a#--nu-out=}";; esac; done
''' % (log, log, tmp, tmp, tmp, tmp))
if not REAL:
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
ini = os.path.join(tmp, 'test.ini')
with open(ini, 'w') as fp:
    fp.write('[paths]\nsave_dir=%s\nbin_dir=%s\n' % (saves, tmp))
    # a trailing comment on a setting line must not become part of the value
    fp.write('renderer=%s   ; which program draws the images\n' % ('mand-cpu' if REAL else 'mand-gpu'))

sys.path.insert(0, ROOT)
from meta import parse_view, read_png_text, view_text      # noqa: E402
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


def same_pixels(a, b):
    """Two images show the same picture (whatever file format they were read from)."""
    a, b = a.convertToFormat(QtGui.QImage.Format_RGB32), b.convertToFormat(QtGui.QImage.Format_RGB32)
    return not a.isNull() and a == b


def dialog_returning(path):
    """A stand-in for QFileDialog that picks `path` without showing anything."""
    class Dlg(object):
        AnyFile, ExistingFile = 0, 1

        def __init__(self, *a):
            pass

        def setFileMode(self, *a):
            pass

        def exec_(self):
            return True

        def selectedFiles(self):
            return [path]
    return Dlg


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


# A point on the set's boundary: views centered on it keep showing structure at every depth.
TARGET = (Decimal('-0.743643887037158704752191506114774'), Decimal('0.131825904205311970493132056385139'))


def aim(g, box=120):
    """Rubber-band (left, top, width) of a box centered on TARGET in the current view."""
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
    g['ask_keep_folder'] = lambda parent: g['PIX_DIR']      # (choosing pix/ itself leaves the files where they are)
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
    check('the buttons sit above the coordinate boxes, where they stay in view whichever part of the column is open',
          run_pos.y() < pos('xbox').y(), (run_pos, pos('xbox')))
    ip = g['reg'].mapTo(window, QtCore.QPoint(0, 0))
    row = [g[n].mapTo(window, QtCore.QPoint(0, 0)) for n in ('run', 'back', 'save', 'reset')]
    check('Run, Back, Save and Reset are in one row in that order', len({p.y() for p in row}) == 1 and
          [p.x() for p in row] == sorted(p.x() for p in row), row)
    check('the buttons are small and fit the column', all(g[n].width() < 80 for n in ('reset', 'run', 'back', 'save')) and
          row[3].x() + g['reset'].width() <= g['side'].mapTo(window, QtCore.QPoint(0, 0)).x() + g['side'].width() + 2,
          [g[n].width() for n in ('reset', 'run', 'back', 'save')])
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
        check('mand-gpu called with x y w file multiplier', len(first) >= 5 and Decimal(first[0]) == Decimal('-1.75') and Decimal(first[2]) == 2, first)
        check('mand-gpu is told the color settings and where to save the counts',
              '--palette=gray' in first and '--mapping=histogram' in first and any(f.startswith('--nu-out=') for f in first), first)

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
        check('reference orbit existed when mand-gpu ran', 'REF_EXISTED' in last)
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
    check('an older ini saying renderer=mand is read as mand-gpu', g['resolve_renderer']('mand') == 'mand-gpu' and
          g['resolve_renderer']('mand-gpu') == 'mand-gpu' and g['resolve_renderer']('mand-cpu') == 'mand-cpu' and
          g['resolve_renderer']('something-else') == 'something-else')
    check('the renderer setting is honored', g['RENDERER'] == ('mand-cpu' if REAL else 'mand-gpu'), g['RENDERER'])

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
    check('default palette is gray and mapping histogram', pal.currentText() == 'gray' and mapping.currentText() == 'histogram')
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
              make_expected(nu_file, '--palette=gray', '--mapping=histogram'))
        mtime, entries, icons = os.path.getmtime(nu_file), len(list(MAP)), icon_pixels(item)

        pix = os.path.join(tmp, 'pix')
        files_before = sorted(os.listdir(pix))
        pal.setCurrentText('fire')
        shown_file = g['image_path'](item)
        check('choosing a palette replaces the view\'s own image file', shown_file == item.fname and os.path.exists(shown_file), shown_file)
        check('recoloring leaves no extra files', sorted(os.listdir(pix)) == files_before, set(os.listdir(pix)) ^ set(files_before))
        check('the recolored image is exactly what colorize makes from the saved counts',
              open(shown_file, 'rb').read() == make_expected(nu_file, '--palette=fire', '--mapping=histogram'))
        check('recoloring did not render again', os.path.getmtime(nu_file) == mtime and len(list(MAP)) == entries)
        check('the thumbnail was recolored too', icon_pixels(item) != icons)
        check('the label shows the recolored image', g['reg'].source.toImage() == QtGui.QImage(shown_file))
        for name, value in (('pal', 'ocean'), ('pal', 'ice'), ('pal', 'fire'), ('pal', 'ocean')):     # many quick changes
            pal.setCurrentText(value)
            check('recoloring to %s shows the new image at once' % value,
                  g['reg'].source.toImage() == QtGui.QImage(item.fname) and
                  open(item.fname, 'rb').read() == make_expected(nu_file, '--palette=%s' % value, '--mapping=histogram'))
        check('a dozen recolorings still leave no extra files', sorted(os.listdir(pix)) == files_before, set(os.listdir(pix)) ^ set(files_before))
        pal.setCurrentText('fire')

        mapping.setCurrentText('linear')
        scale.setValue(40.0)
        shift.setValue(0.25)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--scale=40', '--shift=0.25')
        check('mapping, scale and shift all recolor', open(g['image_path'](item), 'rb').read() == want)
        scale.setValue(0.0)
        want = make_expected(nu_file, '--palette=fire', '--mapping=linear', '--shift=0.25')
        check('a scale of 0 means the default', open(g['image_path'](item), 'rb').read() == want)

        # Each Restore button puts its own box back and recolors once, leaving the other settings alone
        mapping.setCurrentText('linear')
        pal.setCurrentText('ocean')
        scale.setValue(40.0)
        shift.setValue(0.25)
        recolors = []
        real_recolor = g['recolor']
        g['recolor'] = lambda it: (recolors.append(it.fname), real_recolor(it))[1]
        g['restore_scale_btn'].click()
        check('Restore beside Scale sets it back to its default and leaves Shift alone',
              scale.value() == 0.0 and scale.text() == 'default' and shift.value() == 0.25, (scale.value(), scale.text(), shift.value()))
        check('Restore beside Scale recolors once, with the other settings kept', recolors == [item.fname] and
              open(g['image_path'](item), 'rb').read() == make_expected(nu_file, '--palette=ocean', '--mapping=linear', '--shift=0.25'), recolors)
        del recolors[:]
        scale.setValue(40.0)
        del recolors[:]
        g['restore_shift_btn'].click()
        check('Restore beside Shift sets it to 0 and leaves Scale alone', shift.value() == 0.0 and scale.value() == 40.0, (shift.value(), scale.value()))
        check('Restore beside Shift recolors once, with the other settings kept', recolors == [item.fname] and
              open(g['image_path'](item), 'rb').read() == make_expected(nu_file, '--palette=ocean', '--mapping=linear', '--scale=40'), recolors)
        g['recolor'] = real_recolor
        check('Restore leaves the palette and mapping alone', (pal.currentText(), mapping.currentText()) == ('ocean', 'linear'))
        pal.setCurrentText('fire')                  # (back to the settings the next check expects)
        mapping.setCurrentText('linear')
        scale.setValue(0.0)
        shift.setValue(0.25)

        # the settings also go to the next render
        release(g, *aim(g))
        g['on_run']()
        newer = MAP.curr
        check('new renders use the chosen colors', open(g['image_path'](newer), 'rb').read() ==
              make_expected(newer.fname + '.nu', '--palette=fire', '--mapping=linear', '--shift=0.25'))

        # Save writes what is on screen, recolored
        pal.setCurrentText('ocean')
        saved = os.path.join(saves, 'recolored.png')

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
        check('Save writes the recolored image as a PNG', os.path.exists(saved) and same_pixels(QtGui.QImage(saved), QtGui.QImage(g['image_path'](newer))))

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
    check('image is centered in its label', bool(reg.alignment() & QtCore.Qt.AlignCenter) == True, int(reg.alignment()))
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
    check('the picture is drawn centered in the label', red(left + 5, 5) and red(left + pw - 5, 995) and not red(left - 5, 500) and not red(left + pw + 5, 500))
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

    # -- changing the iterations and pressing Run again redraws the same view in place
    pix = os.path.join(tmp, 'pix')
    g['on_reset']()
    release(g, 300, 500, 600)
    g['on_run']()
    view = MAP.curr
    nu_file = view.fname + '.nu'
    names_before, entries = sorted(os.listdir(pix)), len(list(MAP))
    for f in (view.fname, nu_file):
        os.utime(f, (1, 1))
    g['inter'].setCurrentIndex(2)                       # multiplier 3
    g['on_run']()
    check('Run on an unchanged region adds no history entry', len(list(MAP)) == entries and MAP.curr.fname == view.fname,
          (entries, len(list(MAP))))
    check('redrawing in place leaves no extra files', sorted(os.listdir(pix)) == names_before, set(os.listdir(pix)) ^ set(names_before))
    check('the image and its counts were replaced', os.path.getmtime(view.fname) > 1000 and os.path.getmtime(nu_file) > 1000)
    check('the new multiplier is remembered for the view', MAP.curr.xywd.d == 2 and g['inter'].currentIndex() == 2, MAP.curr.xywd)
    check('the view is the same region', Decimal(MAP.curr.xywd.w) == Decimal(view.xywd.w) and Decimal(MAP.curr.xywd.x) == Decimal(view.xywd.x))
    if REAL:
        check('the redrawn image is a proper image', image_ok(g['image_path'](MAP.curr)), g['image_path'](MAP.curr))
    else:
        call_line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('the renderer drew the new limit to a temporary name', call_line[4] == '3' and call_line[3] == view.fname + '.new', call_line)
    check('the label shows the redrawn view', g['reg'].source.toImage() == QtGui.QImage(g['image_path'](MAP.curr)))
    # a failed redraw leaves the old image and counts alone
    before_bytes = (open(view.fname, 'rb').read(), open(nu_file, 'rb').read())
    open(os.path.join(tmp, 'fail'), 'w').close()
    warned = len(dialogs)
    g['inter'].setCurrentIndex(4)
    if REAL:
        g['RENDERER'], saved_renderer = 'no-such-renderer', g['RENDERER']
    g['on_run']()
    if REAL:
        g['RENDERER'] = saved_renderer
    os.remove(os.path.join(tmp, 'fail'))
    check('a failed redraw is reported', len(dialogs) == warned + 1, dialogs[-1:])
    check('a failed redraw keeps the old files and leaves no temporary ones',
          (open(view.fname, 'rb').read(), open(nu_file, 'rb').read()) == before_bytes and sorted(os.listdir(pix)) == names_before,
          set(os.listdir(pix)) ^ set(names_before))
    check('a failed redraw keeps the view\'s old multiplier', MAP.curr.xywd.d == 2, MAP.curr.xywd)
    # the opening view redraws into a copy: the shipped whole.bmp is never overwritten
    g['on_reset']()
    shipped = open(os.path.join(pix, 'whole.bmp'), 'rb').read()
    start_copy, start_nu = g['START_COPY'], os.path.join(pix, 'whole.bmp.nu')
    for f in (start_copy, start_nu):
        if os.path.exists(f):
            os.utime(f, (1, 1))
    g['inter'].setCurrentIndex(1)
    g['on_run']()
    check('redrawing the opening view adds no history entry', len(list(MAP)) == 1 and MAP.curr.fname == g['STARTFILE'], len(list(MAP)))
    check('the shipped whole.bmp is untouched', open(os.path.join(pix, 'whole.bmp'), 'rb').read() == shipped)
    check('the opening view\'s copy and counts were replaced', os.path.getmtime(start_copy) > 1000 and os.path.getmtime(start_nu) > 1000)
    check('the opening view remembers the new multiplier', MAP.curr.xywd.d == 1 and g['INITPG'].xywd.d == 1, MAP.curr.xywd)
    g['inter'].setCurrentIndex(0)
    g['on_reset']()

    # -- Save writes a PNG that remembers the view; Open draws it again
    g['scale_box'].setValue(12.5)
    g['shift_box'].setValue(-0.4)
    g['restore_scale_btn'].click()
    check('the Restore button beside Scale puts only Scale back', g['scale_box'].value() == 0.0 and g['shift_box'].value() == -0.4,
          (g['scale_box'].value(), g['shift_box'].value()))
    g['scale_box'].setValue(12.5)
    g['restore_shift_btn'].click()
    check('the Restore button beside Shift puts only Shift back', g['shift_box'].value() == 0.0 and g['scale_box'].value() == 12.5,
          (g['scale_box'].value(), g['shift_box'].value()))
    pos_row = lambda name: g[name].mapTo(window, QtCore.QPoint(0, 0))
    check('each Restore button sits on the same row as its box, to the right of it',
          abs(pos_row('restore_scale_btn').y() + g['restore_scale_btn'].height() // 2 - pos_row('scale_box').y() - g['scale_box'].height() // 2) <= 3 and
          abs(pos_row('restore_shift_btn').y() + g['restore_shift_btn'].height() // 2 - pos_row('shift_box').y() - g['shift_box'].height() // 2) <= 3 and
          pos_row('restore_scale_btn').x() >= pos_row('scale_box').x() + g['scale_box'].width() - 2 and
          pos_row('restore_shift_btn').x() >= pos_row('shift_box').x() + g['shift_box'].width() - 2 and
          g['restore_scale_btn'].parent() is g['color_group'] and g['restore_shift_btn'].parent() is g['color_group'],
          (pos_row('restore_scale_btn'), pos_row('scale_box')))
    g['restore_scale_btn'].click()
    g['restore_shift_btn'].click()
    check('Restore when already at the defaults is harmless', g['scale_box'].value() == 0.0 and g['shift_box'].value() == 0.0)
    # Scale's arrows step finely, by an amount that suits the mapping
    sbox, mbox = g['scale_box'], g['map_box']
    for name, start, step in (('histogram', 2.5, 0.05), ('linear', 50.0, 0.5), ('log', 0.6, 0.01)):
        mbox.setCurrentText(name)
        check('Scale steps by %g for the %s mapping' % (step, name), abs(sbox.singleStep() - step) < 1e-12, sbox.singleStep())
        sbox.setValue(0.0)
        sbox.stepUp()
        check('the first up-click from "default" goes one step above the %s default' % name, abs(sbox.value() - (start + step)) < 1e-9, sbox.value())
        sbox.setValue(0.0)
        sbox.stepDown()
        check('the first down-click from "default" goes one step below the %s default' % name, abs(sbox.value() - (start - step)) < 1e-9, sbox.value())
        sbox.stepUp()
        sbox.stepUp()
        check('later clicks move by one step each', abs(sbox.value() - (start + step)) < 1e-9, sbox.value())
        sbox.stepBy(10)
        check('Page Up moves ten steps', abs(sbox.value() - (start + 11 * step)) < 1e-9, sbox.value())
    sbox.setValue(0.0)
    mbox.setCurrentText('histogram')
    sbox.setValue(2.555)
    check('Scale keeps three decimals', abs(sbox.value() - 2.555) < 1e-9 and sbox.text() == '2.555', (sbox.value(), sbox.text()))
    sbox.setValue(0.05)
    sbox.stepDown()
    check('stepping down to zero shows "default" again', sbox.value() == 0.0 and sbox.text() == 'default', (sbox.value(), sbox.text()))
    # showing another view brings that view's mapping, and with it the right step
    g['set_color_controls']('fire', 'linear', 0.0, 0.0)
    check('showing a view with another mapping changes the step to suit it', abs(sbox.singleStep() - 0.5) < 1e-12, sbox.singleStep())
    g['set_color_controls']('twilight', 'histogram', 0.0, 0.0)
    sbox.setValue(0.0)
    saved_png = os.path.join(saves, 'view.png')
    g['on_reset']()
    release(g, 300, 500, 600)
    g['on_run']()
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']
    pal.setCurrentText('fire')
    mapping.setCurrentText('log')
    scale.setValue(30.0)
    shift.setValue(0.25)
    g['inter'].setCurrentIndex(3)
    g['on_run']()                                       # same region: redrawn in place with the new settings
    view_now = MAP.curr
    want = (Decimal(exact(g, 'xbox')), Decimal(exact(g, 'ybox')), Decimal(exact(g, 'wbox')))
    real_dialog = g['QFileDialog']
    g['QFileDialog'] = dialog_returning(saved_png)
    g['on_save']()
    got = parse_view(read_png_text(saved_png))
    check('Save writes a PNG', open(saved_png, 'rb').read(8) == b'\x89PNG\r\n\x1a\n')
    check('the PNG carries the exact coordinates', (got['x'], got['y'], got['w']) == want, (got['x'], got['y'], got['w'], want))
    check('the PNG carries the multiplier and the colors',
          (got['multiplier'], got['palette'], got['mapping'], got['scale'], got['shift']) == (g['MULTIPLIERS'][3], 'fire', 'log', 30.0, 0.25), got)
    check('the PNG shows the picture on screen', same_pixels(QtGui.QImage(saved_png), QtGui.QImage(g['image_path'](view_now))))
    g['QFileDialog'] = dialog_returning(os.path.join(saves, 'no-extension'))
    g['on_save']()
    check('Save adds .png to a name without it', os.path.exists(os.path.join(saves, 'no-extension.png')), os.listdir(saves))
    check('Save leaves no temporary files', not [n for n in os.listdir(saves) if n.endswith('.part')], os.listdir(saves))
    # a long, deep coordinate survives the round trip exactly
    deep_x = '-0.' + '7436438870371587047521915061147740' * 6
    img = QtGui.QImage(30, 20, QtGui.QImage.Format_RGB32)
    for k, v in view_text(deep_x, '0.13', '1.5E-190', g['MULTIPLIERS'][5], 'ocean', 'linear', 40, -0.5).items():
        img.setText(k, v)
    deep_png = os.path.join(saves, 'deep.png')
    img.save(deep_png, 'PNG')
    check('a 200-digit coordinate survives a PNG', parse_view(read_png_text(deep_png))['x'] == Decimal(deep_x))

    # Open: from somewhere else, with other colors set, the saved view comes back as a new view with its colors
    g['on_reset']()
    pal.setCurrentText('twilight')
    mapping.setCurrentText('histogram')
    scale.setValue(0.0)
    shift.setValue(0.0)
    g['inter'].setCurrentIndex(0)
    entries, ncalls = len(list(MAP)), len(calls())
    g['QFileDialog'] = dialog_returning(saved_png)
    g['on_open']()
    check('Open adds the saved view to the history', len(list(MAP)) == entries + 1, (entries, len(list(MAP))))
    check('Open shows its exact coordinates', (Decimal(exact(g, 'xbox')), Decimal(exact(g, 'ybox')), Decimal(exact(g, 'wbox'))) == want)
    check('Open restores the multiplier', g['inter'].currentIndex() == 3 and MAP.curr.xywd.d == 3, MAP.curr.xywd)
    check('Open restores the colors', (pal.currentText(), mapping.currentText(), scale.value(), shift.value()) == ('fire', 'log', 30.0, 0.25))
    if not REAL:
        call_line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('Open renders with the saved settings', Decimal(call_line[0]) == want[0] and Decimal(call_line[2]) == want[2] and call_line[4] == str(g['MULTIPLIERS'][3])
              and '--palette=fire' in call_line and '--mapping=log' in call_line and '--scale=30' in call_line and '--shift=0.25' in call_line, call_line)
    else:
        check('Open drew a proper image', image_ok(g['image_path'](MAP.curr)), g['image_path'](MAP.curr))
    entries = len(list(MAP))
    g['on_open']()
    check('opening the view that is already showing redraws it in place', len(list(MAP)) == entries, (entries, len(list(MAP))))

    # things that are not usable are refused with a message, and nothing is drawn
    def refused(path, label):
        shown_dialogs, n_entries, n_calls = len(dialogs), len(list(MAP)), len(calls())
        g['QFileDialog'] = dialog_returning(path)
        g['on_open']()
        check('Open refuses %s' % label, len(dialogs) == shown_dialogs + 1 and len(list(MAP)) == n_entries and len(calls()) == n_calls,
              (len(dialogs) - shown_dialogs, dialogs[-1:]))
    plain = QtGui.QImage(30, 20, QtGui.QImage.Format_RGB32)
    plain_png = os.path.join(saves, 'plain.png')
    plain.save(plain_png, 'PNG')
    refused(plain_png, 'a PNG that has no saved view')
    notpng = os.path.join(saves, 'text.png')
    open(notpng, 'w').write('this is not an image')
    refused(notpng, 'a file that is not a PNG')
    as_bmp = os.path.join(saves, 'real.bmp')
    QtGui.QImage(g['image_path'](MAP.curr)).save(as_bmp, 'BMP')
    refused(as_bmp, 'a BMP image')
    a_png_with_other_name = os.path.join(saves, 'picture.dat')
    shutil.copy(saved_png, a_png_with_other_name)
    refused(a_png_with_other_name, 'a PNG that is not named .png')
    bmp_named_png = os.path.join(saves, 'disguised.png')
    shutil.copy(as_bmp, bmp_named_png)
    refused(bmp_named_png, 'a BMP renamed to .png')
    jpeg = os.path.join(saves, 'photo.jpg')
    QtGui.QImage(g['image_path'](MAP.curr)).save(jpeg, 'JPEG')
    refused(jpeg, 'a JPEG')
    refused(os.path.join(saves, 'missing.png'), 'a file that does not exist')
    good_fields = view_text('-1', '0', '2', 1, 'fire', 'log', 0, 0)
    for label, change in (('a non-numeric width', {'mandelbrot.width': 'wide'}), ('a negative width', {'mandelbrot.width': '-2'}),
                          ('a multiplier the program does not offer', {'mandelbrot.multiplier': '12345678'}),
                          ('a multiplier that is not a number', {'mandelbrot.multiplier': 'lots'}),
                          ('a made-up mapping', {'mandelbrot.mapping': 'sparkle'}),
                          ('a newer file format', {'mandelbrot.version': '99'}),
                          ('a huge exponent', {'mandelbrot.x': '1e99999'})):
        tampered = QtGui.QImage(30, 20, QtGui.QImage.Format_RGB32)
        for k, v in dict(good_fields, **change).items():
            tampered.setText(k, v)
        bad = os.path.join(saves, 'bad.png')
        tampered.save(bad, 'PNG')
        refused(bad, label)
    g['QFileDialog'] = real_dialog

    # -- the tiny x on the selected thumbnail deletes a view and its files; Back skips deleted views
    from cleanup import view_files
    g['on_reset']()
    chain = []
    for _ in range(3):                                  # opening view -> A -> B -> C, each zoomed from the one before
        release(g, 300, 500, 600)
        g['on_run']()
        chain.append(MAP.curr)
    A, B, C = chain
    n_of = lambda item: os.path.basename(item.fname)[len('mandapp'):-len('.bmp')]
    guards = [os.path.join(pix, 'mandapp%sx.bmp' % n_of(B)), os.path.join(pix, 'mandapp%s.png' % n_of(B)),
              os.path.join(pix, 'mandapp%s0.bmp' % n_of(B)), os.path.join(pix, 'mandapp%s0.bmp.nu' % n_of(B))]
    for f in guards:
        open(f, 'wb').write(b'not this view')
    open(B.fname + '.ref', 'wb').write(b'leftover')       # a stray temporary file of that view
    open(os.path.join(pix, 'mandapp%s.c4.bmp' % n_of(B)), 'wb').write(b'older recolor')
    B.icon.click()
    check('the x shows on the selected thumbnail only', B.icon.closer.isVisible() and not A.icon.closer.isVisible() and
          not C.icon.closer.isVisible() and not g['INITPG'].icon.closer.isVisible())
    check('the x is small and in the thumbnail\'s top-right corner', B.icon.closer.width() <= 20 and
          B.icon.closer.x() > B.icon.width() - 40 and B.icon.closer.y() < 10, (B.icon.closer.geometry(), B.icon.size()))
    b_files = view_files(pix, B.fname)
    check('a view\'s files are found by exact name', len(b_files) >= 4 and not set(guards) & set(b_files),
          sorted(os.path.basename(f) for f in b_files))
    asked = []
    g['confirm_delete'] = lambda parent, count, size: (asked.append((count, size)), False)[1]
    thumbs_before = g['scr_layout'].count()
    B.icon.closer.click()
    check('Cancel keeps the view, its files and its thumbnail', MAP[B.fname] is not None and all(os.path.exists(f) for f in b_files) and
          g['scr_layout'].count() == thumbs_before and asked and asked[-1][0] == len(b_files) and asked[-1][1] > 0, asked)
    g['confirm_delete'] = lambda parent, count, size: True
    other_files = view_files(pix, A.fname) + view_files(pix, C.fname)
    had_record = B.fname in g['VIEW_COLORS']
    B.icon.closer.click()
    check('deleting removes the view from the history', MAP[B.fname] is None and len(list(MAP)) == 3,
          [i.fname for i in MAP])
    check('...and every file made for it', not any(os.path.exists(f) for f in b_files), [f for f in b_files if os.path.exists(f)])
    check('...but no other view\'s files and nothing that only looks similar',
          all(os.path.exists(f) for f in other_files + guards), [f for f in other_files + guards if not os.path.exists(f)])
    check('...and its thumbnail', g['scr_layout'].count() == thumbs_before - 1 and B.icon.parent() is None)
    check('...and the settings recorded for it, but not another view\'s',
          had_record and B.fname not in g['VIEW_COLORS'] and A.fname in g['VIEW_COLORS'] and C.fname in g['VIEW_COLORS'],
          (had_record, sorted(os.path.basename(k) for k in g['VIEW_COLORS'])))
    check('the view before it is shown instead', MAP.curr.fname == A.fname and Decimal(exact(g, 'wbox')) == Decimal(A.xywd.w), MAP.curr.fname)
    check('the x moved to the newly selected thumbnail', A.icon.closer.isVisible() and not C.icon.closer.isVisible())
    check('the view that was zoomed from the deleted one now hangs from its parent', MAP[C.fname].parent == A.fname, MAP[C.fname].parent)
    C.icon.click()
    g['on_back']()
    check('Back from C goes to A, the next real view back, not the deleted one', MAP.curr.fname == A.fname, MAP.curr.fname)
    # delete A as well: C now hangs from the opening view
    A.icon.click()
    A.icon.closer.click()
    check('deleting the next view works the same way', MAP[A.fname] is None and MAP.curr.fname == g['STARTFILE'] and MAP[C.fname].parent == g['STARTFILE'],
          (MAP.curr.fname, MAP[C.fname].parent))
    check('the opening view has no x', not g['INITPG'].icon.closer.isVisible())
    C.icon.click()
    g['on_back']()
    check('Back from C now goes to the opening view', MAP.curr.fname == g['STARTFILE'], MAP.curr.fname)
    before = len(list(MAP))
    g['on_delete_view'](g['STARTFILE'])
    check('the opening view cannot be deleted', len(list(MAP)) == before and os.path.exists(os.path.join(pix, 'whole.bmp')))
    # a parent that has gone missing falls back to the opening view
    MAP._map[C.fname] = MAP[C.fname]._replace(parent='no-such-view.bmp')
    C.icon.click()
    g['on_back']()
    check('Back with a missing parent falls back to the opening view', MAP.curr.fname == g['STARTFILE'], MAP.curr.fname)
    # a failed delete is reported
    D = None
    release(g, 300, 500, 600)
    g['on_run']()
    D = MAP.curr
    d_files = view_files(pix, D.fname)
    real_delete = g['delete_files']
    g['delete_files'] = lambda paths: len(paths)         # pretend nothing could be removed
    warned = len(dialogs)
    D.icon.closer.click()
    g['delete_files'] = real_delete
    check('files that cannot be deleted are reported, and the view is still dropped', len(dialogs) == warned + 1 and MAP[D.fname] is None, dialogs[-1:])
    for f in d_files:
        os.remove(f)
    for f in guards + [os.path.join(pix, 'mandapp%s.c4.bmp' % n_of(B))]:
        if os.path.exists(f):
            os.remove(f)
    g['confirm_delete'] = lambda parent, count, size: True
    g['on_reset']()

    # -- selecting a view shows that view's own settings in every control
    # (Changing the Colors box repaints the view that is selected, when it can be repainted, so each view's settings
    # are whatever its picture was last given: read from the program's record of them, and checked to differ.)
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']

    def set_controls(p, m, sc, sh, mult=None):
        pal.setCurrentText(p)
        mapping.setCurrentText(m)
        scale.setValue(sc)
        shift.setValue(sh)
        if mult is not None:
            g['inter'].setCurrentIndex(mult)
    g['on_reset']()
    set_controls('fire', 'log', 30.0, 0.25, 2)
    release(g, 300, 500, 600)
    g['on_run']()
    V1 = MAP.curr
    set_controls('ice', 'linear', 0.0, -0.5, 4)
    release(g, 100, 100, 400)
    g['on_run']()
    V2 = MAP.curr
    set_controls('gray', 'histogram', 7.0, 0.9)            # (repaints V2 when it can)
    rec = g['VIEW_COLORS']

    def shows(item):
        """What every control currently says, and what it should say for this view."""
        got = {'palette': pal.currentText(), 'mapping': mapping.currentText(), 'scale': scale.value(), 'shift': shift.value(),
               'multiplier': g['inter'].currentIndex(), 'dial': g['iter_dial'].value(),
               'x': Decimal(exact(g, 'xbox')), 'y': Decimal(exact(g, 'ybox')), 'w': Decimal(exact(g, 'wbox'))}
        colors = rec[item.fname]
        want = {'palette': colors[0], 'mapping': colors[1], 'scale': colors[2], 'shift': colors[3], 'multiplier': int(item.xywd.d),
                'dial': int(item.xywd.d), 'x': Decimal(item.xywd.x), 'y': Decimal(item.xywd.y), 'w': Decimal(item.xywd.w)}
        return got, want

    check('the two views have different color settings and different multipliers', rec[V1.fname] != rec[V2.fname] and V1.xywd.d != V2.xywd.d,
          (rec[V1.fname], rec[V2.fname]))
    if REAL:        # with the real recolorer the records are exactly what was last applied to each picture
        check('each view\'s record is what its picture was last given', rec[V1.fname][:4] == ('ice', 'linear', 0.0, -0.5) and
              rec[V2.fname][:4] == ('gray', 'histogram', 7.0, 0.9), (rec[V1.fname], rec[V2.fname]))
    V1.icon.click()
    got, want = shows(V1)
    check('selecting a view shows ITS palette, mapping, scale, shift, multiplier, dial and coordinates', got == want and got['multiplier'] == 2,
          (got, want))
    V2.icon.click()
    got, want = shows(V2)
    check('selecting another view replaces them with that view\'s own, not the ones used before', got == want and got['multiplier'] == 4 and
          (got['palette'], got['shift']) == (rec[V2.fname][0], rec[V2.fname][3]), (got, want))
    set_controls('sunset', 'log', 12.0, 0.4)                # change V2's colors, then go to V1 and back
    after_change = rec[V2.fname]
    V1.icon.click()
    got, want = shows(V1)
    check('...and the settings just used on another view do not carry over', got == want and rec[V1.fname] != ('sunset', 'log', 12.0, 0.4), (got, want))
    V2.icon.click()
    got, want = shows(V2)
    check('a view keeps the colors it was last given', got == want and rec[V2.fname] == after_change, (got, want))
    V1.icon.click()
    g['on_back']()
    got, want = shows(MAP.curr) if MAP.curr.fname in rec else (None, None)
    check('Back shows the earlier view\'s settings too', MAP.curr.fname == g['STARTFILE'] and got == want, (MAP.curr.fname, got, want))
    # -- zooming from an earlier view starts from THAT view's settings, not whatever was last put in the controls
    g['on_reset']()
    set_controls('fire', 'log', 30.0, 0.25, 2)
    release(g, 300, 500, 600)
    g['on_run']()
    P = MAP.curr                                          # the view to come back to
    set_controls('ice', 'linear', 0.0, -0.5, 4)
    release(g, 100, 100, 400)
    g['on_run']()
    Q = MAP.curr
    set_controls('gray', 'histogram', 7.0, 0.9, 6)       # "new settings" left in the controls
    P.icon.click()                                        # fall back to P, then box a part of it
    release(g, 200, 200, 300)
    ncalls = len(calls())
    g['on_run']()
    R = MAP.curr
    check('the new view is a child of the view it was boxed from', R.parent == P.fname, (R.parent, P.fname))
    check('it inherits that view\'s multiplier, not the one left in the controls', R.xywd.d == P.xywd.d and R.xywd.d != 6, (R.xywd.d, P.xywd.d))
    check('it inherits that view\'s colors, not the ones left in the controls', rec[R.fname] == rec[P.fname] and rec[R.fname][0] != 'gray',
          (rec[R.fname], rec[P.fname]))
    if not REAL:
        line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('the renderer was asked for that view\'s settings', line[4] == str(g['MULTIPLIERS'][int(P.xywd.d)]) and
              '--palette=' + rec[P.fname][0] in line and '--mapping=' + rec[P.fname][1] in line, line)
    got, want = shows(R)
    check('and every control shows the new view\'s settings (which are the old view\'s)', got == want, (got, want))
    # the same from the opening view, even though nothing was ever drawn from it with a recolorer
    set_controls('aurora', 'linear', 9.0, 0.3, 5)
    g['INITPG'].icon.click()
    got = (pal.currentText(), mapping.currentText(), scale.value(), shift.value(), g['inter'].currentIndex())
    check('selecting the opening view shows its own settings', got == (*rec[g['STARTFILE']][:4], int(g['INITPG'].xywd.d)) and got[0] != 'aurora' and got[4] != 5, got)
    release(g, 300, 500, 600)
    g['on_run']()
    S0 = MAP.curr
    check('a view boxed from the opening view starts from the opening view\'s settings',
          S0.parent == g['STARTFILE'] and rec[S0.fname] == rec[g['STARTFILE']] and S0.xywd.d == g['INITPG'].xywd.d, (rec[S0.fname], rec[g['STARTFILE']]))
    # settings changed AFTER selecting the view are the user's choice and do apply
    set_controls(pal.currentText(), mapping.currentText(), scale.value(), shift.value(), 3)
    release(g, 100, 100, 400)
    g['on_run']()
    check('a multiplier chosen after selecting the view is used', MAP.curr.xywd.d == 3, MAP.curr.xywd)

    # -- the case as the user put it: the palette control says rainbow, an ocean image is selected, a piece of it is boxed
    g['on_reset']()
    set_controls('ocean', 'histogram', 0.0, 0.0, 0)
    release(g, 300, 500, 600)
    g['on_run']()
    ocean_view = MAP.curr
    release(g, 100, 100, 400)
    g['on_run']()                                         # another view, zoomed from the ocean one
    set_controls('rainbow', 'histogram', 0.0, 0.0)        # ...which is then given rainbow
    check('(the palette control says rainbow)', pal.currentText() == 'rainbow')
    ocean_view.icon.click()
    check('selecting the ocean image puts ocean in the palette control', pal.currentText() == 'ocean', pal.currentText())
    release(g, 200, 200, 300)
    g['on_run']()
    blown_up = MAP.curr
    check('a piece blown up from the ocean image comes up ocean, not rainbow',
          blown_up.parent == ocean_view.fname and rec[blown_up.fname][0] == 'ocean' and pal.currentText() == 'ocean', (rec[blown_up.fname], pal.currentText()))
    if not REAL:
        line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('the renderer was told --palette=ocean', '--palette=ocean' in line and '--palette=rainbow' not in line, line)
    else:
        expected_file = os.path.join(tmp, 'ocean-check.bmp')
        subprocess.run([os.path.join(tmp, 'colorize'), blown_up.fname + '.nu', expected_file, '--palette=ocean', '--mapping=histogram'],
                       check=True, capture_output=True)
        check('the drawn picture is exactly what the ocean palette makes',
              open(g['image_path'](blown_up), 'rb').read() == open(expected_file, 'rb').read())

    # selecting only looks: nothing is recolored or redrawn, no files change
    files_now = {n: os.path.getmtime(os.path.join(pix, n)) for n in os.listdir(pix)}
    recolors, real_recolor = [], g['recolor']
    g['recolor'] = lambda it: (recolors.append(it.fname), real_recolor(it))[1]
    calls_before = len(calls())
    for item in (V2, V1, V2):
        item.icon.click()
    g['recolor'] = real_recolor
    check('selecting views recolors nothing, renders nothing and changes no file',
          not recolors and len(calls()) == calls_before and {n: os.path.getmtime(os.path.join(pix, n)) for n in os.listdir(pix)} == files_now,
          (recolors, len(calls()) - calls_before))
    V1.icon.click()
    check('the picture on screen is the selected view\'s own file', g['reg'].source.toImage() == QtGui.QImage(g['image_path'](V1)))
    # a Reset forgets the settings of the views it throws away (but not the opening view's)
    g['ask_cleanup'] = lambda parent, count, size, reset=False: 'keep'
    g['on_reset']()
    check('Reset forgets the old views\' settings', V1.fname not in g['VIEW_COLORS'] and V2.fname not in g['VIEW_COLORS'], list(g['VIEW_COLORS']))
    g['inter'].setCurrentIndex(0)
    for box, value in ((pal, 'twilight'), (mapping, 'histogram')):
        box.setCurrentText(value)
    scale.setValue(0.0)
    shift.setValue(0.0)

    # -- gamma, brightness, contrast and the interior color: controls, recoloring, the renderer, PNGs, per-view settings
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']
    gamma, bright, contrast, interior = g['gamma_box'], g['brightness_box'], g['contrast_box'], g['interior_btn']
    group = g['color_group']
    g['on_reset']()
    for box in (pal, mapping, scale, shift):
        box.blockSignals(True)
    pal.setCurrentText('twilight')
    mapping.setCurrentText('histogram')
    scale.setValue(0.0)
    shift.setValue(0.0)
    for box in (pal, mapping, scale, shift):
        box.blockSignals(False)
    check('the new colors controls start at the plain settings', (gamma.value(), bright.value(), contrast.value(), g['interior_hex']()) ==
          (1.0, 0.0, 0.0, '000000'), (gamma.value(), bright.value(), contrast.value(), g['interior_hex']()))
    check('the new controls are in the Colors box, each with a Restore button on its row',
          all(g[n].parent() is group for n in ('gamma_box', 'brightness_box', 'contrast_box', 'interior_btn', 'restore_gamma_btn',
                                               'restore_brightness_btn', 'restore_contrast_btn', 'restore_interior_btn')) and
          all(abs(pos_row(r).y() + g[r].height() // 2 - pos_row(b).y() - g[b].height() // 2) <= 3 and pos_row(r).x() >= pos_row(b).x() + g[b].width() - 2
              for b, r in (('gamma_box', 'restore_gamma_btn'), ('brightness_box', 'restore_brightness_btn'),
                           ('contrast_box', 'restore_contrast_btn'), ('interior_btn', 'restore_interior_btn'))),
          [pos_row(n) for n in ('gamma_box', 'restore_gamma_btn', 'interior_btn', 'restore_interior_btn')])
    check('every Colors row fits inside the column (nothing is cut off at the right)',
          all(g[n].mapTo(window, QtCore.QPoint(g[n].width(), 0)).x() <= g['controls_scroll'].mapTo(window, QtCore.QPoint(g['controls_scroll'].width(), 0)).x()
              for n in ('restore_scale_btn', 'restore_gamma_btn', 'restore_brightness_btn', 'restore_contrast_btn', 'restore_interior_btn', 'xbox', 'open_btn')),
          g['controls_scroll'].width())
    check('the ranges are the ones the program accepts', (gamma.minimum(), gamma.maximum(), bright.minimum(), bright.maximum(),
                                                         contrast.minimum(), contrast.maximum()) == (0.1, 10.0, -100.0, 100.0, -100.0, 100.0))

    # picking an interior color: the program's own color dialog is replaced by one that answers
    real_getcolor = g['QColorDialog'].getColor
    answers = []

    def pick(hexcolor):
        answers.append(hexcolor)
        g['QColorDialog'].getColor = staticmethod(lambda *a, **k: QtGui.QColor('#' + hexcolor) if hexcolor else QtGui.QColor())

    recolors = []
    real_recolor = g['recolor']
    g['recolor'] = lambda item: (recolors.append(item.fname), real_recolor(item))[1]
    pick('102030')
    interior.click()
    check('choosing an interior color shows it on the button', g['interior_hex']() == '102030' and interior.text() == '#102030' and
          '#102030' in interior.styleSheet().lower(), (g['interior_hex'](), interior.text(), interior.styleSheet()))
    check('and recolors the view once', recolors == [MAP.curr.fname], recolors)
    pick('')                                        # the dialog was canceled
    del recolors[:]
    interior.click()
    check('canceling the color dialog changes nothing', g['interior_hex']() == '102030' and not recolors, (g['interior_hex'](), recolors))
    pick('102030')
    interior.click()
    check('choosing the color that is already set recolors nothing', not recolors, recolors)
    g['restore_interior_btn'].click()
    check('Restore beside Interior puts it back to black, recoloring once', g['interior_hex']() == '000000' and interior.text() == '#000000' and
          len(recolors) == 1, (g['interior_hex'](), recolors))
    del recolors[:]
    g['restore_interior_btn'].click()
    check('Restore beside Interior when already black does nothing', not recolors, recolors)
    g['QColorDialog'].getColor = real_getcolor
    g['recolor'] = real_recolor

    # the real color dialog: a click on its color spectrum must set the interior, even when it starts out black
    # (the dialog takes brightness from its slider, so opened on black every spectrum click would give black again)
    def with_dialog(act):
        seen = {}

        def run():
            box = QtWidgets.QApplication.activeModalWidget()
            seen['start'] = box.currentColor().name()
            act(box)
        QtCore.QTimer.singleShot(400, run)
        interior.click()
        return seen

    def spectrum(box):
        found = [c for c in box.findChildren(QtWidgets.QWidget) if c.metaObject().className() == 'QColorPicker'][0]
        QtTest.QTest.mouseClick(found, QtCore.Qt.LeftButton, pos=QtCore.QPoint(found.width() // 3, found.height() // 3))
        return box.currentColor().name()

    def press(box, label):
        [b for b in box.findChildren(QtWidgets.QPushButton) if b.text().replace('&', '') == label][0].click()

    del recolors[:]
    g['recolor'] = lambda item: (recolors.append(item.fname), real_recolor(item))[1]
    picked = []
    seen = with_dialog(lambda box: (picked.append(spectrum(box)), press(box, 'OK')))
    check('the color dialog does not open on black', seen['start'] != '#000000', seen)
    check('clicking its spectrum and OK sets the interior', g['interior_hex']() == picked[0][1:] != '000000' and interior.text() == picked[0], (picked, g['interior_hex']()))
    check('and recolors the view once', recolors == [MAP.curr.fname], recolors)
    chosen_before = g['interior_hex']()
    seen = with_dialog(lambda box: (spectrum(box), press(box, 'Cancel')))
    check('the dialog opens on the interior color when that is not black', seen['start'] == '#' + chosen_before, (seen, chosen_before))
    check('clicking the spectrum and then Cancel changes nothing', g['interior_hex']() == chosen_before, g['interior_hex']())
    g['restore_interior_btn'].click()
    del recolors[:]
    g['recolor'] = real_recolor

    # each Restore button puts back its own control only
    for box, value, restore, plain in ((gamma, 2.5, 'restore_gamma_btn', 1.0), (bright, 30.0, 'restore_brightness_btn', 0.0),
                                       (contrast, -40.0, 'restore_contrast_btn', 0.0)):
        for other in (gamma, bright, contrast):
            other.setValue({gamma: 1.5, bright: -20.0, contrast: 25.0}[other])
        box.setValue(value)
        g[restore].click()
        left = {gamma: 1.5, bright: -20.0, contrast: 25.0}
        left[box] = plain
        check('%s puts back only its own control' % restore, (gamma.value(), bright.value(), contrast.value()) ==
              (left[gamma], left[bright], left[contrast]), (gamma.value(), bright.value(), contrast.value()))
    for box in (gamma, bright, contrast):
        box.setValue(1.0 if box is gamma else 0.0)

    # the settings reach the renderer (only the ones that are not plain), in a render and in a redraw
    gamma.setValue(1.5)
    bright.setValue(-20.0)
    contrast.setValue(30.0)
    g['show_interior']('102030')
    release(g, 300, 500, 600)
    g['on_run']()
    colored = MAP.curr
    if not REAL:
        line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('the renderer is told gamma, brightness, contrast and interior', {'--gamma=1.5', '--brightness=-20', '--contrast=30', '--interior=102030'} <= set(line), line)
        gamma.setValue(1.0)
        bright.setValue(0.0)
        contrast.setValue(0.0)
        g['show_interior']('000000')
        g['inter'].setCurrentIndex(MAP.curr.xywd.d)
        g['on_run']()
        line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('plain settings are not passed at all', not [a for a in line if a.startswith(('--gamma', '--brightness', '--contrast', '--interior'))], line)
    else:
        import subprocess

        def expected(item, *opts):
            out = os.path.join(tmp, 'exp_%d.bmp' % len(os.listdir(tmp)))
            subprocess.run([os.path.join(tmp, 'colorize'), item.fname + '.nu', out, *opts], check=True, capture_output=True)
            return open(out, 'rb').read()
        base = ['--palette=twilight', '--mapping=histogram']
        full = base + ['--gamma=1.5', '--brightness=-20', '--contrast=30', '--interior=102030']
        check('the renderer drew the picture with all four settings', open(g['image_path'](colored), 'rb').read() == expected(colored, *full))
        plain_image = expected(colored, *base)
        check('and that is not what the plain settings give', open(g['image_path'](colored), 'rb').read() != plain_image)
        files_before = sorted(os.listdir(os.path.join(tmp, 'pix')))
        for label, setter, opts in (
                ('gamma', lambda: gamma.setValue(0.4), base + ['--gamma=0.4', '--brightness=-20', '--contrast=30', '--interior=102030']),
                ('brightness', lambda: bright.setValue(55.0), base + ['--gamma=0.4', '--brightness=55', '--contrast=30', '--interior=102030']),
                ('contrast', lambda: contrast.setValue(-60.0), base + ['--gamma=0.4', '--brightness=55', '--contrast=-60', '--interior=102030']),
                ('interior', lambda: g['restore_interior_btn'].click(), base + ['--gamma=0.4', '--brightness=55', '--contrast=-60'])):
            setter()
            check('changing %s recolors the picture in place' % label, open(g['image_path'](colored), 'rb').read() == expected(colored, *opts) and
                  g['reg'].source.toImage() == QtGui.QImage(g['image_path'](colored)))
        check('and leaves no extra files behind', sorted(os.listdir(os.path.join(tmp, 'pix'))) == files_before,
              set(os.listdir(os.path.join(tmp, 'pix'))) ^ set(files_before))
        # the inside of the set really is the chosen color, and the palette colors really change with contrast and brightness
        g['show_interior']('102030')
        g['on_color_change']()
        img = QtGui.QImage(g['image_path'](colored))
        shades = {img.pixel(x, y) & 0xFFFFFF for x in range(0, img.width(), 9) for y in range(0, img.height(), 9)}
        check('the interior pixels have the chosen color', 0x102030 in shades, len(shades))
        bright.setValue(-100.0)
        contrast.setValue(0.0)
        gamma.setValue(1.0)
        img = QtGui.QImage(g['image_path'](colored))
        shades = {img.pixel(x, y) & 0xFFFFFF for x in range(0, img.width(), 9) for y in range(0, img.height(), 9)}
        check('brightness -100 leaves only the interior color and black', shades <= {0x102030, 0x000000}, len(shades))
        g['restore_brightness_btn'].click()

    # settings are remembered per view, saved in the PNG, and restored by Open and by selecting the view
    for box, v in ((gamma, 2.25), (bright, 15.0), (contrast, -35.0)):
        box.setValue(v)
    g['show_interior']('a0b1c2')
    pal.setCurrentText('fire')
    g['on_run']()                                   # redrawn in place with every setting
    here = MAP.curr
    check('the view\'s record has all eight settings', tuple(g['VIEW_COLORS'][here.fname]) == ('fire', 'histogram', 0.0, 0.0, 2.25, 15.0, -35.0, 'a0b1c2') or
          tuple(g['VIEW_COLORS'][here.fname])[4:] == (2.25, 15.0, -35.0, 'a0b1c2'), g['VIEW_COLORS'][here.fname])
    g['QFileDialog'] = dialog_returning(os.path.join(saves, 'adjusted.png'))
    g['on_save']()
    got = parse_view(read_png_text(os.path.join(saves, 'adjusted.png')))
    check('the PNG carries gamma, brightness, contrast and the interior color',
          (got['gamma'], got['brightness'], got['contrast'], got['interior']) == (2.25, 15.0, -35.0, 'a0b1c2'), got)
    # a different view with different settings
    g['on_reset']()
    release(g, 100, 100, 400)
    for box, v in ((gamma, 0.5), (bright, -60.0), (contrast, 80.0)):
        box.setValue(v)
    g['show_interior']('ffffff')
    g['on_run']()
    other = MAP.curr
    check('a second view has its own record', tuple(g['VIEW_COLORS'][other.fname])[4:] == (0.5, -60.0, 80.0, 'ffffff'), g['VIEW_COLORS'][other.fname])
    # Open the saved one: everything comes back
    g['QFileDialog'] = dialog_returning(os.path.join(saves, 'adjusted.png'))
    g['on_open']()
    now = (gamma.value(), bright.value(), contrast.value(), g['interior_hex']())
    check('Open restores gamma, brightness, contrast and the interior color', now == (2.25, 15.0, -35.0, 'a0b1c2'), now)
    reopened = MAP.curr
    if not REAL:
        line = [c.split() for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED'][-1]
        check('Open renders with them', {'--gamma=2.25', '--brightness=15', '--contrast=-35', '--interior=a0b1c2'} <= set(line), line)
    check('the reopened view\'s record has them', tuple(g['VIEW_COLORS'][reopened.fname])[4:] == (2.25, 15.0, -35.0, 'a0b1c2'))
    # selecting the other view, then this one, shows each view's own
    other.icon.click()
    now = (gamma.value(), bright.value(), contrast.value(), g['interior_hex'](), interior.text())
    check('selecting a view shows its gamma, brightness, contrast and interior', now == (0.5, -60.0, 80.0, 'ffffff', '#ffffff'), now)
    reopened.icon.click()
    now = (gamma.value(), bright.value(), contrast.value(), g['interior_hex'](), interior.text())
    check('and selecting the other shows its own', now == (2.25, 15.0, -35.0, 'a0b1c2', '#a0b1c2'), now)
    # a region boxed from a view starts from that view's settings
    for box, v in ((gamma, 7.0), (bright, 33.0), (contrast, 11.0)):
        box.setValue(v)                             # (settings left in the controls from something else)
    other.icon.click()
    release(g, 200, 200, 300)
    g['on_run']()
    child = MAP.curr
    check('a region boxed from a view inherits its gamma, brightness, contrast and interior (not what was left in the controls)',
          tuple(g['VIEW_COLORS'][child.fname])[4:] == (0.5, -60.0, 80.0, 'ffffff'), g['VIEW_COLORS'][child.fname])
    # a PNG saved before these settings existed opens with the plain ones
    img = QtGui.QImage(30, 20, QtGui.QImage.Format_RGB32)
    for k, v in view_text('-1', '0', '2', 1, 'ocean', 'log', 0, 0).items():
        if k.split('.')[-1] not in ('gamma', 'brightness', 'contrast', 'interior'):
            img.setText(k, v)
    old_png = os.path.join(saves, 'old.png')
    img.save(old_png, 'PNG')
    g['QFileDialog'] = dialog_returning(old_png)
    g['on_open']()
    now = (gamma.value(), bright.value(), contrast.value(), g['interior_hex']())
    check('an older PNG without them opens with the plain settings', now == (1.0, 0.0, 0.0, '000000') and pal.currentText() == 'ocean', now)
    for label, change in (('a gamma out of range', {'mandelbrot.gamma': '50'}), ('a brightness out of range', {'mandelbrot.brightness': '500'}),
                          ('an interior that is not a color', {'mandelbrot.interior': 'purple'})):
        tampered = QtGui.QImage(30, 20, QtGui.QImage.Format_RGB32)
        for k, v in dict(view_text('-1', '0', '2', 1, 'fire', 'log', 0, 0), **change).items():
            tampered.setText(k, v)
        bad = os.path.join(saves, 'bad2.png')
        tampered.save(bad, 'PNG')
        shown_dialogs, n_entries = len(dialogs), len(list(MAP))
        g['QFileDialog'] = dialog_returning(bad)
        g['on_open']()
        check('Open refuses %s' % label, len(dialogs) == shown_dialogs + 1 and len(list(MAP)) == n_entries, dialogs[-1:])
    g['QFileDialog'] = real_dialog
    for box in (gamma, bright, contrast):
        box.blockSignals(True)
        box.setValue(1.0 if box is gamma else 0.0)
        box.blockSignals(False)
    g['show_interior']('000000')
    g['on_reset']()

    # -- the side column: the controls and the history pictures share its height; show either alone, or drag the bar
    split, panes = g['split'], g['panes']
    cb, ib = g['controls_btn'], g['images_btn']
    QtWidgets.QApplication.processEvents()
    sizes = split.sizes()
    check('the controls and the images both show to begin with', cb.isChecked() and ib.isChecked() and min(sizes) > 100, sizes)
    check('the controls open with a good share of the column and the images with the rest', 250 < sizes[0] < 0.7 * sum(sizes) and sizes[1] > 150, sizes)
    check('the opening share is what they need, up to 60% of the column',
          panes.preferred(sum(sizes)) == max(panes.MIN, min(g['controls_panel'].sizeHint().height() + 4, int(sum(sizes) * 0.6))), panes.preferred(sum(sizes)))
    check('the buttons and the two toggle buttons sit above the splitter',
          all(pos_row(n).y() < pos_row('split').y() for n in ('run', 'back', 'save', 'reset', 'controls_btn', 'images_btn')),
          [pos_row(n).y() for n in ('run', 'controls_btn', 'split')])
    total = sum(sizes)
    ib.click()
    QtWidgets.QApplication.processEvents()
    check('Images off: the controls take the whole column', split.sizes()[1] == 0 and split.sizes()[0] >= total - 2 and not ib.isChecked(), split.sizes())
    check('the images are hidden from view', not g['scroll'].isVisibleTo(window) or g['scroll'].height() == 0, g['scroll'].height())
    check('Run, Back, Save and Reset are still there', all(g[n].isVisibleTo(window) and g[n].isEnabled() for n in ('run', 'back', 'save', 'reset')))
    cb.click()
    check('the last open part cannot be hidden', cb.isChecked() and split.sizes()[1] == 0 and split.sizes()[0] > 0, (cb.isChecked(), split.sizes()))
    ib.click()
    QtWidgets.QApplication.processEvents()
    check('Images back on: both show again, divided as before', ib.isChecked() and min(split.sizes()) > 100 and abs(split.sizes()[0] - sizes[0]) <= 3,
          (split.sizes(), sizes))
    cb.click()
    QtWidgets.QApplication.processEvents()
    check('Controls off: the images take the whole column', split.sizes()[0] == 0 and split.sizes()[1] >= total - 2 and not cb.isChecked(), split.sizes())
    check('the controls are hidden but Run and the toggle buttons are still there', all(g[n].isVisibleTo(window) for n in ('run', 'controls_btn', 'images_btn')))
    ib.click()
    check('the images cannot be hidden while the controls are', ib.isChecked() and split.sizes()[1] > 0)
    cb.click()
    QtWidgets.QApplication.processEvents()
    check('Controls back on: both show again', cb.isChecked() and ib.isChecked() and min(split.sizes()) > 100, split.sizes())
    # dragging the bar (the real splitter call that a drag makes)
    split.moveSplitter(sizes[0] + 80, 1)
    QtWidgets.QApplication.processEvents()
    moved = split.sizes()
    check('dragging the bar down gives the controls more room and the images less', moved[0] > sizes[0] + 60 and moved[1] < sizes[1] - 60 and cb.isChecked() and ib.isChecked(), (moved, sizes))
    split.moveSplitter(20, 1)
    QtWidgets.QApplication.processEvents()
    check('dragging it to the top closes the controls and unchecks their button', split.sizes()[0] == 0 and not cb.isChecked() and ib.isChecked(), (split.sizes(), cb.isChecked()))
    cb.click()
    QtWidgets.QApplication.processEvents()
    check('reopening them returns to where the bar had been', cb.isChecked() and abs(split.sizes()[0] - moved[0]) <= 3, (split.sizes(), moved))
    split.moveSplitter(45, 1)                       # (a sliver too small to be of any use closes too)
    QtWidgets.QApplication.processEvents()
    check('dragging the bar nearly to the top closes the controls rather than leaving a sliver', split.sizes()[0] == 0 and not cb.isChecked() and ib.isChecked(), (split.sizes(), cb.isChecked()))
    cb.click()
    QtWidgets.QApplication.processEvents()
    split.moveSplitter(sum(split.sizes()) - 10, 1)
    QtWidgets.QApplication.processEvents()
    check('dragging it to the bottom closes the images and unchecks their button', split.sizes()[1] == 0 and not ib.isChecked() and cb.isChecked(), (split.sizes(), ib.isChecked()))
    ib.click()
    QtWidgets.QApplication.processEvents()
    check('and they come back too', ib.isChecked() and cb.isChecked() and min(split.sizes()) > 60, split.sizes())
    check('the picture has not changed size', g['reg'].width() > 600, g['reg'].width())
    # the controls still work when scrolled, and Enter still runs while the controls are closed
    cb.click()
    QtWidgets.QApplication.processEvents()
    release(g, 300, 500, 600)
    entries = len(list(MAP))
    g['run_keys'][0].activated.emit()
    check('Enter still runs the selection with the controls closed', len(list(MAP)) == entries + 1, (entries, len(list(MAP))))
    cb.click()
    QtWidgets.QApplication.processEvents()
    g['on_reset']()

    # -- Reset puts every control back to its starting position, even on the whole set (the opening view)
    pal, mapping, scale, shift = g['pal_box'], g['map_box'], g['scale_box'], g['shift_box']
    gamma, bright, contrast = g['gamma_box'], g['brightness_box'], g['contrast_box']

    def everything():
        return (pal.currentText(), mapping.currentText(), scale.value(), shift.value(), gamma.value(), bright.value(),
                contrast.value(), g['interior_hex'](), g['inter'].currentIndex(), g['iter_dial'].value(),
                exact(g, 'xbox'), exact(g, 'ybox'), exact(g, 'wbox'))
    g['on_reset']()
    starting = everything()
    check('the starting position is the documented one', starting[:10] == ('gray', 'histogram', 0.0, 0.0, 1.0, 0.0, 0.0, '000000', 0, 0), starting)

    def disturb():
        pal.setCurrentText('fire')
        mapping.setCurrentText('log')
        scale.setValue(1.7)
        shift.setValue(0.35)
        gamma.setValue(2.2)
        bright.setValue(25.0)
        contrast.setValue(-30.0)
        g['show_interior']('336699')
        g['on_color_change']()
        g['inter'].setCurrentIndex(3)
    disturb()                                                   # on the whole set itself
    check('the controls really were changed', everything() != starting, everything())
    g['on_reset']()
    check('Reset on the whole set puts every control back, including the multiplier and dial', everything() == starting, everything())
    check('and the opening view\'s record is the starting settings', tuple(g['VIEW_COLORS'][g['STARTFILE']]) == tuple(g['DEFAULT_COLORS']),
          g['VIEW_COLORS'][g['STARTFILE']])
    if REAL:
        import subprocess
        shipped = open(os.path.join(tmp, 'pix', 'whole.bmp'), 'rb').read()
        out = os.path.join(tmp, 'plain_whole.bmp')
        subprocess.run([os.path.join(tmp, 'colorize'), os.path.join(tmp, 'pix', 'whole.bmp.nu'), out], check=True, capture_output=True)
        check('the opening picture is drawn with the starting colors again', open(g['image_path'](g['INITPG']), 'rb').read() == open(out, 'rb').read())
        check('and the shipped whole.bmp is untouched', open(os.path.join(tmp, 'pix', 'whole.bmp'), 'rb').read() == shipped)
        check('and the screen shows it', g['reg'].source.toImage() == QtGui.QImage(g['image_path'](g['INITPG'])))
    # the opening view redrawn with more iterations goes back to the starting ones
    g['inter'].setCurrentIndex(4)
    g['on_run']()
    check('the opening view was redrawn with a different multiplier', MAP.curr.fname == g['STARTFILE'] and g['INITPG'].xywd.d == 4,
          (MAP.curr.fname, g['INITPG'].xywd))
    ncalls = len([c for c in calls() if c.strip()])
    g['on_reset']()
    check('Reset puts the opening view\'s multiplier back too', g['INITPG'].xywd.d == 0 and g['inter'].currentIndex() == 0 and
          g['iter_dial'].value() == 0, (g['INITPG'].xywd, g['inter'].currentIndex()))
    if not REAL:
        line = [c.split() for c in [c for c in calls() if c.strip()][ncalls:] if c.split()[0] != 'REF_EXISTED']
        check('and it is drawn again with the starting iterations', line and line[-1][4] == '1' and line[-1][:3] == ['-2.75', '-1.333333', '4.0'], line)
    else:
        check('and it is drawn again with the starting iterations', os.path.exists(os.path.join(tmp, 'pix', 'whole.bmp.nu')))
    # from a deeper view with everything changed
    release(g, 300, 500, 600)
    disturb()
    g['on_run']()
    g['on_reset']()
    check('Reset from a zoomed view with everything changed does the same', everything() == starting and len(list(MAP)) == 1, everything())
    # a canceled Reset changes nothing
    release(g, 300, 500, 600)
    g['on_run']()
    disturb()
    mid = everything()
    keep_ask = g['ask_cleanup']
    g['ask_cleanup'] = lambda parent, count, size, reset=False: 'cancel'
    g['on_reset']()
    check('a canceled Reset leaves every control as it was', everything() == mid and len(list(MAP)) == 2, everything())
    g['ask_cleanup'] = keep_ask
    g['on_reset']()

    # -- a render that takes too long can be canceled, and closing the window during one cancels it
    if not REAL:
        import subprocess
        g['on_reset']()
        release(g, 300, 500, 600)
        slow = os.path.join(tmp, 'slow')

        def renderer_gone():
            try:
                pid = int(open(slow + '.pid').read())
                os.kill(pid, 0)
                with open('/proc/%d/stat' % pid) as stat:
                    return stat.read().rsplit(')', 1)[1].split()[0] == 'Z'
            except (OSError, ValueError):
                return True
        open(slow, 'w').close()
        shown_before, views_before, dialogs_before = MAP.curr, len(list(MAP)), len(dialogs)
        seen = {}

        def press_cancel():
            dlg = g['RENDER']['dialog']
            seen['dialog'] = dlg is not None and dlg.isVisible()
            seen['modal'] = dlg is not None and dlg.windowModality() == QtCore.Qt.ApplicationModal
            if dlg is not None:
                dlg.cancel()
        QtCore.QTimer.singleShot(1500, press_cancel)
        g['on_run']()
        check('a slow render shows a Cancel dialog after a moment', seen.get('dialog') and seen.get('modal'), seen)
        check('canceling stops it: no new view, no error dialog', MAP.curr is shown_before and len(list(MAP)) == views_before and len(dialogs) == dialogs_before,
              (MAP.curr is shown_before, len(list(MAP)), views_before, dialogs[dialogs_before:]))
        check('the renderer is gone and the dialog with it', renderer_gone() and
              g['RENDER']['dialog'] is None and not g['rendering']())
        check('and nothing is left half-drawn in pix', not [f for f in os.listdir(os.path.join(tmp, 'pix')) if f.endswith(('.new', '.func', '.ref'))],
              os.listdir(os.path.join(tmp, 'pix')))
        # closing the window mid-render: the render is stopped and the window stays (it closes on the next, ordinary, close)
        QtCore.QTimer.singleShot(800, window.close)
        g['on_run']()
        check('closing the window during a render cancels it and leaves the window open', window.isVisible() and MAP.curr is shown_before and
              renderer_gone(),
              (window.isVisible(), MAP.curr is shown_before))
        os.remove(slow)
        g['on_run']()
        check('and the next render is ordinary', MAP.curr is not shown_before and len(list(MAP)) == views_before + 1)
        g['on_reset']()

    # -- the function: z^2 + c (Mandelbrot) or z^d + c, recorded per view
    g['on_reset']()
    fbox, pbox = g['func_box'], g['power_box']

    def render_calls():
        return [c for c in calls() if c.strip() and c.split()[0] != 'REF_EXISTED']
    check('the function starts as the ordinary Mandelbrot set, with the exponent box off',
          fbox.currentIndex() == 0 and not pbox.isEnabled() and g['current_degree']() == 2, (fbox.currentIndex(), pbox.isEnabled()))
    release(g, 300, 500, 600)
    g['on_run']()
    plain_item = MAP.curr
    if not REAL:
        check('a plain view is drawn without a function option', '--func' not in render_calls()[-1], render_calls()[-1])
    check('a plain view is recorded as degree 2', g['recorded_func'](plain_item.fname) == 2)
    fbox.setCurrentIndex(1)
    check('choosing z^d + c turns the exponent box on', pbox.isEnabled())
    check('choosing a function draws nothing yet', MAP.curr is plain_item and len(list(MAP)) == 2)
    pbox.setValue(3)
    views_before = len(list(MAP))
    g['on_run']()
    cubic_item = MAP.curr
    check('Run with another function over the same region makes a new view', len(list(MAP)) == views_before + 1 and cubic_item is not plain_item,
          (views_before, len(list(MAP))))
    check('the new view is recorded as z^3', g['recorded_func'](cubic_item.fname) == 3 and g['VIEW_FUNC'][cubic_item.fname] == 3)
    if not REAL:
        check('the renderer is given a function file', any(a.startswith('--func=') for a in render_calls()[-1].split()), render_calls()[-1])
        spec = [a for a in render_calls()[-1].split() if a.startswith('--func=')][0][7:]
        check('and the temporary function file is cleaned up', not os.path.exists(spec), spec)
    else:
        check('the picture is not the plain Mandelbrot one', g['image_path'](cubic_item) != g['image_path'](plain_item) and
              open(g['image_path'](cubic_item), 'rb').read() != open(g['image_path'](plain_item), 'rb').read())
    release(g, 300, 500, 600)
    g['on_run']()
    child = MAP.curr
    check('a view zoomed from it keeps the function', g['recorded_func'](child.fname) == 3 and pbox.value() == 3 and fbox.currentIndex() == 1)
    g['fset'](plain_item)
    check('selecting the plain view\'s thumbnail shows its function', fbox.currentIndex() == 0 and not pbox.isEnabled() and g['current_degree']() == 2)
    g['fset'](cubic_item)
    check('selecting the cubic view\'s thumbnail shows z^3 again', fbox.currentIndex() == 1 and pbox.value() == 3 and pbox.isEnabled())
    # deep views get a reference orbit made for the same function
    pbox.setValue(5)
    g['reg'].cand_xyw.x, g['reg'].cand_xyw.y, g['reg'].cand_xyw.w = '-1.2', '-0.3', '1e-30'
    g['show_coords']('-1.2', '-0.3', '1e-30')
    nbefore = len(render_calls())
    g['on_run']()
    if not REAL:
        last = render_calls()[nbefore:]
        parts = last[-1].split() if last else []
        check('a deep view of z^5 is drawn from a reference orbit and a function file', len(parts) > 5 and parts[5].endswith('.ref') and
              any(x.startswith('--func=') for x in parts) and 'REF_EXISTED' in calls(), last)
    check('the deep view is recorded as z^5', g['recorded_func'](MAP.curr.fname) == 5, g['recorded_func'](MAP.curr.fname))
    # saved pictures carry the function
    target = os.path.join(saves, 'cubic.png')
    g['QFileDialog'] = dialog_returning(target)
    g['fset'](cubic_item)
    g['on_save']()
    fields = read_png_text(target)
    check('the PNG of a z^3 view says so', fields.get('mandelbrot.function') == 'power' and fields.get('mandelbrot.exponent') == '3' and
          fields.get('mandelbrot.version') == '2', fields)
    plain_target = os.path.join(saves, 'plain.png')
    g['QFileDialog'] = dialog_returning(plain_target)
    g['fset'](plain_item)
    g['on_save']()
    fields = read_png_text(plain_target)
    check('the PNG of a plain view has no function fields and the old version', 'mandelbrot.function' not in fields and
          'mandelbrot.exponent' not in fields and fields.get('mandelbrot.version') == '1', fields)
    g['QFileDialog'] = dialog_returning(target)
    count = len(list(MAP))
    g['on_open']()
    check('opening the z^3 PNG draws a z^3 view and shows the function', len(list(MAP)) == count + 1 and g['recorded_func'](MAP.curr.fname) == 3 and
          fbox.currentIndex() == 1 and pbox.value() == 3, (len(list(MAP)), g['recorded_func'](MAP.curr.fname)))
    g['QFileDialog'] = dialog_returning(plain_target)
    g['on_open']()
    check('opening the plain PNG puts the function back to z^2', g['recorded_func'](MAP.curr.fname) == 2 and fbox.currentIndex() == 0 and not pbox.isEnabled())
    # deleting a view forgets its function; Reset puts z^2 back
    gone = MAP.curr
    g['confirm_delete'] = lambda parent, count, size: True
    g['on_delete_view'](gone.fname)
    check('deleting a view forgets its function', gone.fname not in g['VIEW_FUNC'])
    fbox.setCurrentIndex(1)
    pbox.setValue(7)
    g['on_reset']()
    check('Reset puts the function back to z^2 and forgets every other view\'s', fbox.currentIndex() == 0 and not pbox.isEnabled() and
          list(g['VIEW_FUNC']) == [g['STARTFILE']] and g['VIEW_FUNC'][g['STARTFILE']] == 2, (fbox.currentIndex(), dict(g['VIEW_FUNC'])))

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
    check('Keep all (leaving them in pix/) resets but deletes nothing', len(list(MAP)) == 1 and all(os.path.exists(f) for f in old))
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
    check('Keep all in pix/ itself leaves the files where they are', all(os.path.exists(f) for f in gen))
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
    # only the opening view's files left (what Reset spares): no prompt, they are quietly removed
    window.show()
    only_opening = [os.path.join(pix_dir, n) for n in ('whole-start.bmp', 'whole.bmp.nu')]
    for f in only_opening:
        open(f, 'wb').write(b'opening view')
    asked.clear()
    check('with only the opening view\'s files left, quitting does not ask', window.close() is True and not asked, asked)
    check('...and removes them', not any(os.path.exists(f) for f in only_opening))
    check('...but never whole.bmp or other files', all(os.path.exists(f) for f in guard))
    # opening files plus anything else: the prompt appears and counts them all
    window.show()
    extra = os.path.join(pix_dir, 'mandapp88.bmp')
    for f in only_opening + [extra]:
        open(f, 'wb').write(b'x')
    asked.clear()
    answer('cancel')
    check('with other files too the prompt appears and counts the opening files as well',
          window.close() is False and asked and asked[-1][0] == 3, asked)
    for f in only_opening + [extra]:
        os.remove(f)
    answer('keep')

    # -- Keep all asks where to keep the files, and moves them there (into a new dated folder, never overwriting)
    dest = os.path.join(tmp, 'kept')
    os.makedirs(dest)
    precious = os.path.join(dest, 'mandapp1.bmp')
    open(precious, 'wb').write(b'already here')
    for _ in range(2):
        release(g, 300, 500, 600)
        g['on_run']()
    window.show()
    mine = g['generated_files'](pix_dir)
    MAPNOW = g['MAP']

    def item_of(f):
        item = MAPNOW[g['STARTFILE']] if f == g['START_COPY'] else MAPNOW[f]
        return item if item is not None and f == g['image_path'](item) else None

    def kept_name(f):
        """A picture of a view in this session is kept as a PNG; one left from earlier is moved as it was."""
        return os.path.basename(f)[:-4] + '.png' if item_of(f) else os.path.basename(f)
    images_before = {os.path.basename(f): QtGui.QImage(f) for f in mine if f.endswith('.bmp')}
    items_before = {os.path.basename(f): item_of(f) for f in mine if f.endswith('.bmp')}
    expected_names = sorted(kept_name(f) for f in mine if f.endswith('.bmp'))
    counts_files = [f for f in mine if not f.endswith('.bmp')]
    check('there are count files in play', len(counts_files) >= 2, counts_files)
    check('some pictures are of views in this session', any(items_before.values()), expected_names)
    answer('keep')
    asked_where = []
    g['ask_keep_folder'] = lambda parent: (asked_where.append(parent), None)[1]
    check('canceling the folder chooser cancels the quit', window.close() is False and window.isVisible() and
          all(os.path.exists(f) for f in mine) and len(asked_where) == 1, asked_where)
    g['ask_keep_folder'] = lambda parent: dest
    check('choosing a folder lets the quit go ahead', window.close() is True and not window.isVisible())
    folders = [d for d in os.listdir(dest) if d.startswith('mandelbrot-')]
    check('the files went into one new dated folder inside it', len(folders) == 1, os.listdir(dest))
    kept_dir = os.path.join(dest, folders[0])
    check('the pictures were kept (as PNGs) and the count files were not', sorted(os.listdir(kept_dir)) == expected_names,
          (sorted(os.listdir(kept_dir)), expected_names))
    pics_ok, meta_ok = True, True
    for name, img in images_before.items():
        item = items_before[name]
        got = os.path.join(kept_dir, name[:-4] + '.png' if item else name)
        pics_ok = pics_ok and same_pixels(QtGui.QImage(got), img)
        if item:
            view = parse_view(read_png_text(got))
            meta_ok = meta_ok and (view['x'], view['y'], view['w']) == (Decimal(item.xywd.x), Decimal(item.xywd.y), Decimal(item.xywd.w)) \
                and view['multiplier'] == g['MULTIPLIERS'][int(item.xywd.d)]
    check('every kept picture shows the same image as the original', pics_ok)
    check('every kept PNG describes its view (coordinates and multiplier)', meta_ok)
    check('no temporary files were left in the kept folder', not [n for n in os.listdir(kept_dir) if n.endswith('.part')])
    check('they are gone from pix/ (pictures moved, counts deleted)', not g['generated_files'](pix_dir) and not any(os.path.exists(f) for f in mine))
    check('nothing already in the chosen folder was touched', open(precious, 'rb').read() == b'already here')
    check('whole.bmp and unrelated files stayed in pix/', all(os.path.exists(f) for f in guard))
    # the same on Reset (the opening view's files stay, since the reset needs them)
    window.show()
    g['on_reset']()
    for _ in range(2):
        release(g, 300, 500, 600)
        g['on_run']()
    old = g['generated_files'](pix_dir, opening=False)
    expected_reset = sorted(kept_name(f) for f in old if f.endswith('.bmp'))
    opening_now = [f for f in g['generated_files'](pix_dir) if f not in old]
    answer('keep')
    g['ask_keep_folder'] = lambda parent: None
    g['on_reset']()
    check('canceling the folder chooser cancels the reset', len(list(MAP)) == 3 and all(os.path.exists(f) for f in old), len(list(MAP)))
    g['ask_keep_folder'] = lambda parent: dest
    g['on_reset']()
    folders = sorted(d for d in os.listdir(dest) if d.startswith('mandelbrot-'))
    check('Keep all on Reset keeps the old views\' pictures as PNGs, drops their counts, and resets', len(folders) == 2 and len(list(MAP)) == 1 and
          not any(os.path.exists(f) for f in old) and
          sorted(os.listdir(os.path.join(dest, folders[-1]))) == expected_reset,
          (folders, len(list(MAP)), sorted(os.listdir(os.path.join(dest, folders[-1])))))
    check('the opening view\'s files were not moved', all(os.path.exists(f) for f in opening_now), opening_now)
    g['ask_keep_folder'] = lambda parent: g['PIX_DIR']
    asked.clear()

    # -- the real dialog: its three buttons give the three answers
    g['ask_cleanup'] = real_ask
    window.show()
    for label, want in (('Keep all\u2026', 'keep'), ('Delete all', 'delete'), ('Cancel', 'cancel')):
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
