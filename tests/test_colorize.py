#!/usr/bin/env python3
"""Tests for the color module (colorize.c) through the `colorize` tool.

The mapping and palette-lookup rules are re-implemented here in Python, so the tests check the C
code against an independent statement of what it is supposed to do.
"""
import bisect
import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from array import array

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PALETTE_SIZE = 4096
TOOL = None


def setUpModule():
    global TOOL
    if shutil.which('gcc') and shutil.which('make'):
        if subprocess.run(['make', '-C', ROOT, 'colorize'], capture_output=True).returncode == 0:
            TOOL = os.path.join(ROOT, 'colorize')


def palette_names():
    out = subprocess.run([TOOL, '--list-palettes'], capture_output=True, text=True, check=True).stdout
    return [line.split()[0] for line in out.strip().split('\n')]


def dump_palette(name):
    out = subprocess.run([TOOL, '--dump-palette=' + name], capture_output=True, text=True, check=True).stdout
    return [int(line, 16) for line in out.split()]


def channels(rgb):
    return (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255


def luminance(rgb):
    r, g, b = (c / 255.0 for c in channels(rgb))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
class Palettes(unittest.TestCase):
    def setUp(self):
        if TOOL is None:
            self.skipTest('colorize does not build here')

    def test_there_are_several_styles_including_the_original(self):
        names = palette_names()
        self.assertGreaterEqual(len(names), 8)
        self.assertEqual(len(set(names)), len(names))
        for expected in ('twilight', 'fire', 'ocean', 'classic', 'rainbow', 'gray'):
            self.assertIn(expected, names)

    def test_every_palette_is_a_full_size_deterministic_table(self):
        for name in palette_names():
            table = dump_palette(name)
            self.assertEqual(len(table), PALETTE_SIZE, name)
            self.assertTrue(all(0 <= c <= 0xFFFFFF for c in table), name)
            self.assertEqual(table, dump_palette(name), name)

    def test_every_palette_is_smooth_and_closes_into_a_loop(self):
        for name in palette_names():
            table = dump_palette(name)
            worst = 0
            for a, b in zip(table, table[1:] + table[:1]):          # includes the wrap-around step
                worst = max(worst, max(abs(x - y) for x, y in zip(channels(a), channels(b))))
            # classic is the original 8-bit ramp, played forwards and back; it has one 13-level step where it enters its gray tail
            self.assertLessEqual(worst, 8 if name != 'classic' else 14, '%s: biggest step between neighbors is %d levels' % (name, worst))

    def test_gradient_palettes_have_no_kinks_including_at_the_seam(self):
        # a smooth spline has tiny second differences; a kink (e.g. a bad wrap at the loop's join) shows up here
        for name in palette_names():
            if name in ('classic', 'gray'):       # classic is an 8-bit ramp; gray's mirror turns are corners by design
                continue
            t = dump_palette(name)
            for k in range(PALETTE_SIZE):
                a, b, c = t[k - 1], t[k], t[(k + 1) % PALETTE_SIZE]
                kink = max(abs(x - 2 * y + z) for x, y, z in zip(channels(a), channels(b), channels(c)))
                self.assertLessEqual(kink, 3, '%s: kink of %d levels at entry %d' % (name, kink, k))

    def test_gradients_match_an_independent_oklab_spline(self):
        """Re-derive palettes from their key colors with the published OKLab matrices and a periodic
        Catmull-Rom spline; the C tables must agree to within rounding. This also pins the color
        space (checked below against Ottosson's reference values) and the join at the loop's seam."""
        M1 = [[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
              [0.0883024619, 0.2817188376, 0.6299787005]]
        M2 = [[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
              [0.0259040371, 0.7827717662, -0.8086757660]]

        def matmul(m, v):
            return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]

        def inverse(m):          # derived, not typed in, so it independently checks the C code's inverse constants
            (a, b, c), (d, e, f), (g, h, i) = m
            det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
            return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
                    [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
                    [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]

        def lin(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        def unlin(c):
            c = min(max(c, 0.0), 1.0)
            return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

        def to_lab(rgb):
            lms = matmul(M1, [lin(ch / 255.0) for ch in channels(rgb)])
            return matmul(M2, [math.copysign(abs(v) ** (1 / 3.0), v) for v in lms])

        def to_rgb(lab):
            lms = [v ** 3 for v in matmul(inverse(M2), lab)]
            return [unlin(v) * 255.0 for v in matmul(inverse(M1), lms)]

        # Ottosson's reference OKLab values for the sRGB primaries and white
        for rgb, want in ((0xFF0000, (0.6280, 0.2249, 0.1258)), (0x00FF00, (0.8664, -0.2339, 0.1795)),
                          (0x0000FF, (0.4520, -0.0325, -0.3115)), (0xFFFFFF, (1.0, 0.0, 0.0))):
            for got, exp in zip(to_lab(rgb), want):
                self.assertAlmostEqual(got, exp, delta=2e-3)

        def spline(stops):
            labs = [to_lab(c) for c in stops]
            n = len(labs)
            table = []
            for k in range(PALETTE_SIZE):
                sk = k * n / float(PALETTE_SIZE)
                i, u = int(sk), sk - int(sk)
                p0, p1, p2, p3 = labs[(i - 1) % n], labs[i % n], labs[(i + 1) % n], labs[(i + 2) % n]
                w = (-0.5 * u ** 3 + u ** 2 - 0.5 * u, 1.5 * u ** 3 - 2.5 * u ** 2 + 1, -1.5 * u ** 3 + 2 * u ** 2 + 0.5 * u,
                     0.5 * u ** 3 - 0.5 * u ** 2)
                table.append(to_rgb([w[0] * p0[j] + w[1] * p1[j] + w[2] * p2[j] + w[3] * p3[j] for j in range(3)]))
            return table
        stops = {'ice': [0xf4faff, 0xbfe3ff, 0x6eb5ff, 0x2f6bd6, 0x14307a, 0x2f6bd6],
                 'sunset': [0x2b1055, 0x7b2d8b, 0xd94f70, 0xff8c42, 0xffd56b, 0xff8c42, 0xd94f70],
                 'twilight': [0x0b1040, 0x3a2a8f, 0x8e44ad, 0xd6458d, 0xff7f50, 0xffd166, 0xbde7f0, 0x2a9d8f, 0x14305a]}
        for name, keys in stops.items():
            want = spline(keys)
            got = dump_palette(name)
            worst = max(abs(g - w) for rgb, wrgb in zip(got, want) for g, w in zip(channels(rgb), wrgb))
            self.assertLessEqual(worst, 1.5, '%s differs from the independent spline by up to %.2f levels' % (name, worst))

    def test_every_palette_uses_many_colors(self):
        for name in palette_names():
            # gray has only 256 shades to offer
            self.assertGreater(len(set(dump_palette(name))), 200 if name == 'gray' else 400, name)

    def test_styles_differ_from_each_other(self):
        tables = {n: dump_palette(n) for n in palette_names()}
        names = list(tables)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                same = sum(x == y for x, y in zip(tables[a], tables[b]))
                self.assertLess(same, PALETTE_SIZE // 4, '%s and %s are nearly the same palette' % (a, b))

    def test_palettes_have_light_and_dark_parts_except_rainbow(self):
        for name in palette_names():
            if name == 'rainbow':
                continue
            lums = [luminance(c) for c in dump_palette(name)]
            self.assertGreater(max(lums) - min(lums), 0.35, '%s has little contrast' % name)

    def test_rainbow_covers_every_hue(self):
        import colorsys
        hues = {int(colorsys.rgb_to_hsv(*(c / 255.0 for c in channels(rgb)))[0] * 12) for rgb in dump_palette('rainbow')}
        self.assertEqual(hues, set(range(12)))

    def test_classic_is_the_original_ramp_played_forwards_then_back(self):
        # the original generator, transcribed with 8-bit wraparound
        ramp = []
        r, g, b = 0xC0, 0x03, 0x03

        def put():
            ramp.append((r << 16) | (g << 8) | b)
        while True:
            took = g < 0xFC
            g = (g + 1) & 255
            if not took:
                break
            put()
            g = (g + 2) & 255
        while True:
            took = r > 0x03
            r = (r - 1) & 255
            if not took:
                break
            put()
            r = (r - 2) & 255
        while True:
            took = b < 0xFC
            b = (b + 1) & 255
            if not took:
                break
            put()
        while True:
            took = g > 0x03
            g = (g - 1) & 255
            if not took:
                break
            put()
        while True:
            took = r < 0x7F
            r = (r + 1) & 255
            if not took:
                break
            put()
        while r <= 0xE5:
            r += 1
            g += 2
            put()
        while True:
            took = r < 0xFC
            r = (r + 1) & 255
            if not took:
                break
            put()
        while True:
            took = g < 0xFC
            g = (g + 1) & 255
            if not took:
                break
            put()
        ramp += [0xF0F0F0] * 12
        self.assertEqual(len(ramp), 952)       # the size of the original palette
        table = dump_palette('classic')
        n = len(ramp)
        for k in range(0, PALETTE_SIZE // 2, 37):
            t = k / float(PALETTE_SIZE)
            self.assertEqual(table[k], ramp[int(2.0 * t * (n - 1) + 0.5)], k)
        self.assertEqual(table[0], ramp[0])
        self.assertEqual(table[PALETTE_SIZE // 2], ramp[-1])      # the turning point: the original's last color
        for k in range(1, PALETTE_SIZE // 2, 53):                 # the second half mirrors the first
            self.assertEqual(table[PALETTE_SIZE - k], table[k])


def write_nu(path, rows):
    h, w = len(rows), len(rows[0])
    with open(path, 'wb') as fp:
        fp.write(struct.pack('<4sII', b'MNU1', w, h))
        for row in rows:
            fp.write(struct.pack('<%dd' % w, *row))
    return w, h


def read_bmp_pixels(path):
    with open(path, 'rb') as fp:
        data = fp.read()
    w, h = struct.unpack('<ii', data[18:26])
    px = array('I')
    px.frombytes(data[54:])
    return w, h, list(px)


def adjusted(table, brightness, contrast):
    """The palette after brightness and contrast, from the formula documented in colorize.c."""
    k, add = 1.0 + contrast / 100.0, brightness * 2.55
    out = []
    for color in table:
        c = 0
        for shift in (0, 8, 16):
            v = math.floor(((color >> shift & 0xFF) - 127.5) * k + 127.5 + add + 0.5)
            c |= max(0, min(255, v)) << shift
        out.append(c)
    return out


def expected_colors(nu, table, mapping, scale, shift, interior=0, gamma=1.0, brightness=0.0, contrast=0.0):
    """Independent implementation of the documented mapping rules (see colorize.h)."""
    table = adjusted(table, brightness, contrast)
    escaped = sorted(v for v in nu if v >= 0)
    out = []
    for v in nu:
        if v < 0:
            out.append(interior)
            continue
        if mapping == 'histogram':
            pos = (bisect.bisect_left(escaped, v) + 0.5) / len(escaped) * scale + shift
        elif mapping == 'linear':
            pos = v / scale + shift
        else:
            pos = math.log2(v + 1.0) * scale + shift
        frac = (pos - math.floor(pos)) ** gamma
        out.append(table[min(int(frac * PALETTE_SIZE), PALETTE_SIZE - 1)])
    return out


@unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
class Coloring(unittest.TestCase):
    def setUp(self):
        if TOOL is None:
            self.skipTest('colorize does not build here')
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def color(self, rows, *options, check=True, bare=False):
        """Colors `rows` with the tool. Unless a palette is named (or `bare`, to try the built-in default), twilight is used,
        so tests that are about something else do not depend on which palette is the default."""
        if not bare and not any(o.startswith('--palette') for o in options):
            options = ('--palette=twilight',) + options
        nuf, out = os.path.join(self.tmp, 'in.nu'), os.path.join(self.tmp, 'out.bmp')
        write_nu(nuf, rows)
        res = subprocess.run([TOOL, nuf, out, *options], capture_output=True, text=True)
        if check:
            self.assertEqual(res.returncode, 0, res.stderr)
            return read_bmp_pixels(out)
        return res

    def values(self, n=400, seed=5, interior=0.15):
        rng = random.Random(seed)
        vals = [-1.0 if rng.random() < interior else math.exp(rng.uniform(0, 7)) for _ in range(n)]
        return [vals[i:i + 20] for i in range(0, n, 20)]

    def flat(self, rows):
        return [v for row in rows for v in row]

    def check_mapping(self, mapping, scale, default_scale, shift=0.0, palette='twilight', extra=()):
        rows = self.values()
        opts = ['--palette=' + palette, '--mapping=' + mapping] + (['--scale=%g' % scale] if scale else []) + \
               (['--shift=%g' % shift] if shift else []) + list(extra)
        w, h, got = self.color(rows, *opts)
        self.assertEqual((w, h), (20, 20))
        want = expected_colors(self.flat(rows), dump_palette(palette), mapping, scale or default_scale, shift)
        self.assertEqual(got, want)

    def test_histogram_mapping(self):
        self.check_mapping('histogram', 3.0, 2.5)
        self.check_mapping('histogram', 1.0, 2.5, shift=0.3, palette='fire')

    def test_linear_mapping(self):
        self.check_mapping('linear', 40.0, 50.0)
        self.check_mapping('linear', 7.5, 50.0, shift=0.6, palette='ocean')

    def test_log_mapping(self):
        self.check_mapping('log', 0.8, 0.6)
        self.check_mapping('log', 0.25, 0.6, shift=0.9, palette='aurora')

    def test_each_mapping_has_its_documented_default_scale(self):
        self.check_mapping('histogram', None, 2.5)
        self.check_mapping('linear', None, 50.0)
        self.check_mapping('log', None, 0.6)

    def test_default_palette_and_mapping_are_gray_and_histogram(self):
        rows = self.values()
        _, _, plain = self.color(rows, bare=True)
        _, _, explicit = self.color(rows, '--palette=gray', '--mapping=histogram', '--scale=2.5')
        self.assertEqual(plain, explicit)
        _, _, twilight = self.color(rows)
        self.assertNotEqual(plain, twilight)

    def test_interior_pixels_get_the_interior_color(self):
        rows = self.values()
        _, _, black = self.color(rows)
        _, _, custom = self.color(rows, '--interior=ff00aa')
        flat = self.flat(rows)
        self.assertTrue(any(v < 0 for v in flat))
        for v, b, c in zip(flat, black, custom):
            if v < 0:
                self.assertEqual((b, c), (0x000000, 0xFF00AA))
            else:
                self.assertEqual(b, c)

    def check_adjusted(self, options, **settings):
        rows = self.values()
        _, _, got = self.color(rows, '--mapping=linear', '--scale=40', *options)
        want = expected_colors(self.flat(rows), dump_palette('twilight'), 'linear', 40.0, 0.0, **settings)
        self.assertEqual(got, want)
        return got

    def test_gamma_bends_the_position_inside_each_cycle(self):
        plain = self.check_adjusted([])
        for g in (0.2, 0.5, 2.0, 7.5):
            self.assertNotEqual(self.check_adjusted(['--gamma=%g' % g], gamma=g), plain, g)
        self.assertEqual(self.check_adjusted(['--gamma=1'], gamma=1.0), plain)         # 1 changes nothing
        # the middle of a cycle (0.5) moves to the start of the palette with gamma > 1, to the end with gamma < 1
        table = dump_palette('twilight')
        pick = lambda opts: self.color([[200.0]], '--mapping=linear', '--scale=400', *opts)[2][0]
        self.assertEqual(pick([]), table[2048])
        self.assertEqual(pick(['--gamma=3']), table[int(0.125 * PALETTE_SIZE)])
        self.assertEqual(pick(['--gamma=0.5']), table[int(0.5 ** 0.5 * PALETTE_SIZE)])
        # both ends of the cycle stay where they are, so the loop of colors still closes up without a seam
        self.assertEqual(self.color([[0.0]], '--mapping=linear', '--scale=400', '--gamma=3')[2][0], table[0])

    def test_brightness_and_contrast_change_the_palette_colors(self):
        plain = self.check_adjusted([])
        for b, c in ((40, 0), (-40, 0), (100, 0), (-100, 0), (0, 50), (0, -50), (0, 100), (0, -100), (30, 60), (-25, -70)):
            got = self.check_adjusted(['--brightness=%g' % b, '--contrast=%g' % c], brightness=b, contrast=c)
            self.assertNotEqual(got, plain, (b, c))

    def test_brightness_and_contrast_move_the_light_and_dark_ends_apart_or_together(self):
        rows = self.values()
        flat = self.flat(rows)

        def luma(opts):
            px = self.color(rows, '--scale=1', *opts)[2]
            lights = [sum((c >> s & 0xFF) for s in (0, 8, 16)) / 3.0 for v, c in zip(flat, px) if v >= 0]
            return min(lights), max(lights), sum(lights) / len(lights)
        base, bright, dark = luma([]), luma(['--brightness=50']), luma(['--brightness=-50'])
        self.assertGreater(bright[2], base[2] + 20)
        self.assertLess(dark[2], base[2] - 20)
        more, less = luma(['--contrast=60']), luma(['--contrast=-60'])
        self.assertGreater(more[1] - more[0], base[1] - base[0])
        self.assertLess(less[1] - less[0], base[1] - base[0])
        flat_gray = luma(['--contrast=-100'])
        self.assertLess(flat_gray[1] - flat_gray[0], 1.5)                   # no contrast at all: every color mid-gray

    def test_extremes_are_limited_to_valid_colors_and_leave_the_interior_alone(self):
        rows = self.values()
        flat = self.flat(rows)
        for opts in (['--brightness=100', '--contrast=100'], ['--brightness=-100', '--contrast=100'], ['--contrast=-100']):
            _, _, px = self.color(rows, '--interior=123456', *opts)
            self.assertTrue(all(0 <= c <= 0xFFFFFF for c in px))
            self.assertTrue(all(c == 0x123456 for v, c in zip(flat, px) if v < 0), opts)
        _, _, white = self.color(rows, '--brightness=100')
        self.assertTrue(all(c == 0xFFFFFF for v, c in zip(flat, white) if v >= 0))
        _, _, black = self.color(rows, '--brightness=-100')
        self.assertTrue(all(c == 0 for v, c in zip(flat, black) if v >= 0))

    def test_shift_rotates_the_palette(self):
        rows = [[100.0 + i for i in range(40)]]
        table = dump_palette('twilight')
        _, _, quarter = self.color(rows, '--mapping=linear', '--scale=40', '--shift=0.25')
        self.assertEqual(quarter, expected_colors(rows[0], table, 'linear', 40.0, 0.25))
        # a whole turn changes nothing
        _, _, base = self.color(rows, '--mapping=linear', '--scale=40')
        _, _, turn = self.color(rows, '--mapping=linear', '--scale=40', '--shift=1')
        _, _, back = self.color(rows, '--mapping=linear', '--scale=40', '--shift=-1')
        self.assertEqual(base, turn)
        self.assertEqual(base, back)
        self.assertNotEqual(base, quarter)

    def test_histogram_uses_the_palette_evenly_whatever_the_values(self):
        # values bunched into a narrow band, as in a deep view: the colors must still spread out
        rng = random.Random(8)
        rows = [[1000.0 + rng.random() * 5.0 for _ in range(100)] for _ in range(100)]
        _, _, got = self.color(rows, '--scale=1')
        index = {c: i for i, c in enumerate(dump_palette('twilight'))}
        buckets = [0] * 8
        for c in got:
            buckets[index[c] * 8 // PALETTE_SIZE] += 1
        self.assertTrue(all(abs(b - len(got) / 8.0) < len(got) * 0.02 for b in buckets), buckets)

    def test_equal_values_get_equal_colors_and_order_is_kept(self):
        rows = [[5.0, 5.0, 9.0, 9.0, 2.0, 2.0, -1.0, 5.0]]
        _, _, got = self.color(rows, '--scale=1')
        self.assertEqual(got[0], got[1])
        self.assertEqual(got[0], got[7])
        self.assertEqual(got[2], got[3])
        index = {c: i for i, c in enumerate(dump_palette('twilight'))}
        # with one cycle, rank order is palette order: 2 < 5 < 9
        self.assertLess(index[got[4]], index[got[0]])
        self.assertLess(index[got[0]], index[got[2]])

    def test_degenerate_images(self):
        self.assertEqual(self.color([[-1.0]])[2], [0])                              # one interior pixel
        self.assertEqual(self.color([[-1.0] * 5] * 3)[2], [0] * 15)                 # nothing escapes
        _, _, one = self.color([[7.0]])
        self.assertEqual(len(one), 1)
        _, _, same = self.color([[3.0] * 6] * 2)
        self.assertEqual(len(set(same)), 1)
        w, h, px = self.color([[1.0 + i for i in range(1)] for _ in range(37)])     # tall and thin
        self.assertEqual((w, h, len(px)), (1, 37, 37))

    def test_huge_and_tiny_values_are_fine(self):
        for m in ('histogram', 'linear', 'log'):
            _, _, px = self.color([[0.0, 1e-300, 1e9, 1e15, -1.0]], '--mapping=' + m)
            self.assertEqual(len(px), 5)

    def test_rejects_bad_options_and_files(self):
        rows = self.values()
        for bad, text in ((['--palette=nope'], 'unknown palette'), (['--mapping=x'], 'unknown mapping'),
                          (['--scale=-1'], '--scale'), (['--shift=zz'], '--shift'), (['--interior=abc'], '--interior'),
                          (['--gamma=0'], '--gamma'), (['--gamma=11'], '--gamma'), (['--gamma=x'], '--gamma'),
                          (['--brightness=101'], '--brightness'), (['--brightness=nan'], '--brightness'),
                          (['--contrast=-101'], '--contrast'), (['--contrast='], '--contrast'),
                          (['--what=1'], 'unexpected')):
            res = self.color(rows, *bad, check=False)
            self.assertNotEqual(res.returncode, 0, bad)
            self.assertIn(text, res.stderr)
        res = subprocess.run([TOOL, os.path.join(self.tmp, 'missing.nu'), os.path.join(self.tmp, 'o.bmp')], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        res = subprocess.run([TOOL], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('usage', res.stderr)

    def test_rejects_corrupt_nu_files(self):
        out = os.path.join(self.tmp, 'o.bmp')

        def attempt(name, data):
            path = os.path.join(self.tmp, name)
            with open(path, 'wb') as fp:
                fp.write(data)
            res = subprocess.run([TOOL, path, out], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0, name)
            self.assertTrue(res.stderr.strip(), name)
        body = struct.pack('<4d', 1.0, 2.0, 3.0, 4.0)
        attempt('magic.nu', struct.pack('<4sII', b'NOPE', 2, 2) + body)
        attempt('short.nu', struct.pack('<4sII', b'MNU1', 2, 2) + body[:16])
        attempt('zero.nu', struct.pack('<4sII', b'MNU1', 0, 2))
        attempt('huge.nu', struct.pack('<4sII', b'MNU1', 0xFFFFFFFF, 0xFFFFFFFF))
        attempt('empty.nu', b'')
        self.assertFalse(os.path.exists(out))


if __name__ == '__main__':
    unittest.main()
