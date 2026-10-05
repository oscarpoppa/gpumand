#!/usr/bin/env python3
"""Arbitrary-precision support for deep zooms.

The GPU renderer iterates in double precision, which stops resolving
pixels once the view is narrower than ~1e-13. For deeper views we compute
one reference orbit at the centre of the image here, in arbitrary
precision, and the renderer iterates each pixel's small difference from it
(perturbation theory) in plain double.

This module also holds the Decimal coordinate math used by the GUI, so that
repeated zooms never round the view through a float.

Reference file format (little-endian): a 16-byte header {uint32 count, int32 step_exp,
float64 step_mant}, then count pairs of float64 (re, im) for Z_0 .. Z_{count-1}, where
Z_0 = 0 and Z_{n+1} = Z_n^2 + C. The pixel spacing is step_mant * 2**step_exp (kept
split so it survives widths below double's ~1e-308 range). The orbit stops after the
first Z with |Z|^2 > BAILOUT2 (the renderers' escape radius, so pixels that stay close to
the reference escape in step with it), or after maxiter steps.
"""
import math
import os
import re
import struct
import sys
from array import array
from collections import namedtuple
from decimal import Decimal, localcontext

import gmpy2

HERE = os.path.dirname(os.path.abspath(__file__))


def read_define(header, name):
    """Read an integer #define from one of the C headers, so sizes cannot drift."""
    with open(os.path.join(HERE, header)) as fp:
        match = re.search(r'#define\s+%s\s+(\d+)' % name, fp.read())
    if not match:
        raise ValueError('%s not defined in %s' % (name, header))
    return int(match.group(1))


ITERATIONS = read_define('iter.h', 'ITERATIONS')
BAILOUT2 = read_define('iter.h', 'BAILOUT2')
WIDTH = read_define('aspect.h', 'WIDTH')
HEIGHT = read_define('aspect.h', 'HEIGHT')

# Below this view width the plain double kernel loses pixels; use perturbation.
PERTURB_BELOW = Decimal('1e-9')


def digits_for(w):
    """Decimal digits needed to place a point inside a view of width w."""
    return max(30, -Decimal(w).adjusted() + 30)


def abbreviate(value, head=9, tail=7, limit=24):
    """Short text for a long Decimal that still shows its scale: leading digits, an ellipsis, trailing digits,
    and the power of ten when the number is not near 1 (e.g. 1.23456789…45678901e-45). Values that fit in
    `limit` characters are shown whole. The leading digits give the value, the exponent its size, and the
    trailing digits tell nearby points apart at depth."""
    d = Decimal(value)
    whole = str(d).lower()
    if len(whole) <= limit:
        return whole
    sign = '-' if d < 0 else ''
    digits = ''.join(map(str, d.as_tuple().digits)).rstrip('0') or '0'     # (not normalize(): that rounds to the context)
    adj = d.adjusted()                       # power of ten of the leading digit
    if len(digits) > head + tail:
        lead, trail = digits[:head], '…' + digits[-tail:]
    else:
        lead, trail = digits, ''
    if -4 <= adj <= 3:                       # near 1: plain notation, 0.743643887…1234567
        if adj >= 0:
            lead = lead.ljust(adj + 1, '0')
            text = lead[:adj + 1] + ('.' + lead[adj + 1:] if lead[adj + 1:] or trail else '')
        else:
            text = '0.' + '0' * (-adj - 1) + lead
        return sign + text + trail
    text = lead[0] + ('.' + lead[1:] if lead[1:] else '')
    return '{}{}{}e{}{}'.format(sign, text, trail, '-' if adj < 0 else '+', abs(adj))


def selection_to_region(x, y, w, pixx, pixy, pixw, pixwid, pixhgt):
    """Map a rubber-band selection to a new (x, y, w), all exact Decimals.

    (x, y, w) is the current view (lower-left corner and width). pixx/pixy is
    the selection's lower-left corner in pixels from the lower-left of the
    image, pixw its width in pixels.
    """
    x, y, w = Decimal(x), Decimal(y), Decimal(w)
    with localcontext() as ctx:
        ctx.prec = digits_for(w) + 5
        height = w * pixhgt / pixwid
        return (x + pixx * w / pixwid,
                y + pixy * height / pixhgt,
                w * pixw / pixwid)


def reference_orbit(x, y, w, maxiter):
    """Orbit of the view's centre, as an array('d') of re, im, re, im, ..."""
    x, y, w = Decimal(x), Decimal(y), Decimal(w)
    bits = max(128, int(-w.adjusted() * 3.33) + 192)
    out = array('d', [0.0, 0.0])
    with gmpy2.context(precision=bits):
        mw = gmpy2.mpfr(str(w))
        cr = gmpy2.mpfr(str(x)) + mw / 2
        ci = gmpy2.mpfr(str(y)) + mw * HEIGHT / (2 * WIDTH)
        zr = zi = gmpy2.mpfr(0)
        for _ in range(maxiter):
            zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
            fr, fi = float(zr), float(zi)
            out.append(fr)
            out.append(fi)
            if fr * fr + fi * fi > BAILOUT2:
                break
    return out


Reference = namedtuple('Reference', ('orbit', 'step_mant', 'step_exp'))
HEADER = struct.Struct('<Iid')


def pixel_step(w):
    """(mantissa, exponent) with mantissa * 2**exponent == w / WIDTH, mantissa in [0.5, 1)."""
    with gmpy2.context(precision=128):
        exp, mant = gmpy2.frexp(gmpy2.mpfr(str(Decimal(w))) / WIDTH)
    return float(mant), int(exp)


def write_reference(path, x, y, w, maxiter):
    orbit = reference_orbit(x, y, w, maxiter)
    mant, exp = pixel_step(w)
    if sys.byteorder == 'big':
        orbit.byteswap()
    with open(path, 'wb') as fp:
        fp.write(HEADER.pack(len(orbit) // 2, exp, mant))
        fp.write(orbit.tobytes())


def read_reference(path):
    """Inverse of write_reference; returns a Reference with the orbit as a list of complex."""
    with open(path, 'rb') as fp:
        count, exp, mant = HEADER.unpack(fp.read(HEADER.size))
        vals = array('d')
        vals.frombytes(fp.read(16 * count))
    if sys.byteorder == 'big':
        vals.byteswap()
    return Reference([complex(vals[2 * i], vals[2 * i + 1]) for i in range(count)], mant, exp)


if __name__ == '__main__':
    if len(sys.argv) != 6:
        sys.stderr.write('Usage: deepzoom.py x y width maxiter outfile\n')
        sys.exit(1)
    write_reference(sys.argv[5], sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))
