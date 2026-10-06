#!/usr/bin/env python3
"""Compares the GPU renderer with the CPU renderer on a set of views. Run it on a machine with an NVIDIA GPU:

    make gpu cpu
    python3 tests/compare_gpu_cpu.py

The CPU renderer is the one the test suite checks against exact arithmetic; the GPU renderer shares its per-pixel
code, so the two should agree except for pixels where the GPU's fused multiply-adds change a chaotic orbit in the last
bits. For each view it reports how many pixels differ (inside/outside the set, or smooth count by more than 1e-3) and
the time each renderer took. Exit status 0 if every view is within 0.5% of its pixels, 1 otherwise.

    --gpu PATH   the GPU renderer to test (default ./mand-gpu); --cpu PATH   the reference (default ./mand-cpu)
    --only TEXT  run only the views whose name contains TEXT
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import time
from array import array
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import deepzoom                                             # noqa: E402
import funcspec                                             # noqa: E402
from test_power import misiurewicz, view_around             # noqa: E402

WIDTH, HEIGHT = deepzoom.WIDTH, deepzoom.HEIGHT
TOLERANCE = 1e-3
ALLOWED = 0.005


def read_nu(path):
    with open(path, 'rb') as fp:
        magic, w, h = struct.unpack('<4sII', fp.read(12))
        nu = array('d')
        nu.frombytes(fp.read(8 * w * h))
    assert magic == b'MNU1' and (w, h) == (WIDTH, HEIGHT)
    return nu


def views():
    """(name, x, y, width, multiplier, degree or None for z^2). Deep views are centered on boundary points."""
    out = [('z^2 whole set, plain', '-2.75', '-1.333333', '4', 1, None),
           ('z^2 seahorse valley, plain', '-0.75', '0.1', '0.1', 3, None),
           ('z^3 plain', '-1.2', '-0.8', '2.4', 2, 3),
           ('z^4 plain', '-1.2', '-0.8', '2.4', 2, 4),
           ('z^7 plain', '-1.2', '-0.8', '2.4', 2, 7)]
    for degree, k in ((None, 1), (3, 1), (7, 1)):
        d = degree or 2
        for w, label in (('1e-30', 'perturbation + BLA'), ('1e-300', 'floatexp')):
            digits = -Decimal(w).adjusted() + 20
            x, y = view_around(misiurewicz(d, k, int(digits * 3.33) + 200), w, digits)
            out.append(('z^%d %s, width %s' % (d, label, w), x, y, w, 1, degree))
    return out


def render(exe, tmp, tag, x, y, w, mult, degree):
    out, nuf = os.path.join(tmp, tag + '.bmp'), os.path.join(tmp, tag + '.nu')
    cmd = [exe, x, y, w, out, str(mult)]
    if Decimal(w) < deepzoom.PERTURB_BELOW:
        ref = os.path.join(tmp, tag + '.ref')
        deepzoom.write_reference(ref, x, y, w, deepzoom.ITERATIONS * mult, degree or 2)
        cmd.append(ref)
    cmd.append('--nu-out=' + nuf)
    if degree:
        spec = os.path.join(tmp, 'pow%d.func' % degree)
        funcspec.write_power_spec(spec, degree)
        cmd.append('--func=' + spec)
    started = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - started
    if res.returncode != 0:
        raise RuntimeError('%s failed:\n%s' % (os.path.basename(exe), res.stderr.strip()))
    return read_nu(nuf), elapsed


def compare(a, b):
    differ, worst = 0, 0.0
    for u, v in zip(a, b):
        if (u == -1.0) != (v == -1.0):
            differ += 1
        elif u != -1.0 and abs(u - v) > TOLERANCE:
            differ += 1
            worst = max(worst, abs(u - v))
    return differ, worst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gpu', default=os.path.join(ROOT, 'mand-gpu'))
    ap.add_argument('--cpu', default=os.path.join(ROOT, 'mand-cpu'))
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    for exe in (args.gpu, args.cpu):
        if not os.access(exe, os.X_OK):
            sys.exit('%s is not built (make gpu cpu)' % exe)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for number, (name, x, y, w, mult, degree) in enumerate(views()):
            if args.only not in name:
                continue
            try:
                cpu, cpu_time = render(args.cpu, tmp, 'cpu%d' % number, x, y, w, mult, degree)
                gpu, gpu_time = render(args.gpu, tmp, 'gpu%d' % number, x, y, w, mult, degree)
            except RuntimeError as e:
                print('FAIL  %-40s %s' % (name, e))
                failures += 1
                continue
            differ, worst = compare(cpu, gpu)
            share = differ / float(len(cpu))
            ok = share <= ALLOWED
            failures += not ok
            print('%s  %-40s %6d of %d pixels differ (%.3f%%), worst smooth-count gap %.3g; CPU %.1fs, GPU %.1fs'
                  % ('ok  ' if ok else 'FAIL', name, differ, len(cpu), 100 * share, worst, cpu_time, gpu_time))
    print('\n%s' % ('all views agree' if not failures else '%d view(s) differ more than %.1f%%' % (failures, 100 * ALLOWED)))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
