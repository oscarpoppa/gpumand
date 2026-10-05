"""Which files the GUI generates in pix/, and removing them when they are not wanted any more.

Only names the program itself makes are ever matched, and only inside the directory given; a copy
saved with Save (anywhere else, under any name) and the shipped whole.bmp are never touched.
"""
import os
import re
import time

# mandapp3.bmp (a render), mandapp3.bmp.nu (its raw counts), mandapp3.c12.bmp (a recolored copy)
RENDERS = re.compile(r'^(mandapp\d+\.bmp(\.nu|\.new)?|mandapp\d+\.c\d+\.bmp)$')   # (.cN.bmp: older versions made one per recoloring)
# whole-start.bmp / whole.bmp.nu / whole.c1.bmp: the opening view, which is drawn on demand and is needed
# again straight away after a Reset
OPENING = re.compile(r'^(whole-start\.bmp(\.new)?|whole\.bmp\.nu|whole\.c\d+\.bmp)$')
# reference orbits are removed right after each render; one still here was left by a crash
REFERENCE = re.compile(r'^mandapp\d+\.bmp\.ref$')
STALE_SECONDS = 3600


def _matching(directory, pattern):
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    paths = [os.path.join(directory, n) for n in sorted(names) if pattern.match(n)]
    return [p for p in paths if os.path.isfile(p) and not os.path.islink(p)]


def generated_files(directory, opening=True):
    """Every file in `directory` that the program made and can make again; with opening=False, not the
    opening view's files (what a Reset needs to keep)."""
    return (_matching(directory, RENDERS) + (_matching(directory, OPENING) if opening else []) +
            _matching(directory, REFERENCE))


def total_size(paths):
    size = 0
    for p in paths:
        try:
            size += os.path.getsize(p)
        except OSError:
            pass
    return size


def delete_files(paths):
    """Remove each file; returns how many could not be removed."""
    failed = 0
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        except OSError:
            failed += 1
    return failed


def remove_stale_references(directory, now=None):
    """Delete reference-orbit files old enough that no running render can still be using them."""
    now = time.time() if now is None else now
    old = [p for p in _matching(directory, REFERENCE) if now - os.path.getmtime(p) > STALE_SECONDS]
    delete_files(old)
    return old


def size_text(nbytes):
    for unit, factor in (('GB', 1 << 30), ('MB', 1 << 20), ('KB', 1 << 10)):
        if nbytes >= factor:
            return '{:.1f} {}'.format(nbytes / factor, unit)
    return '{} bytes'.format(nbytes)
