#!/usr/bin/env python3
import os
from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSlot
from PyQt5.QtGui import QColor, QIcon, QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QColorDialog, QComboBox, QDial, QDoubleSpinBox, QSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QRubberBand, QScrollArea, QShortcut, QSizePolicy, QSplitter,
                             QVBoxLayout, QWidget)
from sys import argv, exit, stderr
from subprocess import call, run as run_process     # `run` is the Run button below
import shutil
from collections import namedtuple
from math import ceil
from configparser import ConfigParser
from optparse import OptionParser
from decimal import Decimal
from cleanup import delete_files, generated_files, move_files, new_folder, split_images, view_files, remove_stale_references, size_text, total_size
from meta import parse_view, read_png_text, view_text
from deepzoom import abbreviate, ITERATIONS, WIDTH, HEIGHT, PERTURB_BELOW, POWER_MIN_DEGREE, POWER_MAX_DEGREE, selection_to_region, write_reference
from funcspec import write_power_spec


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
# bin_dir is where `mand-gpu` and pix/ live; it defaults to this script's directory
BIN_DIR = paths.get('bin_dir', os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = paths.get('save_dir', os.path.expanduser('~'))
# renderer is the program in bin_dir that draws the images: `mand-gpu` (CUDA) or `mand-cpu` (no GPU)
def resolve_renderer(name):
    """The renderer's program name. `mand` is what mand-gpu used to be called, so older ini files still work."""
    return 'mand-gpu' if name == 'mand' else name


RENDERER = resolve_renderer(paths.get('renderer', 'mand-gpu'))
PIX_DIR = os.path.join(BIN_DIR, 'pix')
STARTFILE = os.path.join(PIX_DIR, 'whole.bmp')
# colorize recolors a saved image (the renderer's smooth iteration counts) without rendering again
COLORIZE = os.path.join(BIN_DIR, 'colorize')
FALLBACK_PALETTES = ['twilight', 'fire', 'ocean', 'aurora', 'ice', 'sunset', 'gray', 'rainbow', 'classic']
MAPPINGS = ['histogram', 'linear', 'log']
RESET_COORDS = (Decimal('-2.75'), Decimal('-1.333333'), Decimal('4.0'), 0)
# Iteration multipliers offered (limit = ITERATIONS * multiplier). Deep views need many more
# iterations than shallow ones; the large values are only practical with the BLA speedup, and a view with
# much of its area inside the set will take very long to draw at the top of the range.
MULTIPLIERS = list(range(1, 31)) + [40, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 2000, 5000, 10000, 20000, 50000,
                                    100000, 200000, 500000, 1000000, 2000000, 5000000, 10000000, 20000000]
PIX_WID = WIDTH
PIX_HGT = HEIGHT
WIN_WID = 1460
WIN_HGT = 950
TN_WID = 160
TN_HGT = 120
# the picture may be cropped by up to this fraction of its width or height to fill a window of another shape
MAX_CROP = 0.15
# width of the column of controls beside the picture
SIDE_WID = 290
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
QSplitter::handle:vertical { background-color: #555; margin: 2px 30px; border-radius: 1px; }
QSplitter::handle:vertical:hover { background-color: #8a8a8a; }
QPushButton:checked { background-color: #5a6e8c; border-color: #8aa0c0; }
QPushButton#thumbclose { padding: 0; background-color: rgba(0, 0, 0, 170); border: 1px solid #999; border-radius: 9px; color: #eee; font-weight: bold; }
QPushButton#thumbclose:hover { background-color: #b03a3a; border-color: #eee; }
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


# Each view is identified by the file name its render was written to. Recoloring replaces that file in
# place, so no extra files pile up; SHOWN says which file is displayed for a view. The opening view is
# the exception: its shipped image (whole.bmp) is never overwritten, a copy (whole-start.bmp) is shown.
SHOWN = {}
START_COPY = os.path.join(PIX_DIR, 'whole-start.bmp')


def load_pixmap(path):
    """Read an image fresh from disk (QPixmap(path) may hand back a cached copy of a file we just replaced)."""
    return QPixmap.fromImage(QImage(path))


# The color settings each view's image was last drawn with (saved into its PNG).
VIEW_COLORS = {}


Colors = namedtuple('Colors', ('palette', 'mapping', 'scale', 'shift', 'gamma', 'brightness', 'contrast', 'interior'))
INTERIOR_DEFAULT = '000000'
DEFAULT_COLORS = Colors('gray', 'histogram', 0.0, 0.0, 1.0, 0.0, 0.0, INTERIOR_DEFAULT)     # how every color control starts


def current_colors():
    return Colors(pal_box.currentText(), map_box.currentText(), scale_box.value(), shift_box.value(), gamma_box.value(),
                  brightness_box.value(), contrast_box.value(), interior_hex())


def remember(fname):
    """Record what the controls now show as the color settings of this view (what its picture was last drawn with)."""
    VIEW_COLORS[fname] = current_colors()


def recorded(fname):
    """The color settings recorded for this view, or None if it has none."""
    return VIEW_COLORS.get(fname)


def forget(fname):
    VIEW_COLORS.pop(fname, None)
    VIEW_FUNC.pop(fname, None)


def forget_all_but(keep):
    for key in [k for k in VIEW_COLORS if k != keep]:
        del VIEW_COLORS[key]
    for key in [k for k in VIEW_FUNC if k != keep]:
        del VIEW_FUNC[key]


# The function each view was drawn with, as the exponent d of z^d + c (2 is the ordinary Mandelbrot set). A view
# with no entry was drawn with 2.
VIEW_FUNC = {}
FUNC_DEFAULT = 2


def current_degree():
    return FUNC_DEFAULT if func_box.currentIndex() == 0 else power_box.value()


def remember_func(fname):
    VIEW_FUNC[fname] = current_degree()


def recorded_func(fname):
    return VIEW_FUNC.get(fname, FUNC_DEFAULT)


def set_function_controls(degree):
    """Show this function in the Function box without drawing anything."""
    for box in (func_box, power_box):
        box.blockSignals(True)
    func_box.setCurrentIndex(0 if degree == FUNC_DEFAULT else 1)
    power_box.setValue(max(degree, POWER_MIN_DEGREE))
    power_box.setEnabled(degree != FUNC_DEFAULT)
    for box in (func_box, power_box):
        box.blockSignals(False)


def on_func_changed(*_):
    """A new function is chosen: it applies to the next Run (which draws a new view), not to the picture on screen."""
    power_box.setEnabled(func_box.currentIndex() == 1)


def interior_hex():
    return interior_btn.property('hex')


def show_interior(hexcolor):
    """Show a color on the Interior button (without recoloring anything)."""
    c = QColor('#' + hexcolor)
    interior_btn.setProperty('hex', hexcolor)
    interior_btn.setText('#' + hexcolor)
    light = c.lightness() > 128
    interior_btn.setStyleSheet('QPushButton {{ background-color: #{}; color: {}; border: 1px solid #888; }}'.format(
        hexcolor, '#000' if light else '#fff'))


def set_color_controls(palette, mapping, scale, shift, gamma=1.0, brightness=0.0, contrast=0.0, interior=INTERIOR_DEFAULT):
    """Show these color settings in the Colors box without recoloring anything (the picture already has them)."""
    boxes = (pal_box, map_box, scale_box, shift_box, gamma_box, brightness_box, contrast_box)
    for box in boxes:
        box.blockSignals(True)
    if pal_box.findText(palette) >= 0:
        pal_box.setCurrentText(palette)
    map_box.setCurrentText(mapping)
    update_scale_step()
    scale_box.setValue(scale)
    shift_box.setValue(shift)
    gamma_box.setValue(gamma)
    brightness_box.setValue(brightness)
    contrast_box.setValue(contrast)
    show_interior(interior)
    for box in boxes:
        box.blockSignals(False)


def choose_interior():
    """The Interior button: pick the color of the pixels inside the set."""
    start = QColor('#' + interior_hex())
    if start.value() == 0:
        # the dialog takes brightness from its slider, not from the spectrum: opened on black, every spectrum click would still give black
        start = QColor.fromHsv(0, 0, 255)
    chosen = QColorDialog.getColor(start, window, 'Interior color')
    if chosen.isValid() and chosen.name()[1:] != interior_hex():
        show_interior(chosen.name()[1:])
        on_color_change()


def view_meta(item):
    """The text fields describing a view, for its PNG."""
    colors = recorded(item.fname) or current_colors()
    x, y, w, d = item.xywd
    return view_text(x, y, w, MULTIPLIERS[int(d)], *colors, degree=recorded_func(item.fname))


def write_png(item, source, target):
    """Save the picture in `source` as a PNG carrying the view's description. Returns an error message or None.
    Written under a temporary name and moved into place, so a failure never leaves a broken file."""
    img = QImage(source)
    if img.isNull():
        return 'cannot read {}'.format(source)
    for key, value in view_meta(item).items():
        img.setText(key, value)
    part = target + '.part'
    if not img.save(part, 'PNG'):
        if os.path.exists(part):
            os.remove(part)
        return 'cannot write {}'.format(target)
    try:
        os.replace(part, target)
    except OSError as e:
        if os.path.exists(part):
            os.remove(part)
        return '{}: {}'.format(target, e)
    return None


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
    if gamma_box.value() != 1:
        opts.append('--gamma={:g}'.format(gamma_box.value()))
    if brightness_box.value() != 0:
        opts.append('--brightness={:g}'.format(brightness_box.value()))
    if contrast_box.value() != 0:
        opts.append('--contrast={:g}'.format(contrast_box.value()))
    if interior_hex() != INTERIOR_DEFAULT:
        opts.append('--interior=' + interior_hex())
    return opts


def recolor(item):
    """Redraw a view with the current color settings from its saved counts, replacing its image file.
    True if it was recolored."""
    nu = nu_name(item.fname)
    if not (os.path.exists(nu) and os.access(COLORIZE, os.X_OK)):
        return False
    out = START_COPY if item.fname == STARTFILE else item.fname
    new = out + '.new'      # written beside it and moved into place, so a failure leaves the old image intact
    res = run_process([COLORIZE, nu, new] + color_options(), capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(new):
        if os.path.exists(new):
            os.remove(new)
        QMessageBox.warning(window, 'Recolor failed', (res.stderr or 'colorize failed').strip())
        return False
    os.replace(new, out)
    SHOWN[item.fname] = out
    remember(item.fname)
    item.icon.setIcon(QIcon(load_pixmap(out)))
    return True


def with_restore(box, button):
    """A spin box with its restore button beside it, for a row of the Colors form."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    row.addWidget(box, 1)
    row.addWidget(button)
    return row


def on_color_change(*_):
    """A color control changed: recolor the view on screen at once (new renders use the settings too)."""
    with WaitCurs():
        if recolor(MAP.curr):
            reg.setPixmap(load_pixmap(image_path(MAP.curr)))


def ask_cleanup(parent, count, size, reset=False):
    """Ask whether to delete generated files: 'keep', 'delete' or 'cancel' (stay open / do not reset)."""
    if reset:
        title = 'Reset: delete old files?'
        text = ('Reset clears your zoom history. {} files ({}) in {} belong to views you can no longer go back to.'
                '\n\nDelete them? Copies you saved with Save are never touched.')
        more = ('Keeping lets you choose a folder: the pictures are moved there and the raw count files (which only serve '
                'recoloring) are deleted. Choose pix/ itself to leave everything as it is; later renders reuse the names.')
    else:
        title = 'Delete generated files?'
        text = '{} generated files ({}) are in {}.\n\nDelete them? Copies you saved with Save are never touched.'
        more = 'Keeping lets you choose a folder: the pictures are moved there and the raw count files (which only serve recoloring) are deleted. Choose pix/ itself to leave everything as it is.'
    box = QMessageBox(QMessageBox.Question, title, text.format(count, size_text(size), PIX_DIR), QMessageBox.NoButton, parent)
    box.setInformativeText(more)
    keep = box.addButton('Keep all\u2026', QMessageBox.AcceptRole)
    delete = box.addButton('Delete all', QMessageBox.DestructiveRole)
    cancel = box.addButton('Cancel', QMessageBox.RejectRole)
    box.setDefaultButton(keep)
    box.setEscapeButton(cancel)
    box.exec_()
    clicked = box.clickedButton()
    return 'keep' if clicked is keep else 'delete' if clicked is delete else 'cancel'


def ask_keep_folder(parent):
    """Ask where to keep the files: a folder path, or None if the user canceled."""
    folder = QFileDialog.getExistingDirectory(parent, 'Move the files to which folder?', SAVE_DIR)
    return folder or None


def offer_cleanup(files, reset=False):
    """Let the user delete `files`, or keep them (moved to a folder of their choosing). False if they canceled."""
    if not files:
        return True
    choice = ask_cleanup(window, len(files), total_size(files), reset=reset)
    if choice == 'cancel':
        return False
    if choice == 'delete':
        failed = delete_files(files)
        if failed:
            QMessageBox.warning(window, 'Delete generated files', '{} files could not be deleted.'.format(failed))
    else:
        folder = ask_keep_folder(window)
        if folder is None:
            return False        # no place chosen: do not quit or reset after all
        if os.path.realpath(folder) != os.path.realpath(PIX_DIR):      # choosing pix/ itself leaves them where they are
            images, counts = split_images(files)
            where = new_folder(folder)
            failed = delete_files(counts)           # the raw counts are not worth keeping
            for path in images:
                item = MAP[STARTFILE] if path == START_COPY else MAP[path]
                if item is not None and path == image_path(item):
                    # a picture of a view in this session becomes a PNG that remembers the view; the original goes
                    if write_png(item, path, os.path.join(where, os.path.basename(path)[:-4] + '.png')):
                        failed += 1
                    else:
                        failed += delete_files([path])
                else:
                    try:                                 # (left over from an earlier session: nothing to say what it shows)
                        shutil.move(path, os.path.join(where, os.path.basename(path)))
                    except (OSError, shutil.Error):
                        failed += 1
            if failed:
                QMessageBox.warning(window, 'Keep generated files',
                                    '{} files could not be moved or deleted (the folder is {}).'.format(failed, where))
    return True


def on_quit():
    """Called as the window closes. True to go ahead and quit, False if the user chose to stay."""
    remove_stale_references(PIX_DIR)
    files = generated_files(PIX_DIR)
    if not generated_files(PIX_DIR, opening=False):
        delete_files(files)     # only the opening view's files are left (Reset keeps them): cheap to redraw, not worth asking about
        return True
    return offer_cleanup(files)


class MainWindow(QWidget):
    def closeEvent(self, event):
        if on_quit():
            event.accept()
        else:
            event.ignore()


def ensure_start_image():
    """Draw the opening view with the current palette, if the renderer is there to produce its counts."""
    nu = nu_name(STARTFILE)
    if not os.path.exists(nu):
        start = START_COPY
        x, y, w, d = RESET_COORDS
        try:
            call([os.path.join(BIN_DIR, RENDERER), str(x), str(y), str(w), start, '1', '--nu-out=' + nu] + color_options())
        except OSError:
            return
        if os.path.exists(nu):
            SHOWN[STARTFILE] = start
    if os.path.exists(nu):
        recolor(INITPG)


class Thumb(QPushButton):
    """A history thumbnail. Its tiny x (shown only while it is the selected one) deletes the view and its files."""

    def __init__(self):
        QPushButton.__init__(self)
        self.closer = QPushButton('\u00d7', self)
        self.closer.setObjectName('thumbclose')
        self.closer.setFixedSize(18, 18)
        self.closer.setToolTip('Delete this view and its files')
        self.closer.hide()

    def resizeEvent(self, event):
        QPushButton.resizeEvent(self, event)
        self.closer.move(self.width() - self.closer.width() - 4, 4)


def get_tnail(fname):
    button = Thumb()
    button.closer.clicked.connect(lambda: on_delete_view(fname))
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

    def update(self, pg, d):
        """Record a different iteration multiplier for an existing view (re-rendered in place)."""
        global INITPG
        new = pg._replace(xywd=pg.xywd._replace(d=d))
        if pg.fname == INITPG.fname:
            INITPG = new        # (Reset starts from it again)
        self._map[pg.fname] = new
        if self._current.fname == pg.fname:
            self._current = new
        return new

    def delete(self, pg):
        """Drop a view from the history. Views that were zoomed from it now hang from its parent, so Back still works.
        Returns the view to show instead (its parent)."""
        for name, child in list(self._map.items()):
            if child.parent == pg.fname:
                self._map[name] = child._replace(parent=pg.parent)
        del self._map[pg.fname]
        self._current = self._map[pg.parent]
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
        """The view this one was zoomed from. Deleting a view hangs its children from its parent, so this is
        always the next real view back; a parent that somehow no longer exists falls back to the opening view."""
        if self._current.parent:
            self._current = self._map.get(self._current.parent) or self._map[INITPG.fname]
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
    """The image view. The picture is scaled up evenly (never stretched) to fill the label and centered in it, so a
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


# What Scale means differs by mapping, so its arrow buttons step by an amount that suits the mapping: about 1 to 2% of the
# mapping's own starting value (see README). `start` is that starting value, which "default" stands for.
SCALE_STEPS = {'histogram': (2.5, 0.05), 'linear': (50.0, 0.5), 'log': (0.6, 0.01)}


class ScaleBox(QDoubleSpinBox):
    start = 1.0

    def stepBy(self, steps):
        if self.value() == 0:
            # showing "default": the first click moves from the mapping's own value, not from 0
            self.setValue(max(self.minimum() + self.singleStep(), self.start + steps * self.singleStep()))
        else:
            super().stepBy(steps)


def update_scale_step():
    """Make Scale's arrows suit the mapping now chosen."""
    scale_box.start, scale_box.step = SCALE_STEPS[map_box.currentText()]
    scale_box.setSingleStep(scale_box.step)


class SplitPanes(object):
    """Keeps the Controls and Images buttons in step with the bar between the two parts of the side column:
    each button shows or hides its part, dragging the bar all the way to an end hides that part (and
    unchecks its button), and one part is always showing."""
    MIN = 100           # a part dragged smaller than this closes (it would show next to nothing)

    def __init__(self, splitter, controls_btn, images_btn):
        self.split = splitter
        self.buttons = (controls_btn, images_btn)
        self.shares = None      # how the height was last divided between the two while both showed

    def total(self):
        return max(1, sum(self.split.sizes()))

    def set_sizes(self, controls, images):
        self.split.setSizes([controls, images])

    def toggled(self, which, on):
        other = self.buttons[1 - which]
        if not on and not other.isChecked():
            self.buttons[which].setChecked(True)        # never hide both parts
            return
        total = self.total()
        if self.buttons[0].isChecked() and self.buttons[1].isChecked():
            first = self.shares if self.shares is not None else self.preferred(total)
            self.set_sizes(first, total - first)
        elif self.buttons[0].isChecked():
            self.set_sizes(total, 0)
        else:
            self.set_sizes(0, total)

    def preferred(self, total):
        """The height for the controls when both parts show and nothing has been chosen: all they need, up to 60%."""
        need = self.split.widget(0).widget().sizeHint().height() + 4
        return max(self.MIN, min(need, int(total * 0.6)))

    def moved(self, *_):
        sizes = self.split.sizes()
        if sizes[0] < self.MIN and sizes[1] >= self.MIN:
            sizes = [0, sum(sizes)]
        elif sizes[1] < self.MIN and sizes[0] >= self.MIN:
            sizes = [sum(sizes), 0]
        elif sizes[0] < self.MIN and sizes[1] < self.MIN:
            sizes = [sum(sizes), 0]
        for button, size in zip(self.buttons, sizes):
            button.blockSignals(True)
            button.setChecked(size > 0)
            button.blockSignals(False)
        if min(sizes) > 0:
            self.shares = sizes[0]
        else:
            self.split.setSizes(sizes)


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
    set_function_controls(recorded_func(item.fname))
    if recorded(item.fname):                    # every control describes this view, not whatever was used before
        set_color_controls(*recorded(item.fname))
    reg.setPixmap(load_pixmap(image_path(item)))
    for mem in MAP:
        mem.icon.setFlat(True)
        mem.icon.closer.hide()
    item.icon.setFlat(False)
    item.icon.closer.setVisible(item.parent is not None)      # (the opening view cannot be deleted)
    MAP.set(item)


def confirm_delete(parent, count, size):
    """Ask before deleting a view's files for good."""
    box = QMessageBox(QMessageBox.Question, 'Delete this view?',
                      'Delete this view and its {} files ({})?\n\nThis cannot be undone. Pictures you saved with Save are not touched.'.format(
                          count, size_text(size)), QMessageBox.NoButton, parent)
    delete = box.addButton('Delete', QMessageBox.DestructiveRole)
    cancel = box.addButton('Cancel', QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec_()
    return box.clickedButton() is delete


def on_delete_view(fname):
    """The x on the selected thumbnail: delete that view, its files and its thumbnail, and show its parent."""
    item = MAP[fname]
    if item is None or item.parent is None:         # the opening view stays
        return
    files = view_files(os.path.dirname(item.fname), item.fname)
    if not confirm_delete(window, len(files), total_size(files)):
        return
    with WaitCurs():
        failed = delete_files(files)
        parent = MAP.delete(item)
        scr_layout.removeWidget(item.icon)
        item.icon.setParent(None)
        item.icon.deleteLater()
        SHOWN.pop(item.fname, None)
        forget(item.fname)
        fset(parent)
    if failed:
        QMessageBox.warning(window, 'Delete view', '{} files could not be deleted.'.format(failed))


@pyqtSlot()
def on_reset():
    global INITPG
    remove_stale_references(PIX_DIR)
    if not offer_cleanup(generated_files(PIX_DIR, opening=False), reset=True):
        return          # the user canceled the reset
    with WaitCurs():
        for i in reversed(range(scr_layout.count()-1)): 
            scr_layout.itemAt(i).widget().setParent(None)
        for key in [k for k in SHOWN if k != STARTFILE]:
            del SHOWN[key]       # those file names will be rendered afresh
        forget_all_but(STARTFILE)
        # every control goes back to its starting position, and the opening view is drawn to match
        set_color_controls(*DEFAULT_COLORS)
        set_function_controls(FUNC_DEFAULT)
        remember(STARTFILE)
        remember_func(STARTFILE)
        if INITPG.xywd.d != 0:          # the opening view was redrawn with more iterations: draw it afresh with the starting ones
            INITPG = INITPG._replace(xywd=INITPG.xywd._replace(d=0))
            SHOWN.pop(STARTFILE, None)
            for path in (START_COPY, nu_name(STARTFILE)):
                if os.path.exists(path):
                    os.remove(path)
        ensure_start_image()            # recolors the opening view, or draws it if its counts are gone
        fset(MAP.reset())               # (this also puts the coordinates, the multiplier and the dial back)


def render_view(out, nu, xval, yval, wval, ival, degree=FUNC_DEFAULT):
    """Run the renderer for a view, writing the image to `out` and its counts to `nu`. Returns a problem
    description, or None on success."""
    cmd = [os.path.join(BIN_DIR, RENDERER), xval, yval, wval, out, ival]
    refname = specname = None
    if degree != FUNC_DEFAULT:
        specname = out + '.func'
        write_power_spec(specname, degree)
    if Decimal(wval) < PERTURB_BELOW:
        # Too deep for plain double: render by perturbation off an arbitrary-precision reference orbit.
        refname = out + '.ref'
        write_reference(refname, xval, yval, wval, ITERATIONS * int(ival), degree)
        cmd.append(refname)
    cmd += color_options() + ['--nu-out=' + nu]
    if specname:
        cmd.append('--func=' + specname)     # options may follow the positional arguments
    problem = None
    try:
        status = call(cmd)
        if status != 0:
            problem = '{} exited with status {}'.format(RENDERER, status)
    except OSError as e:     # e.g. the renderer is not built or not executable
        problem = 'cannot run {}: {}'.format(cmd[0], e)
    finally:
        for temporary in (refname, specname):
            if temporary and os.path.exists(temporary):
                os.remove(temporary)
    return problem


def same_region(a, b):
    return Decimal(a.x) == Decimal(b.x) and Decimal(a.y) == Decimal(b.y) and Decimal(a.w) == Decimal(b.w)


def rerender_in_place(item, xval, yval, wval, ival, degree=FUNC_DEFAULT):
    """Draw the current view again (for instance with a different iteration limit), replacing its image and counts
    instead of adding a new view. The new files are written beside the old and moved into place on success."""
    out = START_COPY if item.fname == STARTFILE else item.fname      # (the shipped whole.bmp is never overwritten)
    nu = nu_name(item.fname)
    problem = render_view(out + '.new', nu + '.new', xval, yval, wval, ival, degree)
    if not problem and not (os.path.exists(out + '.new') and os.path.exists(nu + '.new')):
        problem = '{} did not write its output'.format(RENDERER)
    if problem:
        for leftover in (out + '.new', nu + '.new'):
            if os.path.exists(leftover):
                os.remove(leftover)
        return problem
    os.replace(out + '.new', out)
    os.replace(nu + '.new', nu)
    SHOWN[item.fname] = out
    remember(item.fname)
    remember_func(item.fname)
    item = MAP.update(item, inter.currentIndex())
    item.icon.setIcon(QIcon(load_pixmap(out)))
    fset(item)
    return None


@pyqtSlot()
def on_run():
    global MAP
    with WaitCurs():
        reg.cand_xyw.d = inter.currentIndex()
        xval = exact(xbox)
        yval = exact(ybox)
        wval = exact(wbox)
        ival = inter.currentText()
        degree = current_degree()
        if same_region(reg.cand_xyw, MAP.curr.xywd) and degree == recorded_func(MAP.curr.fname):
            # no new selection: this is the same view, so redraw it in place rather than pile up copies
            problem = rerender_in_place(MAP.curr, xval, yval, wval, ival, degree)
        else:     # (another function over the same region is a new view too, so the earlier picture stays in the history)
            problem = render_view(MAP.fname, nu_name(MAP.fname), xval, yval, wval, ival, degree)
            if not problem:
                SHOWN.pop(MAP.fname, None)      # a fresh render replaces any earlier recoloring of this file name
                MAP.add(XYWD(reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w, int(reg.cand_xyw.d)))
                remember(MAP.curr.fname)
                remember_func(MAP.curr.fname)
                scr_layout.insertWidget(0, MAP.curr.icon)
                fset(MAP.curr)
        if problem:
            stderr.write(problem + '\n')
            QMessageBox.warning(window, 'Render failed', problem)


@pyqtSlot()
def on_save():
    """Save the picture on screen as a PNG that remembers its view (coordinates, iterations, colors)."""
    dlg = QFileDialog(window, 'Save File', SAVE_DIR, 'PNG images (*.png)')
    dlg.setFileMode(QFileDialog.AnyFile)
    if not dlg.exec_():
        return
    with WaitCurs():
        target = str(dlg.selectedFiles()[0])
        if not target.lower().endswith('.png'):
            target = '%s.png' % target
        error = write_png(MAP.curr, image_path(MAP.curr), target)
    if error:
        QMessageBox.warning(window, 'Save failed', error)


@pyqtSlot()
def on_open():
    """Open a PNG saved by this program: draw the view it describes as a new view, with its colors."""
    dlg = QFileDialog(window, 'Open a saved view', SAVE_DIR, 'PNG images (*.png)')
    dlg.setFileMode(QFileDialog.ExistingFile)
    if not dlg.exec_():
        return
    path = str(dlg.selectedFiles()[0])
    if not path.lower().endswith('.png'):         # only PNG files, whatever the file chooser let through
        QMessageBox.warning(window, 'Cannot open {}'.format(os.path.basename(path)), 'only PNG files can be opened')
        return
    try:
        view = parse_view(read_png_text(path))      # (also refuses a file that is named .png but is not one)
    except (OSError, ValueError) as e:
        QMessageBox.warning(window, 'Cannot open {}'.format(os.path.basename(path)), str(e))
        return
    if view['multiplier'] not in MULTIPLIERS:
        QMessageBox.warning(window, 'Cannot open {}'.format(os.path.basename(path)),
                            'the iteration multiplier {} is not one this program offers'.format(view['multiplier']))
        return
    set_color_controls(view['palette'], view['mapping'], view['scale'], view['shift'], view['gamma'], view['brightness'],
                       view['contrast'], view['interior'])      # (the controls change without recoloring the view on screen first)
    set_function_controls(view['degree'])
    reg.cand_xyw.x, reg.cand_xyw.y, reg.cand_xyw.w = view['x'], view['y'], view['w']
    show_coords(view['x'], view['y'], view['w'])
    inter.setCurrentIndex(MULTIPLIERS.index(view['multiplier']))
    on_run()


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
    remove_stale_references(PIX_DIR)
    INITPG = PGINFO(XYWD_RESET, STARTFILE, get_tnail(STARTFILE), None)
    MAP = MTree()
    window = MainWindow()
    reg = PicRegion()
    reg.setPixmap(QPixmap(STARTFILE))
    run = QPushButton('Run') 
    run.clicked.connect(on_run)
    run.setToolTip('Render the selected region (Enter)')
    # Enter (the main key and the keypad's) presses Run from anywhere in the window; a held key does not repeat it
    run_keys = []
    for key in (Qt.Key_Return, Qt.Key_Enter):
        shortcut = QShortcut(QKeySequence(key), window)
        shortcut.setAutoRepeat(False)
        shortcut.activated.connect(run.click)
        run_keys.append(shortcut)
    reset = QPushButton('Reset') 
    reset.clicked.connect(on_reset)
    reset.setToolTip('Back to the whole set, with every control at its starting setting')
    back = QPushButton('Back') 
    back.clicked.connect(on_back) 
    save = QPushButton('Save')
    save.clicked.connect(on_save)
    open_btn = QPushButton('Open a saved view\u2026')
    open_btn.clicked.connect(on_open)
    open_btn.setToolTip('Open a PNG saved by this program and draw the view it describes')
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
    func_box = QComboBox()
    func_box.addItems(['z\u00b2 + c', 'z^d + c'])
    func_box.setToolTip('The function whose set is drawn: z\u00b2 + c is the ordinary Mandelbrot set.\nPress Run to draw the chosen function as a new view.')
    func_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    func_box.setMinimumContentsLength(6)
    power_box = QSpinBox()
    power_box.setRange(POWER_MIN_DEGREE, POWER_MAX_DEGREE)
    power_box.setValue(3)
    power_box.setEnabled(False)
    power_box.setKeyboardTracking(False)
    power_box.setToolTip('The exponent d in z^d + c (whole numbers {} to {}). Press Run to apply it.'.format(POWER_MIN_DEGREE, POWER_MAX_DEGREE))
    func_box.currentIndexChanged.connect(on_func_changed)
    pal_box = QComboBox()
    pal_box.addItems(palette_names())
    pal_box.setCurrentText(DEFAULT_COLORS.palette)
    pal_box.setToolTip('Color scheme')
    map_box = QComboBox()
    map_box.addItems(MAPPINGS)
    map_box.setToolTip('histogram: spread the colors evenly over the image (any depth)\n'
                       'linear: a fixed number of iterations per color cycle\n'
                       'log: color cycles per doubling of the iteration count')
    scale_box = ScaleBox()
    scale_box.setRange(0.0, 1000000.0)
    scale_box.setDecimals(3)
    update_scale_step()
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
    gamma_box = QDoubleSpinBox()
    gamma_box.setRange(0.1, 10.0)
    gamma_box.setDecimals(2)
    gamma_box.setSingleStep(0.05)
    gamma_box.setValue(1.0)
    gamma_box.setKeyboardTracking(False)
    gamma_box.setToolTip('Bend the colors within each palette cycle.\nAbove 1 favors the start of the palette, below 1 the end; 1 changes nothing.')
    brightness_box = QDoubleSpinBox()
    brightness_box.setRange(-100.0, 100.0)
    brightness_box.setDecimals(0)
    brightness_box.setSingleStep(5.0)
    brightness_box.setKeyboardTracking(False)
    brightness_box.setToolTip('Make every palette color lighter (above 0) or darker (below 0).\nThe interior color is not changed.')
    contrast_box = QDoubleSpinBox()
    contrast_box.setRange(-100.0, 100.0)
    contrast_box.setDecimals(0)
    contrast_box.setSingleStep(5.0)
    contrast_box.setKeyboardTracking(False)
    contrast_box.setToolTip('Push the palette colors away from mid-gray (above 0) or toward it (below 0; -100 is all gray).\n'
                            'The interior color is not changed.')
    interior_btn = QPushButton()
    interior_btn.setToolTip('The color of the pixels inside the set (click to choose)')
    interior_btn.clicked.connect(choose_interior)
    show_interior(INTERIOR_DEFAULT)
    # each of the color settings below has its own button to put it back how it starts (changing the value recolors, once)
    restore_scale_btn = QPushButton('Restore')
    restore_scale_btn.setToolTip("Put Scale back to its default (the mapping's own value)")
    restore_scale_btn.clicked.connect(lambda: scale_box.setValue(0.0))
    restore_shift_btn = QPushButton('Restore')
    restore_shift_btn.setToolTip('Put Shift back to 0')
    restore_shift_btn.clicked.connect(lambda: shift_box.setValue(0.0))
    restore_gamma_btn = QPushButton('Restore')
    restore_gamma_btn.setToolTip('Put Gamma back to 1')
    restore_gamma_btn.clicked.connect(lambda: gamma_box.setValue(1.0))
    restore_brightness_btn = QPushButton('Restore')
    restore_brightness_btn.setToolTip('Put Brightness back to 0')
    restore_brightness_btn.clicked.connect(lambda: brightness_box.setValue(0.0))
    restore_contrast_btn = QPushButton('Restore')
    restore_contrast_btn.setToolTip('Put Contrast back to 0')
    restore_contrast_btn.clicked.connect(lambda: contrast_box.setValue(0.0))
    restore_interior_btn = QPushButton('Restore')
    restore_interior_btn.setToolTip('Put the interior color back to black')

    def restore_interior():
        if interior_hex() != INTERIOR_DEFAULT:
            show_interior(INTERIOR_DEFAULT)
            on_color_change()
    restore_interior_btn.clicked.connect(restore_interior)
    map_box.currentIndexChanged.connect(update_scale_step)
    for control in (pal_box, map_box):
        control.currentIndexChanged.connect(on_color_change)
    for control in (scale_box, shift_box, gamma_box, brightness_box, contrast_box):
        control.setMinimumWidth(56)         # (a spin box otherwise reserves room for the biggest number it could show)
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
    sel_box.addWidget(open_btn)
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
    color_form.addRow('Scale:', with_restore(scale_box, restore_scale_btn))
    color_form.addRow('Shift:', with_restore(shift_box, restore_shift_btn))
    color_form.addRow('Gamma:', with_restore(gamma_box, restore_gamma_btn))
    color_form.addRow('Brightness:', with_restore(brightness_box, restore_brightness_btn))
    color_form.addRow('Contrast:', with_restore(contrast_box, restore_contrast_btn))
    color_form.addRow('Interior:', with_restore(interior_btn, restore_interior_btn))
    color_group = QGroupBox('Colors')
    color_group.setLayout(color_form)
    func_form = QFormLayout()
    func_form.addRow('Function:', func_box)
    func_form.addRow('Exponent d:', power_box)
    func_group = QGroupBox('Function')
    func_group.setLayout(func_form)
    iter_form = QFormLayout()
    iter_form.addRow('Multiplier:', inter)
    iter_box = QVBoxLayout()
    iter_box.addWidget(iter_dial, 0, Qt.AlignHCenter)
    iter_box.addWidget(iter_label)
    iter_box.addLayout(iter_form)
    iter_group = QGroupBox('Iterations')
    iter_group.setLayout(iter_box)
    # The column has two parts that share its height: the controls (scrolling when they do not fit) and the
    # history thumbnails. Drag the bar between them to give either more room, or use the two buttons
    # above to show just one. The row of buttons stays in view whichever is open.
    controls_panel = QWidget()
    controls_layout = QVBoxLayout()
    controls_layout.setContentsMargins(0, 0, 4, 0)
    controls_layout.addWidget(sel_group)
    controls_layout.addWidget(func_group)
    controls_layout.addWidget(iter_group)
    controls_layout.addWidget(color_group)
    controls_layout.addStretch(1)
    controls_panel.setLayout(controls_layout)
    controls_scroll = QScrollArea()
    controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setWidget(controls_panel)
    split = QSplitter(Qt.Vertical)
    split.setChildrenCollapsible(True)
    split.setHandleWidth(7)
    split.addWidget(controls_scroll)
    split.addWidget(scroll)
    split.setStretchFactor(0, 0)
    split.setStretchFactor(1, 1)
    controls_btn = QPushButton('Controls')
    images_btn = QPushButton('Images')
    for toggle, text in ((controls_btn, 'Show or hide the controls (drag the bar below to resize them)'),
                         (images_btn, 'Show or hide the history pictures (drag the bar below to resize them)')):
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setToolTip(text)
    panes = SplitPanes(split, controls_btn, images_btn)
    controls_btn.toggled.connect(lambda on: panes.toggled(0, on))
    images_btn.toggled.connect(lambda on: panes.toggled(1, on))
    split.splitterMoved.connect(panes.moved)
    toggles = QHBoxLayout()
    toggles.setSpacing(4)
    toggles.addWidget(controls_btn)
    toggles.addWidget(images_btn)
    right = QVBoxLayout()
    right.setContentsMargins(0, 0, 0, 0)
    right.addLayout(btnbox)
    right.addLayout(toggles)
    right.addWidget(split, 1)
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
    remember_func(STARTFILE)
    remember(STARTFILE)                            # the opening view's settings are the starting ones
    ensure_start_image()
    fset(MAP.curr)
    # fit the layout (it can be enlarged; the fields grow with the window)
    hint = window.sizeHint()
    window.setMinimumSize(hint)
    window.resize(max(WIN_WID, hint.width()), hint.height())
    window.show()
    first = panes.preferred(panes.total())       # open with the controls as big as they need, up to 60% of the column
    panes.set_sizes(first, panes.total() - first)
    panes.shares = first
    exit(app.exec_())

