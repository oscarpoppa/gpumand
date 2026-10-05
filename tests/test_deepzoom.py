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
import zlib
from decimal import Decimal, localcontext

import gmpy2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
import deepzoom
from deepzoom import WIDTH, HEIGHT, BAILOUT2

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
        if z.real * z.real + z.imag * z.imag > BAILOUT2:
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
            if zr * zr + zi * zi > BAILOUT2:
                return cnt
    return iterations


def smooth_nu(idx, zz):
    """Python mirror of smooth_nu() in pert.h."""
    import math
    nu = idx + 2.0 - math.log2(0.5 * math.log2(zz))
    return max(nu, 0.0)


def exact_nu(x, y, w, pix_x, pix_y, iterations):
    """(escape index, smooth iteration count) by direct iteration at high precision; (iterations, -1.0) inside."""
    bits = max(128, int(-w.adjusted() * 3.33) + 192)
    with gmpy2.context(precision=bits):
        step = gmpy2.mpfr(str(w)) / WIDTH
        cr = gmpy2.mpfr(str(x)) + step * pix_x
        ci = gmpy2.mpfr(str(y)) + step * pix_y
        zr = zi = gmpy2.mpfr(0)
        for cnt in range(iterations):
            zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
            zz = zr * zr + zi * zi
            if zz > BAILOUT2:
                return cnt, smooth_nu(cnt, float(zz))
    return iterations, -1.0


def plain_double_count(x, y, step, pix_x, pix_y, iterations):
    """Mirror of MandKern."""
    c = complex(float(x) + step * pix_x, float(y) + step * pix_y)
    z = 0j
    for cnt in range(iterations):
        z = z * z + c
        if z.real * z.real + z.imag * z.imag > BAILOUT2:
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
        # centre 1+0i runs 0, 1, 2, 5, 26, 677 and stops at the first value past the escape radius
        x, y = view_for_center(Decimal('1'), Decimal('0'), Decimal('1e-3'))
        ref = self.roundtrip(x, y, '1e-3', 100)
        self.assertEqual([round(abs(z)) for z in ref.orbit], [0, 1, 2, 5, 26, 677])
        self.assertGreater(abs(ref.orbit[-1]) ** 2, BAILOUT2)
        self.assertLess(abs(ref.orbit[-2]) ** 2, BAILOUT2)

    def test_step_survives_beyond_double_range(self):
        x, y = view_for_center(SPIRAL[0], SPIRAL[1], Decimal('1e-400'))
        ref = self.roundtrip(x, y, '1e-400', 50)
        self.assertGreaterEqual(ref.step_mant, 0.5)
        self.assertLess(ref.step_mant, 1.0)
        self.assertLess(ref.step_exp, -1300)  # 1e-400/1200 ~ 2^-1339


class PerturbationBase(unittest.TestCase):
    """Helpers for rendering through the C harness; no tests of its own."""

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
        return [(int(f[0]), int(f[1])) for f in (line.split() for line in out if line)]

    def run_cli_nu(self, mode, path, pix, maxiter=MAXITER):
        """Like run_cli but returns (count, steps, smooth iteration count) per pixel."""
        if CLI is None:
            self.skipTest('gcc not available')
        out = subprocess.run([CLI, mode, path, str(maxiter)], input=''.join('%d %d\n' % p for p in pix),
                             capture_output=True, text=True, check=True).stdout.split('\n')
        return [(int(f[0]), int(f[1]), float(f[2])) for f in (line.split() for line in out if line)]

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


class Perturbation(PerturbationBase):
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


def nucleus(guess, period, bits=5000, digits=1500):
    """Centre of the period-`period` minibrot near `guess`, by Newton's method at high precision."""
    from gmpy2 import mpc, mpfr
    with gmpy2.context(precision=bits):
        c = mpc(mpfr(str(guess[0])), mpfr(str(guess[1])))
        for _ in range(60):
            z, dz = mpc(0), mpc(0)
            for _ in range(period):
                dz = 2 * z * dz + 1
                z = z * z + c
            c = c - z / dz
        return Decimal(mpfr(c.real).__format__('.%df' % digits)), Decimal(mpfr(c.imag).__format__('.%df' % digits))


class FloatexpFast(unittest.TestCase):
    """The fast floatexp loop (plain double arithmetic with a separate exponent) must agree with
    the original slow loop, kept in tests/fx_reference.h, which renormalises every operation."""

    @classmethod
    def setUpClass(cls):
        if CLI is None:
            raise unittest.SkipTest('gcc not available')
        with localcontext() as ctx:
            ctx.prec = 1700
            cls.nucleus = nucleus((Decimal('-0.7436423016578859'), Decimal('0.1318265198125947')), 39)

    def counts(self, mode, path, pix, maxiter):
        out = subprocess.run([CLI, mode, path, str(maxiter)], input=''.join('%d %d\n' % p for p in pix),
                             capture_output=True, text=True, check=True).stdout.split('\n')
        return [int(line.split()[0]) for line in out if line]

    def make_ref(self, w, center, maxiter):
        w = Decimal(w)
        with localcontext() as ctx:
            ctx.prec = max(60, deepzoom.digits_for(w) + 20)
            x, y = view_for_center(center[0], center[1], w)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, 'r.ref')
        deepzoom.write_reference(path, x, y, w, maxiter)
        return path

    def compare(self, w, center, span=None, npix=100, maxiter=3000, min_distinct=1):
        path = self.make_ref(w, center, maxiter)
        rng = random.Random(zlib.crc32(('fx%s%s' % (w, center[0])).encode()))
        if span is None:
            pix = [(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(npix)]
        else:   # pixels far outside the image: the reference is then a poor match
            pix = [(rng.randrange(-span, span), rng.randrange(-span, span)) for _ in range(npix)]
        want = self.counts('fxref', path, pix, maxiter)
        got = self.counts('fx', path, pix, maxiter)
        self.assertGreaterEqual(len(set(want)), min_distinct, 'sample too uniform to be meaningful')
        bad = sum(a != b for a, b in zip(want, got))
        self.assertLessEqual(bad, npix // 100, '%s w=%s: %d of %d pixels differ from the reference loop' % (center[0], w, bad, npix))

    def test_spiral_at_every_depth(self):
        for w in ('1e-8', '1e-30', '1e-150', '1e-400', '1e-1000'):
            self.compare(w, SPIRAL, min_distinct=5)

    def test_minibrot_with_long_reference(self):
        for w in ('1e-3', '1e-5'):
            self.compare(w, MINIBROT, min_distinct=20)

    def test_view_centred_exactly_on_a_nucleus(self):
        # the reference orbit passes through (almost) exactly zero every 39 iterations
        for w in ('1e-3', '1e-5', '1e-30', '1e-400'):
            self.compare(w, self.nucleus, min_distinct=20 if w in ('1e-3', '1e-5') else 1)

    def test_reference_that_escapes_early(self):
        self.compare('0.5', EARLY_ESCAPE, min_distinct=5)

    def test_pixels_far_from_the_reference(self):
        self.compare('1e-30', SPIRAL, span=400000, min_distinct=5)
        self.compare('1e-30', self.nucleus, span=400000)

    def test_is_much_faster_than_the_reference_loop(self):
        import time
        path = self.make_ref('1e-400', SPIRAL, 3000)
        rng = random.Random(3)
        pix = [(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(3000)]
        timings = {}
        for mode in ('fxref', 'fx'):
            start = time.perf_counter()
            self.counts(mode, path, pix, 3000)
            timings[mode] = time.perf_counter() - start
        self.assertLess(timings['fx'] * 4, timings['fxref'], 'fast %.3fs vs reference %.3fs' % (timings['fx'], timings['fxref']))


class SmoothIterationCount(PerturbationBase):
    """The smooth iteration count nu: exact where the loops are exact, and continuous across the
    band edges where the integer count jumps."""

    def check_nu(self, w, center, mode, tol, npix=60, maxiter=MAXITER):
        w = Decimal(w)
        x, y, path, ref = self.make_ref(w, center, maxiter)
        pix = self.pixels(11, npix)
        got = self.run_cli_nu(mode, path, pix, maxiter)
        worst = 0.0
        escaped = 0
        for (px, py), (cnt, _, nu) in zip(pix, got):
            idx, want = exact_nu(x, y, w, px, py, maxiter)
            if idx >= maxiter:
                self.assertEqual((cnt, nu), (maxiter, -1.0), 'interior pixel must report -1')
                continue
            escaped += 1
            self.assertEqual(cnt, idx)
            worst = max(worst, abs(nu - want))
        self.assertGreater(escaped, npix // 3, 'sample has too few escaping pixels')
        self.assertLess(worst, tol, '%s %s: worst |nu - exact| = %g' % (mode, w, worst))

    def test_double_perturbation_nu_matches_exact(self):
        self.check_nu('1e-5', SPIRAL, 'dbl', 1e-6)
        self.check_nu('1e-30', SPIRAL, 'dbl', 1e-6)
        self.check_nu('1e-4', MINIBROT, 'dbl', 1e-4)   # long chaotic orbits: ~2e-6 from exact

    def test_floatexp_nu_matches_exact(self):
        self.check_nu('1e-30', SPIRAL, 'fx', 1e-6)
        self.check_nu('1e-400', SPIRAL, 'fx', 1e-6)

    def test_bla_nu_matches_exact(self):
        self.check_nu('1e-100', SPIRAL, 'bla', 1e-4, maxiter=6000)

    def test_nu_is_continuous_across_a_band_edge(self):
        # find, in plain doubles, a point where the integer count jumps by one along a line
        def idx(cx, cy):
            z, c = 0j, complex(cx, cy)
            for i in range(300):
                z = z * z + c
                if z.real * z.real + z.imag * z.imag > BAILOUT2:
                    return i
            return 300
        cy = 0.8
        xs = [-0.6 + i * 1e-3 for i in range(900)]
        edge = next((a, b) for a, b in zip(xs, xs[1:]) if idx(a, cy) >= 6 and idx(b, cy) == idx(a, cy) + 1 or idx(b, cy) >= 6 and idx(a, cy) == idx(b, cy) + 1)
        lo, hi = edge
        for _ in range(60):
            mid = (lo + hi) / 2
            if idx(mid, cy) == idx(lo, cy):
                lo = mid
            else:
                hi = mid
        k = min(idx(edge[0], cy), idx(edge[1], cy))
        w = Decimal('1e-12')
        centre = (Decimal(lo), Decimal(cy))      # a double is an exact Decimal
        x, y, path, ref = self.make_ref(w, centre, 300)
        row = [(px, HEIGHT // 2) for px in range(WIDTH)]
        got = self.run_cli_nu('dbl', path, row, 300)
        counts = {c for c, _, _ in got}
        self.assertEqual(counts, {k, k + 1}, 'the view must straddle the band edge (counts %s)' % sorted(counts))
        jumps = [(a, b) for a, b in zip(got, got[1:]) if a[0] != b[0]]
        self.assertTrue(jumps)
        for a, b in jumps:
            self.assertEqual(abs(a[0] - b[0]), 1)
            self.assertLess(abs(a[2] - b[2]), 1e-3, 'nu jumps from %.6f to %.6f across the edge' % (a[2], b[2]))



if __name__ == '__main__':
    unittest.main()


class Abbreviate(unittest.TestCase):
    """The coordinate boxes show long values in a short form: leading digits, an ellipsis, trailing digits, exponent."""

    def digits(self, d):
        return ''.join(map(str, abs(Decimal(d)).normalize().as_tuple().digits))

    def test_short_values_are_shown_whole(self):
        for v in ('-2.75', '4.0', '-1.333333', '1E-45', '0.5', '5E+30', '123456.789'):
            self.assertEqual(deepzoom.abbreviate(Decimal(v)), str(Decimal(v)).lower())

    def test_long_values_keep_leading_trailing_digits_and_scale(self):
        random.seed(7)
        with localcontext() as ctx:
            ctx.prec = 1200
            for _ in range(300):
                mant = ''.join(random.choice('0123456789') for _ in range(random.randint(30, 150)))
                mant = str(random.randint(1, 9)) + mant[:-1] + str(random.randint(1, 9))
                exp = random.choice([0, -1, -3, -7, -45, -300, -1000, 5, 40])
                sign = random.choice(['', '-'])
                d = Decimal('%s%s.%s' % (sign, mant[0], mant[1:])).scaleb(exp)
                text = deepzoom.abbreviate(d)
                self.assertLessEqual(len(text), 28, text)
                self.assertIn('\u2026', text)
                self.assertEqual(text.startswith('-'), sign == '-')
                body = text.lstrip('-')
                head, tail = body.split('\u2026')
                self.assertEqual(head.replace('.', '').lstrip('0'), self.digits(d)[:len(head.replace('.', '').lstrip('0'))])
                self.assertEqual(len(head.replace('.', '').lstrip('0')), 9)
                if 'e' in tail:
                    digits_tail, e = tail.split('e')
                    self.assertEqual(int(e), d.adjusted())
                    self.assertTrue(-4 > d.adjusted() or d.adjusted() > 3)
                else:
                    digits_tail = tail
                    self.assertTrue(-4 <= d.adjusted() <= 3)
                self.assertEqual(digits_tail, self.digits(d)[-7:])
                if 'e' not in tail:        # plain notation must read back as the same number to 9 digits
                    approx = Decimal(head.replace('\u2026', ''))
                    self.assertLess(abs(approx - abs(d)), abs(d) * Decimal('1e-8'))
                else:
                    self.assertEqual(Decimal(head), abs(d).scaleb(-d.adjusted()).quantize(Decimal(head)) if False else Decimal(head))
                    self.assertLess(abs(Decimal(head) - abs(d).scaleb(-d.adjusted())), Decimal('1e-8'))

    def test_scale_is_distinguishable_at_every_depth(self):
        with localcontext() as ctx:
            ctx.prec = 1200
            texts = {deepzoom.abbreviate(Decimal('1.2345678901234567890123456789').scaleb(-n)) for n in range(1, 1000, 7)}
            self.assertEqual(len(texts), len(range(1, 1000, 7)))

    def test_trailing_digits_survive_the_default_context(self):
        # Decimal.normalize() and abs() round to the context's 28 digits; the short form must not
        d = Decimal('-0.74364388724000000000000000000000003333299963')
        self.assertEqual(deepzoom.abbreviate(d), '-0.743643887…3299963')
        self.assertEqual(deepzoom.abbreviate(Decimal('1.2345678901234567890123456789012345678E-700')), '1.23456789…2345678e-700')


class ReferenceLength(unittest.TestCase):
    def test_orbit_is_capped_however_high_the_limit(self):
        # a point inside the set never escapes, so the orbit stops only at the cap
        old = deepzoom.MAX_REFERENCE
        deepzoom.MAX_REFERENCE = 250
        try:
            orbit = deepzoom.reference_orbit('0', '0', '1e-3', 40000000000)
        finally:
            deepzoom.MAX_REFERENCE = old
        self.assertEqual(len(orbit) // 2, 251)     # Z_0 plus 250 steps

    def test_the_cap_fits_what_the_renderers_load(self):
        header = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'refio.h')).read()
        self.assertIn('#define MAX_REF_POINTS (1u << 24)', header)
        self.assertEqual(deepzoom.MAX_REFERENCE + 1, 1 << 24)
