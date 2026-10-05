#!/usr/bin/env python3
"""Tests for deepzoom.py and the perturbation code in pert.h / bla.c.

Two layers:
  * perturb_count() is a Python mirror of the plain perturbation loop;
  * pert_cli (tests/pert_cli.c, built here with gcc) runs the REAL C code that the CUDA
    kernels call (double perturbation, BLA skipping, floatexp), since there is no GPU
    in CI. Iteration counts from both are compared with exact high-precision iteration.

Run: python3 -m unittest discover -s tests
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal, localcontext

import gmpy2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
import deepzoom
from deepzoom import WIDTH, HEIGHT

MAXITER = 3000
# The Misiurewicz point c = i has self-similar spiral structure at every scale, so
# a view centred on it has varied iteration counts however deep we zoom.
SPIRAL = (Decimal(0), Decimal(1))
# Centre of a wide view whose reference orbit escapes within a few iterations,
# while pixels inside the cardioid run for MAXITER (exercises rebase-on-exhaustion).
EARLY_ESCAPE = (Decimal('0.3'), Decimal(0))
# Nucleus of a period-39 minibrot in seahorse valley: the reference orbit never escapes
# and views of width 1e-3..1e-5 around it have long, varied pixel orbits (BLA's use case).
MINIBROT = (Decimal('-0.743642301657885946118597319433777835874198977270059896706944'),
            Decimal('0.131826519812594723499193012305519151310169161798284249052611'))
SEAHORSE = (Decimal('-0.743643887037158704752191506114774'),
            Decimal('0.131825904205311970493132056385139'))

CLI = None


def setUpModule():
    global CLI
    if shutil.which('gcc'):
        tmp = tempfile.mkdtemp()
        CLI = os.path.join(tmp, 'pert_cli')
        cmd = ['gcc', '-std=c99', '-O1', '-g', '-Wall', '-Wextra', '-pedantic', '-I', ROOT, '-o', CLI,
               os.path.join(ROOT, 'tests', 'pert_cli.c'), os.path.join(ROOT, 'bla.c'), '-lm']
        # catch out-of-bounds table reads and UB when the sanitizers are installed
        if subprocess.run(cmd + ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'], capture_output=True).returncode:
            subprocess.check_call(cmd)


def view_for_center(cx, cy, w):
    """Lower-left x, y of a view of width w centred on (cx, cy)."""
    with localcontext() as ctx:
        ctx.prec = deepzoom.digits_for(w) + 10
        return cx - w / 2, cy - w * HEIGHT / (2 * WIDTH)


def perturb_count(ref, step, pix_x, pix_y, iterations):
    """Python mirror of pert_pixel_dbl without BLA."""
    dc = complex((pix_x - WIDTH // 2) * step, (pix_y - HEIGHT // 2) * step)
    refn = len(ref)
    d = 0j
    n = 0
    cnt = 0
    while cnt < iterations:
        nd = 2.0 * ref[n] * d + d * d + dc
        n += 1
        cnt += 1
        z = ref[n] + nd
        if z.real * z.real + z.imag * z.imag > 4.0:
            return cnt - 1
        if abs(z) ** 2 < abs(nd) ** 2 or n >= refn - 1:
            d = z
            n = 0
        else:
            d = nd
    return iterations


def exact_count(x, y, w, pix_x, pix_y, iterations):
    """Iteration count by direct iteration at high precision."""
    bits = max(128, int(-w.adjusted() * 3.33) + 192)
    with gmpy2.context(precision=bits):
        step = gmpy2.mpfr(str(w)) / WIDTH
        cr = gmpy2.mpfr(str(x)) + step * pix_x
        ci = gmpy2.mpfr(str(y)) + step * pix_y
        zr = zi = gmpy2.mpfr(0)
        for cnt in range(iterations):
            zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
            if zr * zr + zi * zi > 4:
                return cnt
    return iterations


def plain_double_count(x, y, step, pix_x, pix_y, iterations):
    """Mirror of MandKern."""
    c = complex(float(x) + step * pix_x, float(y) + step * pix_y)
    z = 0j
    for cnt in range(iterations):
        z = z * z + c
        if z.real * z.real + z.imag * z.imag > 4.0:
            return cnt
    return iterations


class RegionMath(unittest.TestCase):
    def test_exact_halving(self):
        x, y, w = deepzoom.selection_to_region('-2.0', '-1.333333', '4.0', 300, 200, 600, WIDTH, HEIGHT)
        self.assertEqual(w, Decimal('2'))
        self.assertEqual(x, Decimal('-1'))
        self.assertLess(abs(y - (Decimal('-1.333333') + Decimal(200 * 4) / 1200)), Decimal('1e-25'))

    def test_deep_zoom_keeps_digits(self):
        x, y, w = Decimal('-0.75'), Decimal('0.1'), Decimal('4')
        for _ in range(60):
            x, y, w = deepzoom.selection_to_region(x, y, w, 601, 400, 120, WIDTH, HEIGHT)
        self.assertLess(w, Decimal('1e-50'))
        # position still resolves a single pixel: a one-pixel shift must change x
        x2, _, _ = deepzoom.selection_to_region(x, y, w, 1, 400, 120, WIDTH, HEIGHT)
        self.assertNotEqual(x, x2)
        # and a double could not tell the difference
        self.assertEqual(float(x), float(x + w / WIDTH))

    def test_zoom_past_double_exponent_range(self):
        x, y, w = Decimal('-0.75'), Decimal('0.1'), Decimal('4')
        for _ in range(300):
            x, y, w = deepzoom.selection_to_region(x, y, w, 601, 400, 12, WIDTH, HEIGHT)
        self.assertLess(w, Decimal('1e-500'))
        self.assertEqual(float(w), 0.0)  # a double cannot hold it, the Decimal can
        x2, _, _ = deepzoom.selection_to_region(x, y, w, 1, 400, 120, WIDTH, HEIGHT)
        self.assertNotEqual(x, x2)


class ReferenceFile(unittest.TestCase):
    def roundtrip(self, x, y, w, maxiter):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'r.ref')
            deepzoom.write_reference(path, x, y, w, maxiter)
            return deepzoom.read_reference(path)

    def test_round_trip(self):
        x, y = view_for_center(Decimal('-0.5'), Decimal('0'), Decimal('3'))
        ref = self.roundtrip(x, y, '3', 50)
        self.assertEqual(ref.orbit[0], 0j)
        self.assertAlmostEqual(ref.orbit[1], complex(-0.5, 0), places=12)
        self.assertEqual(ref.orbit[2], ref.orbit[1] ** 2 + ref.orbit[1])
        self.assertAlmostEqual(ref.step_mant * 2.0 ** ref.step_exp, 3 / 1200.0, places=15)

    def test_stops_at_escape(self):
        # centre 1+0i escapes at Z3 = 5
        x, y = view_for_center(Decimal('1'), Decimal('0'), Decimal('1e-3'))
        ref = self.roundtrip(x, y, '1e-3', 100)
        self.assertEqual(len(ref.orbit), 4)
        self.assertGreater(abs(ref.orbit[-1]), 2)

    def test_step_survives_beyond_double_range(self):
        x, y = view_for_center(SPIRAL[0], SPIRAL[1], Decimal('1e-400'))
        ref = self.roundtrip(x, y, '1e-400', 50)
        self.assertGreaterEqual(ref.step_mant, 0.5)
        self.assertLess(ref.step_mant, 1.0)
        self.assertLess(ref.step_exp, -1300)  # 1e-400/1200 ~ 2^-1339


class Perturbation(unittest.TestCase):
    def pixels(self, seed, count):
        rng = random.Random(seed)
        return [(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(count)]

    def make_ref(self, w, center, maxiter=MAXITER):
        x, y = view_for_center(center[0], center[1], w)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, 'r.ref')
        deepzoom.write_reference(path, x, y, w, maxiter)
        return x, y, path, deepzoom.read_reference(path)

    def run_cli(self, mode, path, pix, maxiter=MAXITER):
        if CLI is None:
            self.skipTest('gcc not available')
        out = subprocess.run([CLI, mode, path, str(maxiter)], input=''.join('%d %d\n' % p for p in pix),
                             capture_output=True, text=True, check=True).stdout.split('\n')
        return [tuple(int(v) for v in line.split()) for line in out if line]

    def exact(self, x, y, w, pix, maxiter=MAXITER):
        return [exact_count(x, y, w, px, py, maxiter) for px, py in pix]

    def check(self, w, center, mode, npix=100, min_match=0.97, maxiter=MAXITER, min_distinct=5):
        """Fraction of pixels whose count equals the exact one, for the C code in `mode`."""
        w = Decimal(w)
        x, y, path, ref = self.make_ref(w, center, maxiter)
        pix = self.pixels(1, npix)
        want = self.exact(x, y, w, pix, maxiter)
        got = self.run_cli(mode, path, pix, maxiter)
        self.assertGreaterEqual(len(set(want)), min_distinct, 'sample too uniform to be a meaningful test')
        match = sum(g[0] == e for g, e in zip(got, want)) / float(npix)
        self.assertGreaterEqual(match, min_match, '%s w=%s: %.0f%% exact' % (mode, w, match * 100))
        return got, want, ref

    # -- Python mirror ---------------------------------------------------------

    def compare_mirror(self, w, center, npix=100):
        w = Decimal(w)
        x, y, _, ref = self.make_ref(w, center)
        step = ref.step_mant * 2.0 ** ref.step_exp
        pert = plain = 0
        exact = set()
        for px, py in self.pixels(1, npix):
            want = exact_count(x, y, w, px, py, MAXITER)
            exact.add(want)
            pert += perturb_count(ref.orbit, step, px, py, MAXITER) == want
            plain += plain_double_count(x, y, step, px, py, MAXITER) == want
        self.assertGreaterEqual(len(exact), 5, 'sample is too uniform to be a meaningful test')
        return pert / float(npix), plain / float(npix)

    def test_mirror_shallow(self):
        pert, _ = self.compare_mirror('1e-5', SPIRAL)
        self.assertGreaterEqual(pert, 0.97)

    def test_mirror_beyond_double_limit(self):
        pert, plain = self.compare_mirror('1e-20', SPIRAL)
        self.assertGreaterEqual(pert, 0.97)
        self.assertLess(plain, 0.5)

    # -- the real C code -------------------------------------------------------

    def test_c_double_perturbation_shallow(self):
        self.check('1e-5', SPIRAL, 'dbl')

    def test_c_double_perturbation_beyond_double_limit(self):
        self.check('1e-20', SPIRAL, 'dbl')
        self.check('1e-150', SPIRAL, 'dbl')

    def test_c_reference_escapes_early(self):
        self.check('0.5', EARLY_ESCAPE, 'dbl')

    def test_c_floatexp_matches_exact_inside_double_range(self):
        self.check('1e-20', SPIRAL, 'fx')
        self.check('1e-150', SPIRAL, 'fx')

    def test_c_floatexp_pixels_outliving_the_reference(self):
        # the reference escapes after ~13 iterations but most pixels run on: they must rebase
        self.check('0.5', EARLY_ESCAPE, 'fx')

    def test_c_floatexp_beyond_double_exponent_range(self):
        # these widths underflow a double (pixel step 0), so only floatexp can render them
        for w in ('1e-400', '1e-1000'):
            got, want, ref = self.check(w, SPIRAL, 'fx', npix=60, maxiter=4000)
            self.assertEqual(float(Decimal(w)) / WIDTH, 0.0)
            self.assertEqual(len(set(g[0] for g in got)) > 5, True)

    def test_c_bla_matches_exact(self):
        for w in ('1e-3', '1e-4', '1e-5'):
            self.check(w, MINIBROT, 'bla', npix=80, min_match=0.95)

    def test_c_bla_skips_iterations(self):
        # Deep in the spiral the pixel offsets start far below BLA's validity radius, so whole
        # runs of iterations are skipped: far fewer loop steps for the same answer.
        w = Decimal('1e-100')
        x, y, path, ref = self.make_ref(w, SPIRAL, 6000)
        pix = self.pixels(2, 100)
        want = self.exact(x, y, w, pix, 6000)
        plain = self.run_cli('dbl', path, pix, 6000)
        fast = self.run_cli('bla', path, pix, 6000)
        total_plain = sum(s for _, s in plain)
        total_fast = sum(s for _, s in fast)
        self.assertLess(total_fast * 5, total_plain, 'BLA took %d steps vs %d' % (total_fast, total_plain))
        self.assertGreaterEqual(sum(f[0] == e for f, e in zip(fast, want)) / 100.0, 0.97)
        self.assertGreaterEqual(len(set(want)), 5)

    def test_c_bla_never_exceeds_iteration_limit(self):
        # Sweep the limit across the escape counts of a deep view, so skips land on and across it.
        # A count above the limit would index past the palette on the GPU.
        w = Decimal('1e-100')
        x, y, path, ref = self.make_ref(w, SPIRAL, 6000)
        pix = self.pixels(4, 60)
        full = self.exact(x, y, w, pix, 6000)
        self.assertGreater(len(set(full)), 5)
        for limit in range(200, 370, 7):
            for mode in ('dbl', 'bla'):
                got = [c for c, _ in self.run_cli(mode, path, pix, limit)]
                self.assertTrue(all(c <= limit for c in got), '%s limit %d: count above limit' % (mode, limit))
                want = [min(e, limit) for e in full]
                exact = sum(g == v for g, v in zip(got, want)) / float(len(pix))
                self.assertGreaterEqual(exact, 0.97, '%s limit %d: %.0f%% exact' % (mode, limit, exact * 100))

    def test_c_bla_follows_reference_to_its_end(self):
        # pixels at the image centre have a tiny offset, so they ride the reference orbit all the
        # way to its end, where skips must stop short of the table's last entries
        w = Decimal('1e-100')
        x, y, path, ref = self.make_ref(w, SPIRAL, 6000)
        pix = [(WIDTH // 2 + i, HEIGHT // 2 + j) for i in range(-2, 3) for j in range(-2, 3)]
        want = self.exact(x, y, w, pix, 6000)
        for mode in ('dbl', 'bla'):
            got = [c for c, _ in self.run_cli(mode, path, pix, 6000)]
            self.assertEqual(got, want, mode)

    def test_c_bla_table_error_is_bounded(self):
        # Inside each entry's stated radius, a skip must agree with iterating step by step to
        # about BLA_EPS. Catches wrong coefficient composition or a too-generous radius.
        if CLI is None:
            self.skipTest('gcc not available')
        eps = 2.0 ** -24
        for w, center in (('1e-100', SPIRAL), ('1e-30', SPIRAL), ('1e-8', MINIBROT), ('1e-12', MINIBROT),
                          ('1e-6', SEAHORSE)):
            x, y, path, ref = self.make_ref(Decimal(w), center, 6000)
            out = subprocess.run([CLI, 'blacheck', path, '1'], capture_output=True, text=True, check=True).stdout
            checked = 0
            for line in out.strip().split('\n'):
                level, used, err = line.split()
                if int(used):
                    checked += 1
                    self.assertLessEqual(float(err), 2.5 * eps, '%s %s level %s: error %s' % (center[0], w, level, err))
            self.assertGreater(checked, 0)

    def test_c_bla_skips_obey_invariants(self):
        # Checks every skip the loop makes, from a trace of the real code: it must start on a
        # multiple of its length, stay inside the reference orbit, and not cross the iteration limit.
        # The nucleus view matters: its reference passes through Z = 0 (radius 0), so pixels are
        # forced into plain steps and arrive at unaligned positions of the table.
        if CLI is None:
            self.skipTest('gcc not available')
        centre = [(WIDTH // 2 + i, HEIGHT // 2 + j) for i in range(-2, 3) for j in range(-2, 3)]
        for w, center, limits in (('1e-100', SPIRAL, (6000, 300, 333, 351, 364, 371)),
                                  ('1e-8', MINIBROT, (3000, 1001, 2999))):
            x, y, path, ref = self.make_ref(Decimal(w), center, 6000)
            last = len(ref.orbit) - 1
            skips = 0
            for limit in limits:
                res = subprocess.run([CLI, 'bla', path, str(limit)], env=dict(os.environ, PERT_TRACE='1'),
                                     capture_output=True, text=True,
                                     input=''.join('%d %d\n' % p for p in self.pixels(6, 40) + centre))
                self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                for line in res.stderr.split('\n'):
                    fields = line.split()
                    if len(fields) != 3 or fields[0] == 'pixel':
                        continue
                    n, span, cnt = (int(v) for v in fields)
                    self.assertEqual(n % span, 0, '%s: skip of %d starts at unaligned n=%d' % (w, span, n))
                    self.assertLessEqual(n + span, last, '%s: skip of %d from n=%d runs past the reference' % (w, span, n))
                    self.assertLessEqual(cnt + span, limit, '%s: skip of %d at count %d crosses limit %d' % (w, span, cnt, limit))
                    skips += span > 1
            self.assertGreater(skips, 100, '%s: the test never exercised a real skip' % w)


if __name__ == '__main__':
    unittest.main()
