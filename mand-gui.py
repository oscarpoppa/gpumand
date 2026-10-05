#!/usr/bin/env python3
import os
from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (QApplication, QComboBox, QDial, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QRubberBand, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from sys import argv, exit, stderr
from subprocess import call, run as run_process     # `run` is the Run button below
from shutil import copyfile
from collections import namedtuple
from math import ceil
from configparser import ConfigParser
from optparse import OptionParser
from decimal import Decimal
from deepzoom import abbreviate, ITERATIONS, WIDTH, HEIGHT, PERTURB_BELOW, selection_to_region, write_reference


parser = OptionParser()
parser.add_option("-i", "--ini", dest="ininame", help="Supply ini file path", metavar="FILE")
(options,args) = parser.parse_args()

# a ';' or '#' after whitespace starts a comment, so `renderer=mand-cpu  ; note` still works
config = ConfigParser(inline_comment_prefixes=(';', '#'))
fname = options.ininame or 'mand-gui.ini'
try:
    config.read(fname)
    paths = config['paths']
except Exception:
    stderr.write('Something wrong with ini file: {}\n'.format(fname))
    exit(1)

TITLE = 'Mandelbrot Set Viewer'
# bin_dir is where `mand` and pix/ live; it defaults to this script's directory
BIN_DIR = paths.get('bin_dir', os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = paths.get('save_dir', os.path.expanduser('~'))
# renderer is the program in bin_dir that draws the images: `mand` (CUDA) or `mand-cpu` (no GPU)
RENDERER = paths.get('renderer', 'mand')
PIX_DIR = os.path.join(BIN_DIR, 'pix')
STARTFILE = os.path.join(PIX_DIR, 'whole.bmp')
# colorize recolors a saved image (the renderer's smooth iteration counts) without rendering again
COLORIZE = os.path.join(BIN_DIR, 'colorize')
FALLBACK_PALETTES = ['twilight', 'fire', 'ocean', 'aurora', 'ice', 'sunset', 'gray', 'rainbow', 'classic']
MAPPINGS = ['histogram', 'linear', 'log']
RESET_COORDS = (Decimal('-2.75'), Decimal('-1.333333'), Decimal('4.0'), 0)
# Iteration multipliers offered (limit = ITERATIONS * multiplier). Deep views need many more
# iterations than shallow ones; the large values are only practical with the BLA speedup.
MULTIPLIERS = list(range(1, 31)) + [40, 50, 75, 100, 150, 200, 300, 500, 750, 1000]
PIX_WID = WIDTH
PIX_HGT = HEIGHT
WIN_WID = 1460
WIN_HGT = 950
TN_WID = 160
TN_HGT = 120
# the picture may be cropped by up to this fraction of its width or height to fill a window of another shape
MAX_CROP = 0.15
# width of the column of controls beside the picture
SIDE_WID = 270
# a dark gray control area; the image is the brightest thing on screen
DARK_STYLE = """
QWidget { background-color: #2d2d2d; color: #dcdcdc; }
QGroupBox { border: 1px solid #555; border-radius: 4px; margin-top: 1.2ex; padding-top: 1ex; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
QLineEdit, QComboBox, QDoubleSpinBox { background-color: #3c3c3c; border: 1px solid #5a5a5a; border-radius: 3px; padding: 2px 4px; }
QComboBox QAbstractItemView { background-color: #3c3c3c; selection-background-color: #5a6e8c; }
QPushButton { background-color: #444; border: 1px solid #666; border-radius: 3px; padding: 3px 4px; }
QPushButton:hover { background-color: #505050; }
QPushButton:flat { background-color: transparent; border: 2px solid transparent; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #2d2d2d; width: 12px; }
QScrollBar::handle:vertical { background: #666; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background-color: #3c3c3c; color: #dcdcdc; border: 1px solid #666; }
"""

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


def render_name(n):
    return os.path.join(PIX_DIR, 'mandapp{}.bmp'.format(n))


# Each view is identified by the file name its render was written to; recoloring writes a new file
# (Qt caches pixmaps by path), and SHOWN says which file is currently displayed for a view.
SHOWN = {}
RECOLORS = [0]


def nu_name(fname):
    return fname + '.nu'


def image_path(item):
    return SHOWN.get(item.fname, item.fname)


def palette_names():
    try:
        out = run_process([COLORIZE, '--list-palettes'], capture_output=True, text=True, timeout=10)
        names = [line.split()[0] for line in out.stdout.strip().split('\n') if line.strip()]
        if out.returncode == 0 and names:
            return names
    except Exception:
        pass
    return list(FALLBACK_PALETTES)


def color_options():
    """The color settings as command line options for the renderer and for colorize."""
    opts = ['--palette=' + pal_box.currentText(), '--mapping=' + map_box.currentText()]
    if scale_box.value() > 0:
        opts.append('--scale={:g}'.format(scale_box.value()))
    if shift_box.value() != 0:
        opts.append('--shift={:g}'.format(shift_box.value()))
    return opts


def recolor(item):
    """Redraw a view with the current color settings from its saved counts. True if it was recolored."""
    nu = nu_name(item.fname)
    if not (os.path.exists(nu) and os.access(COLORIZE, os.X_OK)):
        return False
    RECOLORS[0] += 1
    out = '{}.c{}.bmp'.format(item.fname[:-4], RECOLORS[0])
    res = run_process([COLORIZE, nu, out] + color_options(), capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(out):
        QMessageBox.warning(window, 'Recolor failed', (res.stderr or 'colorize failed').strip())
        return False
    SHOWN[item.fname] = out
    pixmap = QPixmap(out)
    item.icon.setIcon(QIcon(pixmap))
    return True


def on_color_change(*_):
    """A color control changed: recolor the view on screen at once (new renders use the settings too)."""
    with WaitCurs():
        if recolor(MAP.curr):
            reg.setPixmap(QPixmap(image_path(MAP.curr)))


def ensure_start_image():
    """Draw the opening view with the current palette, if the renderer is there to produce its counts."""
    nu = nu_name(STARTFILE)
    if not os.path.exists(nu):
        start = os.path.join(PIX_DIR, 'whole-start.bmp')
        x, y, w, d = RESET_COORDS
        try:
            call([os.path.join(BIN_DIR, RENDERER), str(x), str(y), str(w), start, '1', '--nu-out=' + nu] + color_options())
        except OSError:
            return
        if os.path.exists(nu):
            SHOWN[STARTFILE] = start
    if os.path.exists(nu):
        recolor(INITPG)


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
        if pg.parent and pg.fname in self._map:
            self._current = self._map[pg.parent]
            del(self._map[pg.fname])
        return self._current

    @property
    def fname(self):
        return render_name(self._count)

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
    """The image view. The picture is scaled up evenly (never stretched) to fill the label and centred in it, so a
    bigger window gives a bigger image. To use more of a wide or tall window a little may be cropped off the edges,
    at most MAX_CROP of the picture's width or height, where there is usually only background. The selection box
    keeps the image's own shape, and mouse positions are mapped back to pixels of the real image."""

    def __init__(self, parent = None):
        QLabel.__init__(self, parent)
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.cand_xyw = LogXYW(*RESET_COORDS)
        self.source = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(PIX_WID, PIX_HGT)

    def minimumSizeHint(self):
        return QSize(PIX_WID // 3, PIX_HGT // 3)

    def setPixmap(self, pixmap):
        self.source = pixmap
        self.refit()

    def layout_image(self):
        """How the image sits in the label: (scale, scaled width, scaled height, cropped width, cropped height).

        The scale is the one that fits the whole image, raised until the label is covered or MAX_CROP of the
        image would be cut off, whichever comes first. The cropped size is the part that shows."""
        rect = self.contentsRect()
        fit = min(rect.width() / PIX_WID, rect.height() / PIX_HGT)
        cover = max(rect.width() / PIX_WID, rect.height() / PIX_HGT)
        scale = max(min(cover, fit / (1.0 - MAX_CROP)), 1e-3)
        sw, sh = max(round(PIX_WID * scale), 1), max(round(PIX_HGT * scale), 1)
        return scale, sw, sh, min(sw, rect.width()), min(sh, rect.height())

    def refit(self):
        """Show the source image as large as fits, cropped evenly at the edges if it overflows."""
        scale, sw, sh, cw, ch = self.layout_image()
        if self.source.isNull() or (sw, sh) == (self.source.width(), self.source.height()) == (cw, ch):
            QLabel.setPixmap(self, self.source)
            return
        big = self.source.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        QLabel.setPixmap(self, big.copy((sw - cw) // 2, (sh - ch) // 2, cw, ch))

    def resizeEvent(self, event):
        QLabel.resizeEvent(self, event)
        self.rubberBand.hide()
        self.refit()

    def view(self):
        """(left, top, scale): where the image's top-left corner is in the label (negative if cropped) and
        label pixels per image pixel."""
        if self.source.isNull():
            return 0, 0, 1.0
        rect = self.contentsRect()
        scale, sw, sh, cw, ch = self.layout_image()
        return (rect.x() + (rect.width() - cw) // 2 - (sw - cw) // 2,
                rect.y() + (rect.height() - ch) // 2 - (sh - ch) // 2, scale)

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
            geom = self.rubberBand.geometry()
            left, top, scale = self.view()
            pixx = round((geom.bottomLeft().x() - left) / scale)
            pixy = PIX_HGT - round((geom.bottomLeft().y() - top) / scale)
            pixw = round(geom.width() / scale)
            if pixw > 10: 
                cur = MAP.curr.xywd
                self.cand_xyw.x, self.cand_xyw.y, self.cand_xyw.w = selection_to_region(
                    cur.x, cur.y, cur.w, pixx, pixy, pixw, PIX_WID, PIX_HGT)
                self.cand_xyw.d = inter.currentIndex()
                show_coords(self.cand_xyw.x, self.cand_xyw.y, self.cand_xyw.w)


def show_coords(x, y, w):
    """Fill the read-only coordinate boxes. A very long value is shown abbreviated (leading digits, an ellipsis,
    trailing digits, and its power of ten); the exact text is kept on the box and in its tooltip."""
    for box, value in ((xbox, x), (ybox, y), (wbox, w)):
        box.setText(abbreviate(value))
        box.setToolTip(str(value))
        box.setProperty('exact', str(value))
        box.setCursorPosition(0)


def exact(box):
    """The full text of the value a coordinate box stands for."""
    return box.property('exact')


def iteration_text(index):
    mult = MULTIPLIERS[index]
    return '\u00d7{} = {:,} iterations'.format(mult, ITERATIONS * mult)


def on_inter_changed(index):
    """The multiplier box changed (by hand, by the dial, or by picking another view): update the readout and dial."""
    if index < 0:
        return
    iter_label.setText(iteration_text(index))
    if iter_dial.value() != index:
        iter_dial.setValue(index)


def on_dial_changed(value):
    if inter.currentIndex() != value:
        inter.setCurrentIndex(value)


def fset(item):
    reg.rubberBand.hide()
    show_coords(item.xywd.x, item.xywd.y, item.xywd.w)
    reg.cand_xyw.x = item.xywd.x
    reg.cand_xyw.y = item.xywd.y
    reg.cand_xyw.w = item.xywd.w
    reg.cand_xyw.d = int(item.xywd.d)
    inter.setCurrentIndex(int(item.xywd.d))
    reg.setPixmap(QPixmap(image_path(item)))
    for mem in MAP:
        mem.icon.setFlat(True)
    item.icon.setFlat(False)
    MAP.set(item)


@pyqtSlot()
def on_reset():
    with WaitCurs():
        for i in reversed(range(scr_layout.count()-1)): 
            scr_layout.itemAt(i).widget().setParent(None)
        for key in [k for k in SHOWN if k != STARTFILE]:
            del SHOWN[key]       # those file names will be rendered afresh
        fset(MAP.reset())


@pyqtSlot()
def on_run():
    global MAP
    with WaitCurs():
        reg.cand_xyw.d = inter.currentIndex()
        xval = exact(xbox)
        yval = exact(ybox)
        wval = exact(wbox)
        ival = inter.currentText()
        cmd = [os.path.join(BIN_DIR, RENDERER), xval, yval, wval, MAP.fname, ival]
        refname = None
        if Decimal(wval) < PERTURB_BELOW:
            # Too deep for plain double: render by perturbation off an arbitrary-precision reference orbit.
            refname = MAP.fname + '.ref'
            write_reference(refname, xval, yval, wval, ITERATIONS * int(ival))
            cmd.append(refname)
        cmd += color_options() + ['--nu-out=' + nu_name(MAP.fname)]     # options may follow the positional arguments
        problem = None
        try:
            status = call(cmd)
            if status != 0:
                problem = '{} exited with status {}'.format(RENDERER, status)
        except OSError as e:     # e.g. the renderer is not built or not executable
            problem = 'cannot run {}: {}'.format(cmd[0], e)
        finally:
            if refname and os.path.exists(refname):
                os.remove(refname)
        if problem:
            stderr.write(problem + '\n')
            QMessageBox.warning(window, 'Render failed', problem)
            return
        SHOWN.pop(MAP.fname, None)      # a fresh render replaces any earlier recoloring of this file name
        added = MAP.add(XYWD(reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w, int(reg.cand_xyw.d)))
        scr_layout.insertWidget(0, MAP.curr.icon)
        fset(MAP.curr) 


@pyqtSlot()
def on_save():
    dlg = QFileDialog(window, 'Save File', SAVE_DIR, 'Images (*.bmp)')
    dlg.setFileMode(QFileDialog.AnyFile)
    if not dlg.exec_():
        return
    error = None
    with WaitCurs():
        target = str(dlg.selectedFiles()[0])
        if not target.endswith('.bmp'):
            target = '%s.bmp' % target
        try:
            copyfile(image_path(MAP.curr), target)
        except OSError as e:
            error = '{}: {}'.format(target, e)
    if error:
        QMessageBox.warning(window, 'Save failed', error)


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
    inter.addItems([str(n) for n in MULTIPLIERS])
    inter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    # a dial for the iteration limit: one notch per multiplier, kept in step with the box above
    iter_dial = QDial()
    iter_dial.setRange(0, len(MULTIPLIERS) - 1)
    iter_dial.setNotchesVisible(True)
    iter_dial.setWrapping(False)
    iter_dial.setFixedSize(100, 100)
    iter_dial.setToolTip('Turn the dial (or scroll over it) to choose how many iterations to allow.\n'
                         'More iterations fill in black areas of deep views, but take longer.\nPress Run to apply it.')
    iter_label = QLabel()
    iter_label.setAlignment(Qt.AlignCenter)
    inter.currentIndexChanged.connect(on_inter_changed)
    iter_dial.valueChanged.connect(on_dial_changed)
    on_inter_changed(inter.currentIndex())
    pal_box = QComboBox()
    pal_box.addItems(palette_names())
    pal_box.setCurrentText('twilight')
    pal_box.setToolTip('Color scheme')
    map_box = QComboBox()
    map_box.addItems(MAPPINGS)
    map_box.setToolTip('histogram: spread the colors evenly over the image (any depth)\n'
                       'linear: a fixed number of iterations per color cycle\n'
                       'log: color cycles per doubling of the iteration count')
    scale_box = QDoubleSpinBox()
    scale_box.setRange(0.0, 1000000.0)
    scale_box.setDecimals(2)
    scale_box.setSingleStep(0.5)
    scale_box.setSpecialValueText('default')
    scale_box.setKeyboardTracking(False)
    scale_box.setToolTip('histogram: palette cycles across the image\nlinear: iterations per cycle\n'
                         'log: cycles per doubling\n(default: a good value for the mapping)')
    shift_box = QDoubleSpinBox()
    shift_box.setRange(-100.0, 100.0)
    shift_box.setDecimals(2)
    shift_box.setSingleStep(0.05)
    shift_box.setKeyboardTracking(False)
    shift_box.setToolTip('Rotate the palette (1 is a full turn)')
    for control in (pal_box, map_box):
        control.currentIndexChanged.connect(on_color_change)
    for control in (scale_box, shift_box):
        control.valueChanged.connect(on_color_change)
    # Everything but the picture lives in one narrow column on the right, so the picture gets the whole
    # height of the window.
    # The selection fields stack vertically, each under its label; long (deep-zoom) values scroll in the
    # box and show in full in its tooltip.
    sel_form = QFormLayout()
    sel_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
    sel_form.addRow('X coordinate (lower left):', xbox)
    sel_form.addRow('Y coordinate (lower left):', ybox)
    sel_form.addRow('Width:', wbox)
    btnbox = QHBoxLayout()
    btnbox.setSpacing(4)
    btnbox.addWidget(run)
    btnbox.addWidget(back)
    btnbox.addWidget(save)
    btnbox.addWidget(reset)
    sel_box = QVBoxLayout()
    sel_box.addLayout(sel_form)
    sel_box.addLayout(btnbox)
    sel_group = QGroupBox('Selection')
    sel_group.setLayout(sel_box)
    rside = QWidget()
    scr_layout = QVBoxLayout()
    rside.setLayout(scr_layout) 
    scroll = QScrollArea()
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidgetResizable(True)
    scroll.setWidget(rside)
    scr_layout.insertWidget(0, INITPG.icon)
    color_form = QFormLayout()
    color_form.addRow('Palette:', pal_box)
    color_form.addRow('Mapping:', map_box)
    color_form.addRow('Scale:', scale_box)
    color_form.addRow('Shift:', shift_box)
    color_group = QGroupBox('Colors')
    color_group.setLayout(color_form)
    iter_form = QFormLayout()
    iter_form.addRow('Multiplier:', inter)
    iter_box = QVBoxLayout()
    iter_box.addWidget(iter_dial, 0, Qt.AlignHCenter)
    iter_box.addWidget(iter_label)
    iter_box.addLayout(iter_form)
    iter_group = QGroupBox('Iterations')
    iter_group.setLayout(iter_box)
    right = QVBoxLayout()
    right.setContentsMargins(0, 0, 0, 0)
    right.addWidget(sel_group)
    right.addWidget(iter_group)
    right.addWidget(color_group)
    right.addWidget(scroll, 1)
    side = QWidget()
    side.setLayout(right)
    side.setFixedWidth(SIDE_WID)
    wholescr = QHBoxLayout()
    wholescr.setContentsMargins(6, 6, 6, 6)
    wholescr.addWidget(reg, 1)
    wholescr.addWidget(side)
    window.setLayout(wholescr) 
    window.setWindowTitle(TITLE)
    window.setStyleSheet(DARK_STYLE)
    ensure_start_image()
    fset(MAP.curr)
    # fit the layout (it can be enlarged; the fields grow with the window)
    hint = window.sizeHint()
    window.setMinimumSize(hint)
    window.resize(max(WIN_WID, hint.width()), hint.height())
    window.show()
    exit(app.exec_())

