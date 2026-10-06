"""Function files for the renderers' --func option (see funcspec.h for the format).

    write_power_spec('cubic.func', 3)     # z^3 + c

Reading is strict, like the C reader: a file that is not understood raises ValueError.
"""
from deepzoom import POWER_MIN_DEGREE, POWER_MAX_DEGREE

MAGIC = 'gpumand-func 1'
MAX_LINES = 32


def power_spec_text(degree):
    """The text of a function file for z^degree + c."""
    if isinstance(degree, bool) or not isinstance(degree, int) or not POWER_MIN_DEGREE <= degree <= POWER_MAX_DEGREE:
        raise ValueError('the degree must be a whole number from %d to %d' % (POWER_MIN_DEGREE, POWER_MAX_DEGREE))
    return '%s\nkind power\ndegree %d\n' % (MAGIC, degree)


def write_power_spec(path, degree):
    text = power_spec_text(degree)
    with open(path, 'w') as fp:
        fp.write(text)


def read_spec(path):
    """Returns {'kind': 'power', 'degree': d}."""
    with open(path) as fp:
        lines = fp.read().split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if not lines or len(lines) > MAX_LINES:
        raise ValueError('not a function file')
    if lines[0].rstrip('\r') != MAGIC:
        raise ValueError('not a function file (the first line must be "%s")' % MAGIC)
    found = {}
    for number, line in enumerate(lines[1:], 2):
        line = line.rstrip('\r')
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError('line %d: expected "key value"' % number)
        key, value = parts
        if key in found:
            raise ValueError('line %d: %s appears twice' % (number, key))
        if key == 'kind':
            if value != 'power':
                raise ValueError('line %d: unknown kind (only "power" is supported)' % number)
            found[key] = value
        elif key == 'degree':
            if not value.isdigit() or not POWER_MIN_DEGREE <= int(value) <= POWER_MAX_DEGREE:
                raise ValueError('line %d: degree must be a whole number from %d to %d' % (number, POWER_MIN_DEGREE, POWER_MAX_DEGREE))
            found[key] = int(value)
        else:
            raise ValueError('line %d: unknown key' % number)
    for key in ('kind', 'degree'):
        if key not in found:
            raise ValueError('no %s line' % key)
    return found
