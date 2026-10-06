#!/usr/bin/env python3
"""Tests for drawing z^d + c: the function files (--func), the plain, perturbation, BLA and floatexp paths of
mand-cpu for d > 2, and the pieces of pert.h / bla.c that the GPU build shares.

The oracle is independent of the code under test: exact iteration with gmpy2's complex numbers (their own
power function, at high precision), and the smooth count written out again here from its definition.
Skipped when gcc/OpenMP are unavailable.
"""
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from array import array
from decimal import Decimal, localcontext

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import gmpy2
import deepzoom
import funcspec
import test_cpu_renderer as tcr
from deepzoom import WIDTH, HEIGHT, BAILOUT2, POWER_MIN_DEGREE, POWER_MAX_DEGREE

MAND = None       # mand-cpu
MAND_FX = None    # the same with the floatexp threshold lowered, so a cheap view uses that path
POW_CLI = None    # tests/pow_cli.c
TMP = None
BLA_EPS = 2.0 ** -24


def setUpModule():
    global MAND, MAND_FX, POW_CLI, TMP
    if not shutil.which('gcc') or not shutil.which('make'):
        return
    if subprocess.run(tcr.gcc_command('/dev/null'), capture_output=True).returncode:
        return
    TMP = tempfile.mkdtemp()
    subprocess.check_call(['make', '-C', ROOT, 'mand-cpu'], stdout=subprocess.DEVNULL)
    MAND = os.path.join(ROOT, 'mand-cpu')
    MAND_FX = os.path.join(TMP, 'mand-cpu-fx')
    subprocess.check_call(tcr.gcc_command(MAND_FX, '-DFX_STEP_EXP=(-10)'))
    POW_CLI = os.path.join(TMP, 'pow_cli')
    cmd = ['gcc', '-std=c99', '-O1', '-g', '-Wall', '-Wextra', '-pedantic', '-I', ROOT, '-o', POW_CLI,
           os.path.join(ROOT, 'tests', 'pow_cli.c'), os.path.join(ROOT, 'bla.c'), '-lm']
    if subprocess.run(cmd + ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'], capture_output=True).returncode:
        subprocess.check_call(cmd)


def tearDownModule():
    if TMP:
        shutil.rmtree(TMP, ignore_errors=True)


# -- the independent oracle ---------------------------------------------------------------------

def smooth_nu(idx, zz, d):
    """The smooth iteration count of z^d + c, from its definition: log_d(log|z|) grows by one per iteration."""
    return max(idx + 2.0 - math.log(0.5 * math.log2(zz)) / math.log(d), 0.0)


def exact_nu(cx, cy, d, iterations, bits):
    """Smooth count of the point c = cx + i cy (decimal strings) by iteration at `bits` bits; -1 inside."""
    with gmpy2.context(precision=bits):
        c = gmpy2.mpc(gmpy2.mpfr(cx), gmpy2.mpfr(cy))
        z = gmpy2.mpc(0)
        for n in range(iterations):
            z = z ** d + c
            zz = float(z.real * z.real + z.imag * z.imag)
            if zz > BAILOUT2:
                return smooth_nu(n, zz, d)
    return -1.0


def misiurewicz(d, k, bits):
    """A boundary point of the d-th degree set with structure at every depth. With w = exp(2 pi i k / d), p the
    root of p^(d-1) = 1 - w and c = p - p^d, the critical orbit runs 0, c, p, p, p, ... onto a repelling fixed point.
    Returns (re, im) as mpfr."""
    with gmpy2.context(precision=bits):
        angle = 2 * gmpy2.const_pi() * k / d
        w = gmpy2.mpc(gmpy2.cos(angle), gmpy2.sin(angle))
        p = (1 - w) ** (gmpy2.mpfr(1) / (d - 1))
        c = p - p ** d
        return c.real, c.imag


def view_around(point, w, digits):
    """(x, y) lower-left corner of the view of width w centered on the point, as decimal strings."""
    with localcontext() as ctx:
        ctx.prec = digits + 30
        with gmpy2.context(precision=int(digits * 3.33) + 120):
            cx = Decimal(point[0].__format__('.%df' % (digits + 20)))
            cy = Decimal(point[1].__format__('.%df' % (digits + 20)))
        w = Decimal(w)
        return str(cx - w / 2), str(cy - w * HEIGHT / (2 * WIDTH))


def pixel_c(x, y, w, px, py, bits):
    """The c of pixel (px, py) of the view with lower-left corner (x, y): decimal strings."""
    with gmpy2.context(precision=bits):
        step = gmpy2.mpfr(str(w)) / WIDTH
        return str(gmpy2.mpfr(x) + step * px), str(gmpy2.mpfr(y) + step * py)


# -- function files -----------------------------------------------------------------------------

BAD_FILES = {
    'an empty file': '',
    'no first line': 'kind power\ndegree 3\n',
    'a wrong first line': 'gpumand-func 2\nkind power\ndegree 3\n',
    'a first line with more on it': 'gpumand-func 1 extra\nkind power\ndegree 3\n',
    'a missing kind': 'gpumand-func 1\ndegree 3\n',
    'a missing degree': 'gpumand-func 1\nkind power\n',
    'an unknown kind': 'gpumand-func 1\nkind tape\ndegree 3\n',
    'an unknown key': 'gpumand-func 1\nkind power\ndegree 3\nspeed fast\n',
    'a repeated kind': 'gpumand-func 1\nkind power\nkind power\ndegree 3\n',
    'a repeated degree': 'gpumand-func 1\nkind power\ndegree 3\ndegree 4\n',
    'a degree below the range': 'gpumand-func 1\nkind power\ndegree %d\n' % (POWER_MIN_DEGREE - 1),
    'a degree above the range': 'gpumand-func 1\nkind power\ndegree %d\n' % (POWER_MAX_DEGREE + 1),
    'a negative degree': 'gpumand-func 1\nkind power\ndegree -3\n',
    'a fractional degree': 'gpumand-func 1\nkind power\ndegree 2.5\n',
    'a text degree': 'gpumand-func 1\nkind power\ndegree three\n',
    'a line with one word': 'gpumand-func 1\nkind power\ndegree\n',
    'a line with three words': 'gpumand-func 1\nkind power\ndegree 3 4\n',
    'a line that is too long': 'gpumand-func 1\nkind power\ndegree 3\n' + 'x' * 400 + '\n',
    'far too many lines': 'gpumand-func 1\nkind power\ndegree 3\n' + '\n' * 100,
}


class FuncFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, text):
        path = os.path.join(self.tmp, 'f%d.func' % len(os.listdir(self.tmp)))
        with open(path, 'w') as fp:
            fp.write(text)
        return path

    def test_degree_range_is_the_one_in_the_c_header(self):
        self.assertEqual((POWER_MIN_DEGREE, POWER_MAX_DEGREE), (2, 64))

    def test_round_trip_for_every_degree(self):
        for d in range(POWER_MIN_DEGREE, POWER_MAX_DEGREE + 1):
            path = os.path.join(self.tmp, 'd%d.func' % d)
            funcspec.write_power_spec(path, d)
            self.assertEqual(funcspec.read_spec(path), {'kind': 'power', 'degree': d})

    def test_writing_refuses_bad_degrees(self):
        for bad in (1, 0, -3, 65, 1000, 2.5, '3', None, True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                funcspec.power_spec_text(bad)

    def test_the_python_reader_refuses_bad_files(self):
        for label, text in BAD_FILES.items():
            with self.assertRaises(ValueError, msg=label):
                funcspec.read_spec(self.write(text))

    def test_the_python_reader_accepts_blank_lines_and_windows_line_ends(self):
        self.assertEqual(funcspec.read_spec(self.write('gpumand-func 1\r\n\r\nkind power\r\ndegree 5\r\n')), {'kind': 'power', 'degree': 5})

    def render(self, *args):
        out = os.path.join(self.tmp, 'out%d.bmp' % len(os.listdir(self.tmp)))
        res = subprocess.run([MAND, '-1.2', '-0.8', '2.4', out, '1', *args], capture_output=True, text=True)
        return res, out

    @unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
    def test_the_renderer_refuses_bad_files_and_draws_nothing(self):
        if MAND is None:
            self.skipTest('gcc with OpenMP not available')
        for label, text in BAD_FILES.items():
            res, out = self.render('--func=' + self.write(text))
            self.assertNotEqual(res.returncode, 0, label)
            self.assertTrue(res.stderr.strip(), label)
            self.assertFalse(os.path.exists(out), label)
        res, out = self.render('--func=' + os.path.join(self.tmp, 'missing.func'))
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('cannot open', res.stderr)
        res, out = self.render('--func=' + self.tmp)                 # a folder
        self.assertNotEqual(res.returncode, 0)
        res, out = self.render('--func=')
        self.assertNotEqual(res.returncode, 0)

    @unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
    def test_the_renderer_says_what_is_wrong_and_where(self):
        if MAND is None:
            self.skipTest('gcc with OpenMP not available')
        res, _ = self.render('--func=' + self.write('gpumand-func 1\nkind power\ndegree 99\n'))
        self.assertIn('line 3', res.stderr)
        self.assertIn('from 2 to 64', res.stderr)
        res, _ = self.render('--func=' + self.write('gpumand-func 1\nkind power\ncolor red\n'))
        self.assertIn('line 3', res.stderr)
        self.assertIn('unknown key', res.stderr)

    @unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
    def test_the_option_works_anywhere_on_the_command_line(self):
        if MAND is None:
            self.skipTest('gcc with OpenMP not available')
        spec = self.write(funcspec.power_spec_text(3))
        out = os.path.join(self.tmp, 'a.bmp')
        for args in ([MAND, '--func=' + spec, '-1.2', '-0.8', '2.4', out, '1'],
                     [MAND, '-1.2', '-0.8', '--func=' + spec, '2.4', out, '1'],
                     [MAND, '-1.2', '-0.8', '2.4', out, '1', '--func=' + spec]):
            res = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(os.path.exists(out))
            os.remove(out)


# -- the GPU renderer (it cannot run here: only its build is checked; the kernels call the code tested below) ----

@unittest.skipIf(shutil.which('nvcc') is None, 'needs nvcc')
class GpuBuild(unittest.TestCase):
    KERNELS = ('MandKern', 'MandKernPert', 'MandKernPertFx', 'MandKernPow', 'MandKernPertPow', 'MandKernPertFxPow')

    def test_every_kernel_compiles_without_spilling_or_a_stack_frame(self):
        # the step for z^d + c was written with no per-thread array so that no kernel needs local memory; keep it so
        res = subprocess.run(['nvcc', '-Xptxas', '-v', '-arch=sm_50', '-Wno-deprecated-gpu-targets', '-c',
                              os.path.join(ROOT, 'mand-gpu.cu'), '-o', os.path.join(tempfile.mkdtemp(), 'k.o')],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        import re
        frames, name = {}, None
        for line in res.stderr.split('\n'):
            m = re.search(r'Function properties for (\S+)', line)
            if m:
                name = m.group(1)
            m = re.search(r'(\d+) bytes stack frame, (\d+) bytes spill stores, (\d+) bytes spill loads', line)
            if m and name:
                frames[name] = tuple(int(v) for v in m.groups())
        for kernel in self.KERNELS:
            found = [n for n in frames if re.match(r'_Z\d+%s[A-Z]' % kernel, n) and n.startswith('_Z%d%s' % (len(kernel), kernel))]
            self.assertEqual(len(found), 1, '%s is not among %s' % (kernel, sorted(frames)))
            self.assertEqual(frames[found[0]], (0, 0, 0), '%s uses local memory: %s' % (kernel, frames[found[0]]))

    def test_the_makefile_links_the_function_file_reader_into_mand_gpu(self):
        with open(os.path.join(ROOT, 'makefile')) as fp:
            text = fp.read()
        self.assertIn('funcspec.o', text.split('mand-gpu:')[1].split('\n')[0])


# -- the reference orbit ------------------------------------------------------------------------

class ReferenceOrbit(unittest.TestCase):
    def test_degree_two_is_the_original_orbit(self):
        a = deepzoom.reference_orbit('-0.5', '0.2', '1e-3', 300)
        b = deepzoom.reference_orbit('-0.5', '0.2', '1e-3', 300, 2)
        self.assertEqual(a, b)

    def test_orbit_follows_z_to_the_d_plus_c(self):
        for d in (3, 4, 7, 16):
            orbit = deepzoom.reference_orbit('-0.31', '0.07', '1e-3', 40, d)
            vals = [complex(orbit[2 * i], orbit[2 * i + 1]) for i in range(len(orbit) // 2)]
            c = vals[1]
            self.assertEqual(vals[0], 0)
            for i in range(1, len(vals) - 1):
                self.assertAlmostEqual(vals[i + 1], vals[i] ** d + c, delta=1e-9 * max(1.0, abs(vals[i + 1])))

    def test_orbit_stops_when_it_escapes(self):
        for d in (2, 3, 5):
            orbit = deepzoom.reference_orbit('1.5', '0', '1e-6', 1000, d)
            vals = [complex(orbit[2 * i], orbit[2 * i + 1]) for i in range(len(orbit) // 2)]
            self.assertGreater(abs(vals[-1]) ** 2, BAILOUT2)
            self.assertTrue(all(abs(v) ** 2 <= BAILOUT2 for v in vals[:-1]))
            self.assertLess(len(vals), 20)

    def test_bad_degrees_are_refused(self):
        for d in (1, 0, -2, 65):
            with self.assertRaises(ValueError):
                deepzoom.reference_orbit('0', '0', '1e-3', 10, d)


# -- the per-step arithmetic and the BLA table (the code the GPU shares) -------------------------

@unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
class SharedCode(unittest.TestCase):
    def setUp(self):
        if POW_CLI is None:
            self.skipTest('gcc not available')
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_perturbation_step_equals_the_exact_difference(self):
        # (Z + d)^p - Z^p from d * pow_q(), against exact arithmetic, for offsets from 1e-30 to 1e3 times |Z|
        rng = random.Random(7)
        cases = []
        for p in (2, 3, 4, 5, 7, 8, 16, 31, 64):
            for ratio in (1e-30, 1e-15, 1e-8, 1e-3, 0.05, 0.5, 1.0, 3.0, 100.0, 1e3):
                for _ in range(6):
                    zr, zi = rng.uniform(-2, 2), rng.uniform(-2, 2)
                    scale = math.hypot(zr, zi) * ratio
                    ang = rng.uniform(0, 2 * math.pi)
                    cases.append((p, zr, zi, scale * math.cos(ang), scale * math.sin(ang)))
        inp = ''.join('%d %s %s %s %s\n' % (p, zr.hex(), zi.hex(), dr.hex(), di.hex()) for p, zr, zi, dr, di in cases)
        out = subprocess.run([POW_CLI, 'delta'], input=inp, capture_output=True, text=True, check=True).stdout.split('\n')
        worst = worst_benign = 0.0
        with gmpy2.context(precision=600):
            for (p, zr, zi, dr, di), line in zip(cases, out):
                got = complex(*[float.fromhex(v) for v in line.split()])
                z, d = gmpy2.mpc(zr, zi), gmpy2.mpc(dr, di)
                want = (z + d) ** p - z ** p
                miss = abs(gmpy2.mpc(got.real, got.imag) - want)
                # Backward-stable bound: no more than rounding errors of the sizes of the terms being added. (When the
                # terms cancel, as for |Z + d| < |d|, the true difference can be far smaller; the renderer rebases then.)
                terms = (abs(z) + abs(d)) ** p - abs(z) ** p
                worst = max(worst, float(miss / terms))
                if abs(d) <= 0.3 * abs(z):
                    worst_benign = max(worst_benign, float(miss / abs(want)))
        self.assertLess(worst, 1e-13, worst)
        # and where the offset is small next to Z, the step is right to a handful of rounding errors of its own size
        self.assertLess(worst_benign, 1e-12, worst_benign)

    def test_the_step_is_not_just_the_leading_terms(self):
        # mutation guard of a different kind: for d comparable to Z every term of the binomial sum matters
        inp = '5 %s %s %s %s\n' % ((1.0).hex(), (0.5).hex(), (0.7).hex(), (-0.9).hex())
        out = subprocess.run([POW_CLI, 'delta'], input=inp, capture_output=True, text=True, check=True).stdout
        got = complex(*[float.fromhex(v) for v in out.split()])
        z, d = complex(1.0, 0.5), complex(0.7, -0.9)
        self.assertAlmostEqual(got, (z + d) ** 5 - z ** 5, delta=1e-12)
        self.assertGreater(abs(got - 5 * z ** 4 * d), 1.0)          # the linear term alone would be far off

    def test_bla_skips_agree_with_stepping_inside_their_radius(self):
        for d, k in ((2, 1), (3, 1), (4, 1), (5, 2), (7, 1), (16, 3)):
            for w in ('1e-8', '1e-30'):
                bits = int(-Decimal(w).adjusted() * 3.33) + 400
                point = misiurewicz(d, k, bits + 100)
                x, y = view_around(point, w, -Decimal(w).adjusted() + 20)
                path = os.path.join(self.tmp, 'r%d_%s.ref' % (d, w))
                deepzoom.write_reference(path, x, y, w, 3000, d)
                out = subprocess.run([POW_CLI, 'blacheck', str(d), path], capture_output=True, text=True, check=True).stdout
                checked = 0
                for line in out.strip().split('\n'):
                    level, used, err = line.split()
                    if int(used):
                        checked += 1
                        self.assertLessEqual(float(err), 2.5 * BLA_EPS, 'd=%d %s level %s: error %s' % (d, w, level, err))
                # (the orbit expands by |d p^(d-1)| per step, so only the first few levels have a radius at all in a
                # view this wide; a narrower view has more)
                self.assertGreaterEqual(checked, 1 if w == '1e-8' else 4, 'd=%d %s: the table was barely exercised' % (d, w))

    def test_the_table_for_degree_two_is_the_original_table(self):
        # bla_build_pow with p = 2 must give bla_build's table: the same entries have a usable radius at every level
        path = os.path.join(self.tmp, 'two.ref')
        point = misiurewicz(2, 1, 400)
        x, y = view_around(point, '1e-10', 40)
        deepzoom.write_reference(path, x, y, '1e-10', 3000, 2)
        mine = subprocess.run([POW_CLI, 'blacheck', '2', path], capture_output=True, text=True, check=True).stdout
        cli = os.path.join(TMP, 'pert_cli_for_pow_tests')
        if not os.path.exists(cli):
            subprocess.check_call(['gcc', '-std=c99', '-O1', '-I', ROOT, '-o', cli, os.path.join(ROOT, 'tests', 'pert_cli.c'),
                                   os.path.join(ROOT, 'bla.c'), '-lm'])
        theirs = subprocess.run([cli, 'blacheck', path, '1'], capture_output=True, text=True, check=True).stdout
        used = lambda text: [line.split()[:2] for line in text.strip().split('\n')]
        self.assertEqual(used(mine), used(theirs))         # the same entries are usable at every level


# -- the renderer ---------------------------------------------------------------------------------

@unittest.skipIf(shutil.which('gcc') is None, 'needs gcc')
class PowerRenderer(unittest.TestCase):
    def setUp(self):
        if MAND is None:
            self.skipTest('gcc with OpenMP not available')
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def render(self, exe, x, y, w, d, mult=1, ref=None, expect_path=None, spec=True):
        n = len(os.listdir(self.tmp))
        out, nuf = os.path.join(self.tmp, 'out%d.bmp' % n), os.path.join(self.tmp, 'out%d.nu' % n)
        cmd = [exe, str(x), str(y), str(w), out, str(mult)] + ([ref] if ref else []) + ['--nu-out=' + nuf]
        if spec:
            path = os.path.join(self.tmp, 'spec%d.func' % d)
            funcspec.write_power_spec(path, d)
            cmd.append('--func=' + path)
        res = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, MAND_VERBOSE='1'))
        self.assertEqual(res.returncode, 0, res.stderr)
        if expect_path:
            self.assertIn('mand-cpu: %s path' % expect_path, res.stderr)
        return tcr.read_nu(nuf)

    def make_ref(self, x, y, w, maxiter, d):
        path = os.path.join(self.tmp, 'r%d.ref' % len(os.listdir(self.tmp)))
        deepzoom.write_reference(path, x, y, w, maxiter, d)
        return path

    def compare(self, nu, x, y, w, d, iterations, count, seed, tol, min_match):
        """Sampled pixels against exact iteration; returns how many were inside and how many distinct escape values."""
        rng = random.Random(seed)
        bits = max(200, int(-Decimal(w).adjusted() * 3.33) + 192)
        match = inside = 0
        seen = set()
        for _ in range(count):
            px, py = rng.randrange(WIDTH), rng.randrange(HEIGHT)
            cx, cy = pixel_c(x, y, w, px, py, bits)
            want, got = exact_nu(cx, cy, d, iterations, bits), nu[WIDTH * py + px]
            inside += want == -1.0
            seen.add(round(got, 1))
            match += (got == -1.0) if want == -1.0 else (got >= 0 and abs(got - want) < tol)
        self.assertGreaterEqual(match / float(count), min_match, 'd=%d w=%s: %d of %d match' % (d, w, match, count))
        return inside, len(seen)

    def test_plain_path_matches_exact_iteration(self):
        for d in (2, 3, 4, 5, 7, 16, 64):
            nu = self.render(MAND, '-1.2', '-0.8', '2.4', d, expect_path='plain')
            inside, distinct = self.compare(nu, '-1.2', '-0.8', '2.4', d, 2000, 120, d, 1e-6, 0.97)
            self.assertGreater(inside, 5, 'd=%d: nothing sampled inside the set' % d)
            self.assertTrue(any(v >= 0 for v in nu) and any(v == -1.0 for v in nu))
            self.assertGreater(distinct, 5, 'd=%d: too little variety to mean anything' % d)

    def test_perturbation_with_bla_matches_exact_iteration(self):
        for d, k in ((2, 1), (3, 1), (4, 1), (5, 2), (7, 1), (16, 3)):
            for w in ('1e-6', '1e-30'):
                digits = -Decimal(w).adjusted() + 20
                x, y = view_around(misiurewicz(d, k, int(digits * 3.33) + 200), w, digits)
                ref = self.make_ref(x, y, w, 2000, d)
                nu = self.render(MAND, x, y, w, d, ref=ref, expect_path='perturbation+BLA')
                inside, distinct = self.compare(nu, x, y, w, d, 2000, 50, d + 31, 1e-3, 0.96)
                self.assertGreater(distinct, 8, 'd=%d %s: no structure in the view' % (d, w))

    def test_floatexp_path_matches_exact_iteration(self):
        # the floatexp loop on a cheap view (threshold lowered in this build), then for real below 1e-300
        for d, k in ((3, 1), (4, 1), (7, 1)):
            w = '1e-6'
            x, y = view_around(misiurewicz(d, k, 400), w, 26)
            ref = self.make_ref(x, y, w, 2000, d)
            nu = self.render(MAND_FX, x, y, w, d, ref=ref, expect_path='floatexp')
            inside, distinct = self.compare(nu, x, y, w, d, 2000, 50, d + 7, 1e-3, 0.96)
            self.assertGreater(distinct, 8)
        for d, k in ((3, 1), (5, 1)):
            w = '1e-300'
            digits = 320
            x, y = view_around(misiurewicz(d, k, int(digits * 3.33) + 200), w, digits)
            ref = self.make_ref(x, y, w, 2000, d)
            nu = self.render(MAND, x, y, w, d, ref=ref, expect_path='floatexp')
            inside, distinct = self.compare(nu, x, y, w, d, 2000, 30, d + 99, 1e-3, 0.96)
            self.assertGreater(distinct, 8)

    def test_degree_two_through_the_new_code_matches_the_original_code(self):
        # plain path: the same arithmetic, so the same numbers
        a = self.render(MAND, '-2', '-1.333333', '4', 2, spec=False)
        b = self.render(MAND, '-2', '-1.333333', '4', 2, spec=True)
        differ = sum(1 for u, v in zip(a, b) if abs(u - v) > 1e-9 and not (u == -1.0 and v == -1.0))
        self.assertLess(differ, len(a) // 5000, differ)
        # perturbation: rounded a little differently, so allow a sliver of chaotic pixels
        w = '1e-20'
        x, y = view_around(misiurewicz(2, 1, 400), w, 40)
        ref = self.make_ref(x, y, w, 2000, 2)
        a = self.render(MAND, x, y, w, 2, ref=ref, spec=False)
        b = self.render(MAND, x, y, w, 2, ref=ref, spec=True)
        differ = sum(1 for u, v in zip(a, b) if (u == -1.0) != (v == -1.0) or (u != -1.0 and abs(u - v) > 1e-3))
        self.assertLess(differ, len(a) // 500, differ)

    def test_other_degrees_really_differ(self):
        a = self.render(MAND, '-1.2', '-0.8', '2.4', 3)
        b = self.render(MAND, '-1.2', '-0.8', '2.4', 4)
        c = self.render(MAND, '-1.2', '-0.8', '2.4', 2, spec=False)
        self.assertGreater(sum(1 for u, v in zip(a, b) if u != v), len(a) // 10)
        self.assertGreater(sum(1 for u, v in zip(a, c) if u != v), len(a) // 10)

    def test_smooth_count_has_no_bands(self):
        # just outside the set, escape counts step from one value to the next across the view; the smooth count
        # must change by tiny amounts between neighboring pixels, and cover a range of about one whole step
        for d in (2, 3, 4, 7, 16):
            nu = self.render(MAND, '1.05', '-0.4', '0.9', d)
            self.assertTrue(all(v >= 0 for v in nu))
            worst = max(abs(nu[WIDTH * y + x] - nu[WIDTH * y + x + 1]) for y in range(0, HEIGHT, 4) for x in range(WIDTH - 1))
            self.assertLess(worst, 0.03, 'd=%d: neighbors differ by %.4f' % (d, worst))
            self.assertGreater(max(nu) - min(nu), 0.5, 'd=%d: the view crosses no band edge' % d)

    def test_smooth_count_formula_on_first_iteration_escapes(self):
        # for c with |c| > 256 the first iteration escapes, z = c, so nu = smooth_nu(0, |c|^2, d) exactly
        for d in (2, 3, 8, 64):
            nu = self.render(MAND, '299', '-0.5', '2', d)
            step = 2.0 / WIDTH
            for px, py in ((0, 0), (WIDTH - 1, HEIGHT - 1), (600, 400), (123, 456)):
                cx, cy = 299.0 + step * px, -0.5 + step * py
                self.assertAlmostEqual(nu[WIDTH * py + px], smooth_nu(0, cx * cx + cy * cy, d), delta=1e-9)


if __name__ == '__main__':
    unittest.main()
