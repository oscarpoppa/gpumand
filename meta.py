"""Describing a view inside the PNG saved of it, and reading that description back.

A saved picture carries its coordinates, iteration multiplier and color settings as PNG text fields, so
the GUI's Open button can redraw it. The fields are plain ASCII text; the reader here is pure Python
(no Qt) so that files can be checked, and what they claim validated, before anything is rendered.
"""
import struct
import zlib
from decimal import Decimal, InvalidOperation

PREFIX = 'mandelbrot.'
VERSION = '1'
MAPPINGS = ('histogram', 'linear', 'log')
MAX_TEXT = 5000                     # longest value accepted (a coordinate at width 1e-1000 is ~1100 characters)
MAX_EXPONENT = 5000
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def view_text(x, y, w, multiplier, palette, mapping, scale, shift, gamma=1.0, brightness=0.0, contrast=0.0,
              interior='000000'):
    """The text fields describing a view, as {key: value}."""
    return {
        'Software': 'gpumand',
        'Description': 'Mandelbrot set view: x={} y={} width={} (lower left corner)'.format(x, y, w),
        PREFIX + 'version': VERSION,
        PREFIX + 'x': str(x),
        PREFIX + 'y': str(y),
        PREFIX + 'width': str(w),
        PREFIX + 'multiplier': str(int(multiplier)),
        PREFIX + 'palette': str(palette),
        PREFIX + 'mapping': str(mapping),
        PREFIX + 'scale': '{:g}'.format(float(scale)),
        PREFIX + 'shift': '{:g}'.format(float(shift)),
        PREFIX + 'gamma': '{:g}'.format(float(gamma)),
        PREFIX + 'brightness': '{:g}'.format(float(brightness)),
        PREFIX + 'contrast': '{:g}'.format(float(contrast)),
        PREFIX + 'interior': str(interior),
    }


def read_png_text(path):
    """All the text fields of a PNG file (tEXt, zTXt and iTXt chunks) as {key: value}; later duplicates are ignored.
    Raises ValueError if the file is not a PNG."""
    out = {}
    with open(path, 'rb') as fp:
        if fp.read(8) != PNG_SIGNATURE:
            raise ValueError('not a PNG image')
        while True:
            head = fp.read(8)
            if len(head) < 8:
                break
            length, kind = struct.unpack('>I4s', head)
            if length > 1 << 28:
                raise ValueError('damaged PNG image')
            if kind not in (b'tEXt', b'zTXt', b'iTXt'):
                if kind == b'IEND':
                    break
                fp.seek(length + 4, 1)                           # the picture itself (and its CRC) is not needed
                continue
            data = fp.read(length)
            fp.read(4)                                           # CRC
            if len(data) < length:
                raise ValueError('damaged PNG image')
            try:
                if kind == b'tEXt':
                    key, _, value = data.partition(b'\0')
                    out.setdefault(key.decode('latin-1'), value.decode('latin-1'))
                elif kind == b'zTXt':
                    key, _, rest = data.partition(b'\0')
                    out.setdefault(key.decode('latin-1'), zlib.decompress(rest[1:]).decode('latin-1'))
                elif kind == b'iTXt':
                    key, _, rest = data.partition(b'\0')
                    compressed = rest[0]
                    rest = rest[2:]                              # skip the flags
                    _, _, rest = rest.partition(b'\0')           # language tag
                    _, _, text = rest.partition(b'\0')           # translated keyword
                    out.setdefault(key.decode('latin-1'), (zlib.decompress(text) if compressed else text).decode('utf-8'))
            except (zlib.error, UnicodeDecodeError, IndexError):
                continue
    return out


def _decimal(text, name):
    if not text or len(text) > MAX_TEXT:
        raise ValueError('{} is missing or too long'.format(name))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError('{} is not a number'.format(name))
    if not value.is_finite() or abs(value.adjusted()) > MAX_EXPONENT:
        raise ValueError('{} is out of range'.format(name))
    return value


def _float(text, name):
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError('{} is not a number'.format(name))
    if value != value or abs(value) > 1e9:
        raise ValueError('{} is out of range'.format(name))
    return value


def parse_view(text):
    """Check the text fields of a saved view and return them as a dict (x, y, w as Decimals, multiplier an int,
    palette, mapping, scale, shift, gamma, brightness, contrast, interior). Raises ValueError, with a message fit to show the user, if it is not a
    view this program saved or any field is unusable."""
    if text.get(PREFIX + 'version') is None:
        raise ValueError('this image has no saved Mandelbrot view in it (only images saved by this program do)')
    if text[PREFIX + 'version'] != VERSION:
        raise ValueError('this image was saved by a newer version of the program (format {})'.format(text[PREFIX + 'version']))
    x = _decimal(text.get(PREFIX + 'x'), 'x')
    y = _decimal(text.get(PREFIX + 'y'), 'y')
    w = _decimal(text.get(PREFIX + 'width'), 'width')
    if w <= 0:
        raise ValueError('width must be positive')
    try:
        multiplier = int(text.get(PREFIX + 'multiplier', ''))
    except ValueError:
        raise ValueError('multiplier is not a whole number')
    if multiplier < 1:
        raise ValueError('multiplier must be at least 1')
    palette = text.get(PREFIX + 'palette', '')
    if not palette or len(palette) > 31 or not all(c.isalnum() or c in '_-' for c in palette):
        raise ValueError('palette name is not usable')
    mapping = text.get(PREFIX + 'mapping', '')
    if mapping not in MAPPINGS:
        raise ValueError('mapping must be one of ' + ', '.join(MAPPINGS))
    scale = _float(text.get(PREFIX + 'scale'), 'scale')
    shift = _float(text.get(PREFIX + 'shift'), 'shift')
    if scale < 0:
        raise ValueError('scale cannot be negative')
    # fields added later: a picture saved before them simply has the plain settings
    gamma = _float(text.get(PREFIX + 'gamma', '1'), 'gamma')
    brightness = _float(text.get(PREFIX + 'brightness', '0'), 'brightness')
    contrast = _float(text.get(PREFIX + 'contrast', '0'), 'contrast')
    if not 0.1 <= gamma <= 10:
        raise ValueError('gamma must be from 0.1 to 10')
    if not -100 <= brightness <= 100:
        raise ValueError('brightness must be from -100 to 100')
    if not -100 <= contrast <= 100:
        raise ValueError('contrast must be from -100 to 100')
    interior = text.get(PREFIX + 'interior', '000000')
    if len(interior) != 6 or any(c not in '0123456789abcdefABCDEF' for c in interior):
        raise ValueError('interior color must be six hex digits')
    return {'x': x, 'y': y, 'w': w, 'multiplier': multiplier, 'palette': palette, 'mapping': mapping,
            'scale': scale, 'shift': shift, 'gamma': gamma, 'brightness': brightness, 'contrast': contrast,
            'interior': interior.lower()}
