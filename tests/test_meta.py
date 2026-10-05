"""meta.py: the description of a view inside a saved PNG. PNG files are built by hand here, so the reader is
checked against the file format itself rather than against Qt's writer."""
import os
import struct
import sys
import tempfile
import unittest
import zlib
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import meta


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png(*extra, size=(2, 2)):
    """A tiny valid PNG with the given extra chunks before the image data."""
    w, h = size
    rows = b''.join(b'\0' + b'\x10\x20\x30' * w for _ in range(h))
    return (meta.PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + b''.join(extra) +
            chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def text(key, value):
    return chunk(b'tEXt', key.encode('latin-1') + b'\0' + value.encode('latin-1'))


GOOD = meta.view_text('-0.75', '0.1', '1E-30', 100, 'fire', 'log', 30, 0.25)


class Meta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name='a.png'):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'wb') as fp:
            fp.write(data)
        return path

    def fields_png(self, fields):
        return self.write(png(*[text(k, v) for k, v in fields.items()]))

    # -- writing the fields
    def test_fields_describe_the_view(self):
        self.assertEqual(GOOD['mandelbrot.x'], '-0.75')
        self.assertEqual(GOOD['mandelbrot.width'], '1E-30')
        self.assertEqual(GOOD['mandelbrot.multiplier'], '100')
        self.assertEqual((GOOD['mandelbrot.scale'], GOOD['mandelbrot.shift']), ('30', '0.25'))
        self.assertEqual(GOOD['Software'], 'gpumand')
        self.assertTrue(all(len(k) <= 79 and k.isascii() for k in GOOD))

    def test_decimals_keep_every_digit(self):
        x = Decimal('-0.' + '7436438870371587047521915061147740' * 30)
        got = meta.parse_view(meta.read_png_text(self.fields_png(meta.view_text(x, '0', '1E-900', 1, 'a', 'log', 0, 0))))
        self.assertEqual(got['x'], x)
        self.assertEqual(got['w'], Decimal('1E-900'))

    # -- reading text chunks
    def test_reads_text_chunks_of_every_kind(self):
        itxt_plain = chunk(b'iTXt', b'k.plain\0\0\0\0\0' + 'café'.encode())
        itxt_zip = chunk(b'iTXt', b'k.zip\0\x01\0\0\0' + zlib.compress('zipped é'.encode()))
        ztxt = chunk(b'zTXt', b'k.z\0\0' + zlib.compress(b'compressed'))
        path = self.write(png(text('k.text', 'plain'), ztxt, itxt_plain, itxt_zip))
        self.assertEqual(meta.read_png_text(path), {'k.text': 'plain', 'k.z': 'compressed', 'k.plain': 'café', 'k.zip': 'zipped é'})

    def test_first_of_duplicate_keys_wins(self):
        path = self.write(png(text('k', 'first'), text('k', 'second')))
        self.assertEqual(meta.read_png_text(path), {'k': 'first'})

    def test_a_picture_without_text_has_none(self):
        self.assertEqual(meta.read_png_text(self.write(png())), {})

    def test_text_after_the_image_data_is_ignored_like_any_png_reader_would(self):
        data = png()
        path = self.write(data[:-12] + text('late', 'x') + data[-12:])
        self.assertEqual(meta.read_png_text(path), {'late': 'x'})

    def test_refuses_files_that_are_not_png(self):
        for name, data in (('bmp.png', b'BM' + bytes(60)), ('text.png', b'hello'), ('empty.png', b''), ('jpeg.png', b'\xff\xd8\xff\xe0' + bytes(20))):
            with self.assertRaises(ValueError, msg=name):
                meta.read_png_text(self.write(data, name))

    def test_damaged_files_are_refused_or_harmless(self):
        whole = png(text('k', 'v'))
        for cut in (9, 20, 40, len(whole) - 20):
            path = self.write(whole[:cut])
            try:
                meta.read_png_text(path)
            except ValueError:
                pass            # either way: no crash, no hang
        huge = meta.PNG_SIGNATURE + struct.pack('>I4s', 0x7fffffff, b'tEXt') + b'x' * 10
        with self.assertRaises(ValueError):
            meta.read_png_text(self.write(huge))

    def test_big_picture_data_is_skipped_not_loaded(self):
        big = png(size=(300, 300))
        path = self.write(big[:33] + text('mandelbrot.version', '1') + big[33:])
        self.assertEqual(meta.read_png_text(path), {'mandelbrot.version': '1'})

    # -- checking what a file claims
    def test_good_fields_are_accepted(self):
        got = meta.parse_view(GOOD)
        self.assertEqual((got['x'], got['y'], got['w'], got['multiplier']), (Decimal('-0.75'), Decimal('0.1'), Decimal('1E-30'), 100))
        self.assertEqual((got['palette'], got['mapping'], got['scale'], got['shift']), ('fire', 'log', 30.0, 0.25))

    def test_bad_fields_are_refused_with_a_reason(self):
        bad = {'no version at all': None, 'x is not a number': {'mandelbrot.x': 'abc'}, 'x is NaN': {'mandelbrot.x': 'NaN'},
               'x is infinite': {'mandelbrot.x': 'Infinity'}, 'x has a huge exponent': {'mandelbrot.x': '1e99999'},
               'y is empty': {'mandelbrot.y': ''}, 'width is zero': {'mandelbrot.width': '0'}, 'width is negative': {'mandelbrot.width': '-1'},
               'width is absurdly long': {'mandelbrot.width': '1' * 6000}, 'x has thousands of digits': {'mandelbrot.x': '0.' + '1' * 6000}, 'multiplier is zero': {'mandelbrot.multiplier': '0'},
               'multiplier is text': {'mandelbrot.multiplier': 'lots'}, 'multiplier is fractional': {'mandelbrot.multiplier': '1.5'},
               'palette is empty': {'mandelbrot.palette': ''}, 'palette has a path in it': {'mandelbrot.palette': '../x'},
               'palette is too long': {'mandelbrot.palette': 'p' * 40}, 'mapping is unknown': {'mandelbrot.mapping': 'sparkle'},
               'scale is negative': {'mandelbrot.scale': '-1'}, 'scale is NaN': {'mandelbrot.scale': 'nan'},
               'shift is text': {'mandelbrot.shift': 'x'}, 'format is newer': {'mandelbrot.version': '2'}}
        for label, change in bad.items():
            fields = {k: v for k, v in GOOD.items() if k != 'mandelbrot.version'} if change is None else dict(GOOD, **change)
            with self.assertRaises(ValueError, msg=label):
                meta.parse_view(fields)

    def test_missing_fields_are_refused(self):
        for key in [k for k in GOOD if k.startswith('mandelbrot.') and k != 'mandelbrot.version']:
            fields = {k: v for k, v in GOOD.items() if k != key}
            with self.assertRaises(ValueError, msg=key):
                meta.parse_view(fields)


if __name__ == '__main__':
    unittest.main()
