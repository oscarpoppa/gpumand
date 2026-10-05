#!/usr/bin/env python3
"""Tests for mand-cpu, the CPU renderer. Skipped when gcc/OpenMP are unavailable.

Each render is checked against what the maths says it must be: the smooth iteration count (nu)
of a sampled pixel, read from the --nu-out file, equals the value from direct high-precision
iteration (or from a Python mirror of the plain kernel). Coloring is tested in test_colorize.py;
here only the pipeline's consistency with the `colorize` tool is checked.
"""
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from array import array
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import deepzoom
from deepzoom import WIDTH, HEIGHT, ITERATIONS, BAILOUT2
import test_deepzoom as td

SOURCES = ['mand-cpu.c', 'colorize.c', 'bmp.c', 'get-coords.c', 'bla.c', 'refio.c']
TMP = None
MAND = None       # built through `make mand-cpu`
MAND_FX = None    # same sources, floatexp threshold lowered so a cheap view uses that path
COLORIZE = None   # built through `make colorize`


def gcc_command(out, *extra):
    return ['gcc', '-O2', '-std=gnu99', '-ffp-contract=off', '-fopenmp', '-Wall', '-Wextra', '-I', ROOT,
            *extra, '-o', out] + [os.path.join(ROOT, s) for s in SOURCES] + ['-lm']


def setUpModule():
    global TMP, MAND, MAND_FX, COLORIZE
    if not shutil.which('gcc') or not shutil.which('make'):
        return
    if subprocess.run(gcc_command('/dev/null'), capture_output=True).returncode:
        return  # no OpenMP / compiler problem: tests below skip
    TMP = tempfile.mkdtemp()
    subprocess.check_call(['make', '-C', ROOT, 'mand-cpu', 'colorize'], stdout=subprocess.DEVNULL)
    MAND = os.path.join(ROOT, 'mand-cpu')
    COLORIZE = os.path.join(ROOT, 'colorize')
    MAND_FX = os.path.join(TMP, 'mand-cpu-fx')
    subprocess.check_call(gcc_command(MAND_FX, '-DFX_STEP_EXP=(-10)'))


def tearDownModule():
    if TMP:
        shutil.rmtree(TMP, ignore_errors=True)


def read_bmp(path):
    with open(path, 'rb') as fp:
        data = fp.read()
    pix = array('I')
    pix.frombytes(data[54:])
    return data[:54], pix


def read_nu(path):
    with open(path, 'rb') as fp:
        magic, w, h = struct.unpack('<4sII', fp.read(12))
        nu = array('d')
        nu.frombytes(fp.read(8 * w * h))
    assert magic == b'MNU1' and (w, h) == (WIDTH, HEIGHT) and len(nu) == w * h
    return nu


@unittest.skipUnless(shutil.which('gcc') and shutil.which('make'), 'needs gcc and make')
class CpuRenderer(unittest.TestCase):
    def setUp(self):
        if MAND is None:
            self.skipTest('gcc with OpenMP not available')
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def render(self, exe, x, y, w, mult, ref=None, env=None, expect_path=None, options=()):
        """Runs the renderer; returns (bmp path, nu array)."""
        n = len(os.listdir(self.tmp))
        out, nuf = os.path.join(self.tmp, 'out%d.bmp' % n), os.path.join(self.tmp, 'out%d.nu' % n)
        cmd = [exe, str(x), str(y), str(w), out, str(mult)] + ([ref] if ref else []) + ['--nu-out=' + nuf, *options]
        res = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, MAND_VERBOSE='1', **(env or {})))
        self.assertEqual(res.returncode, 0, res.stderr)
        if expect_path:
            self.assertIn('mand-cpu: %s path' % expect_path, res.stderr)
        return out, read_nu(nuf)

    def make_ref(self, x, y, w, maxiter):
        path = os.path.join(self.tmp, 'r%d.ref' % len(os.listdir(self.tmp)))
        deepzoom.write_reference(path, x, y, w, maxiter)
        return path

    def sample(self, seed, n):
        rng = random.Random(seed)
        return [(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(n)]

    def check_nu(self, nu, expected, pixels, tol, min_match=0.99):
        """expected(px, py) -> smooth count or -1. Escaped pixels must agree within tol; inside must be -1."""
        match = 0
        for px, py in pixels:
            want, got = expected(px, py), nu[WIDTH * py + px]
            ok = (got == -1.0) if want == -1.0 else (got >= 0 and abs(got - want) < tol)
            match += ok
        frac = match / float(len(pixels))
        self.assertGreaterEqual(frac, min_match, '%.1f%% of sampled pixels match' % (frac * 100))

    # -- output format -------------------------------------------------------------

    def test_writes_a_valid_bmp_and_nu_file(self):
        out, nu = self.render(MAND, -2, -1.333333, 4, 1)
        head, pix = read_bmp(out)
        self.assertEqual(head[:2], b'BM')
        self.assertEqual(int.from_bytes(head[18:22], 'little'), WIDTH)
        self.assertEqual(int.from_bytes(head[22:26], 'little'), HEIGHT)
        self.assertEqual(len(pix), WIDTH * HEIGHT)
        self.assertEqual(os.path.getsize(out), 54 + 4 * WIDTH * HEIGHT)
        self.assertTrue(any(v == -1.0 for v in nu), 'the whole set has interior pixels')
        self.assertTrue(all(v == -1.0 or v >= 0.0 for v in nu))
        # interior pixels get the interior color (black by default); the cardioid's centre is inside
        inside = [i for i, v in enumerate(nu) if v == -1.0]
        self.assertTrue(all(pix[i] == 0 for i in inside[:2000]))

    def test_nu_file_is_optional(self):
        out = os.path.join(self.tmp, 'o.bmp')
        subprocess.run([MAND, '-2', '-1.3', '4', out, '1'], check=True, capture_output=True)
        self.assertEqual(os.listdir(self.tmp), ['o.bmp'])

    def test_image_matches_the_colorize_tool(self):
        # recoloring a saved nu file must give exactly the image the renderer wrote
        opts = ['--palette=fire', '--mapping=linear', '--scale=30', '--shift=0.1', '--interior=102030']
        out, _ = self.render(MAND, -0.7436, 0.1318, 1e-3, 1, options=opts)
        nuf = out[:-4] + '.nu'
        again = os.path.join(self.tmp, 'again.bmp')
        subprocess.run([COLORIZE, nuf, again] + opts, check=True, capture_output=True)
        with open(out, 'rb') as a, open(again, 'rb') as b:
            self.assertEqual(a.read(), b.read())
        _, pix = read_bmp(out)
        self.assertIn(0x102030, set(pix))

    # -- the three render paths ----------------------------------------------------

    def plain_expected(self, x, y, w, mult):
        iterations = ITERATIONS * mult

        def expected(px, py):
            cx, cy = x + w * px / WIDTH, y + w * py / WIDTH   # same expression order as the renderer
            z, c = 0j, complex(cx, cy)
            for cnt in range(iterations):
                z = z * z + c
                zz = z.real * z.real + z.imag * z.imag
                if zz > BAILOUT2:
                    return td.smooth_nu(cnt, zz)
            return -1.0
        return expected

    def test_plain_kernel_whole_set(self):
        _, nu = self.render(MAND, -2.0, -1.333333, 4.0, 1, expect_path='plain')
        self.check_nu(nu, self.plain_expected(-2.0, -1.333333, 4.0, 1), self.sample(1, 600), 1e-9, 0.999)

    def test_plain_kernel_zoomed(self):
        x, y, w = -0.7436, 0.1318, 1e-3
        _, nu = self.render(MAND, x, y, w, 2)
        self.check_nu(nu, self.plain_expected(x, y, w, 2), self.sample(2, 400), 1e-9, 0.999)

    def exact_expected(self, x, y, w, iterations):
        w = Decimal(w)
        return lambda px, py: td.exact_nu(x, y, w, px, py, iterations)[1]

    def test_perturbation_with_bla_far_past_double_precision(self):
        w = Decimal('1e-30')
        x, y = td.view_for_center(td.SPIRAL[0], td.SPIRAL[1], w)
        ref = self.make_ref(x, y, w, 2000)
        _, nu = self.render(MAND, x, y, w, 1, ref, expect_path='perturbation+BLA')
        self.assertGreater(len({round(v, 3) for v in nu}), 100, 'image should have structure, not be flat')
        self.check_nu(nu, self.exact_expected(x, y, w, 2000), self.sample(3, 300), 1e-3, 0.99)

    def test_floatexp_path_is_used_and_correct(self):
        # MAND_FX switches to floatexp at pixel step < 2^-10, so this width exercises that loop
        w = Decimal('1e-6')
        x, y = td.view_for_center(td.SPIRAL[0], td.SPIRAL[1], w)
        ref = self.make_ref(x, y, w, 2000)
        _, nu = self.render(MAND_FX, x, y, w, 1, ref, expect_path='floatexp')
        self.assertGreater(len({round(v, 3) for v in nu}), 100)
        self.check_nu(nu, self.exact_expected(x, y, w, 2000), self.sample(4, 300), 1e-5, 0.99)
        # and it agrees with the double-precision perturbation path on the same input
        _, other = self.render(MAND, x, y, w, 1, ref, expect_path='perturbation+BLA')
        same = sum(abs(a - b) < 1e-3 for a, b in zip(nu, other)) / float(len(nu))
        self.assertGreater(same, 0.999, 'floatexp vs double perturbation: %.4f agree' % same)

    # -- iteration limits past 2^31 (the top multiplier, 20 million, is 4e10 iterations) --------------------
    # Every pixel of these views escapes within a few iterations, so only the limit's arithmetic is tested.
    # 2000 * 1,073,742 = 2,147,484,000 is just past 2^31: held in 32 bits it goes negative, the loop never
    # runs, and the whole image would come out "inside the set" (-1).
    OUTSIDE = ('0.6', '0.5')
    MULTS = (1073742, 20000000)

    def test_huge_iteration_limit_plain_path(self):
        x, y = self.OUTSIDE
        _, ok = self.render(MAND, x, y, 0.5, 1, expect_path='plain')
        self.assertTrue(all(v >= 0 for v in ok), 'sanity: nothing in this view is inside the set')
        for mult in self.MULTS:
            _, huge = self.render(MAND, x, y, 0.5, mult, expect_path='plain')
            self.assertEqual(list(ok), list(huge), mult)

    def test_huge_iteration_limit_perturbation_paths(self):
        x, y = self.OUTSIDE
        for width, exe, path in ((Decimal('1e-12'), MAND, 'perturbation+BLA'), (Decimal('1e-6'), MAND_FX, 'floatexp')):
            ref = self.make_ref(x, y, width, 2000)
            _, ok = self.render(exe, x, y, width, 1, ref, expect_path=path)
            self.assertTrue(all(v >= 0 for v in ok), path)
            for mult in self.MULTS:
                _, huge = self.render(exe, x, y, width, mult, ref, expect_path=path)
                self.assertEqual(list(ok), list(huge), (path, mult))

    # -- determinism -----------------------------------------------------------------

    def test_result_does_not_depend_on_thread_count(self):
        one = self.render(MAND, -0.7436, 0.1318, 1e-3, 1, env={'OMP_NUM_THREADS': '1'})
        many = self.render(MAND, -0.7436, 0.1318, 1e-3, 1, env={'OMP_NUM_THREADS': '4'})
        self.assertEqual(one[1], many[1])
        with open(one[0], 'rb') as a, open(many[0], 'rb') as b:
            self.assertEqual(a.read(), b.read())

    # -- error handling (must fail loudly, as the GUI relies on the exit status) ----

    def fails(self, *args, text=None):
        res = subprocess.run([MAND, *args], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0, 'expected failure for %s' % (args,))
        self.assertTrue(res.stderr.strip(), 'expected a message on stderr')
        if text:
            self.assertIn(text, res.stderr)

    def test_rejects_bad_arguments(self):
        out = os.path.join(self.tmp, 'o.bmp')
        self.fails()
        self.fails('1', '2', '3')
        self.fails('1', '2', 'abc', out, '1')
        self.fails('1', '2', '0', out, '1')          # zero width and no reference orbit
        self.fails('1', '2', '3', out, '0')          # multiplier must be at least 1

    def test_rejects_bad_color_options(self):
        out = os.path.join(self.tmp, 'o.bmp')
        base = ['-2', '-1.3', '4', out, '1']
        self.fails(*base, '--palette=nonesuch', text='unknown palette')
        self.fails(*base, '--mapping=sideways', text='unknown mapping')
        self.fails(*base, '--scale=-3', text='--scale')
        self.fails(*base, '--scale=abc', text='--scale')
        self.fails(*base, '--shift=x', text='--shift')
        self.fails(*base, '--interior=12345', text='--interior')
        self.fails(*base, '--interior=gggggg', text='--interior')
        self.fails(*base, '--bogus=1', text='unknown option')
        self.fails(*base, '--nu-out=', text='--nu-out')
        self.assertFalse(os.path.exists(out), 'nothing should be written for a rejected command line')

    def test_options_may_come_before_the_positional_arguments(self):
        out = os.path.join(self.tmp, 'o.bmp')
        subprocess.run([MAND, '--palette=ice', '-2', '-1.3', '4', '--mapping=log', out, '1'], check=True, capture_output=True)
        self.assertTrue(os.path.exists(out))

    def test_reports_unwritable_output_and_bad_reference(self):
        self.fails('-2', '-1.3', '4', '/nonexistent-dir/x.bmp', '1')
        self.fails('-2', '-1.3', '4', os.path.join(self.tmp, 'o.bmp'), '1', os.path.join(self.tmp, 'missing.ref'))
        self.fails('-2', '-1.3', '4', os.path.join(self.tmp, 'o.bmp'), '1', '--nu-out=/nonexistent-dir/x.nu')
        junk = os.path.join(self.tmp, 'junk.ref')
        with open(junk, 'wb') as fp:
            fp.write(b'not a reference orbit')
        self.fails('-2', '-1.3', '4', os.path.join(self.tmp, 'o.bmp'), '1', junk)

    def test_rejects_malformed_reference_orbits(self):
        out = os.path.join(self.tmp, 'o.bmp')
        orbit = struct.pack('<4d', 0.0, 0.0, 0.5, 0.0)   # two points

        def ref_file(name, count, step_exp, step_mant, body=orbit):
            path = os.path.join(self.tmp, name)
            with open(path, 'wb') as fp:
                fp.write(struct.pack('<Iid', count, step_exp, step_mant) + body)
            return path
        good = ref_file('good.ref', 2, -10, 0.5)
        subprocess.run([MAND, '-2', '-1.3', '4', out, '1', good], check=True, capture_output=True)
        self.fails('-2', '-1.3', '4', out, '1', ref_file('zero_step.ref', 2, -10, 0.0))
        self.fails('-2', '-1.3', '4', out, '1', ref_file('neg_step.ref', 2, -10, -0.5))
        self.fails('-2', '-1.3', '4', out, '1', ref_file('one_point.ref', 1, -10, 0.5, orbit[:16]))
        self.fails('-2', '-1.3', '4', out, '1', ref_file('truncated.ref', 3, -10, 0.5))   # claims 3 points, has 2
        self.fails('-2', '-1.3', '4', out, '1', ref_file('huge.ref', 0xFFFFFFFF, -10, 0.5))


if __name__ == '__main__':
    unittest.main()
