#!/usr/bin/env python3
"""Regenerates the pictures used in README.md (docs/images/*.png) by running the real renderer.

    make cpu && python3 docs/make_images.py [adjustments]

Name a picture (zoom-journey, palettes, mappings or adjustments) to redraw just that one. Needs mand-cpu and colorize built, gmpy2 (for deep views) and Pillow. The GUI screenshot is made separately
(docs/make_screenshot.py). Rendering the deep tiles takes a few seconds each.
"""
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, localcontext

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'images')
sys.path.insert(0, ROOT)
import deepzoom                                                    # noqa: E402

WIDTH, HEIGHT = deepzoom.WIDTH, deepzoom.HEIGHT
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
SEAHORSE = (Decimal('-0.743643887037158704752191506114774'), Decimal('0.131825904205311970493132056385139'))
SPIRAL = (Decimal(0), Decimal(1))                                    # c = i: structure at every depth


def corner(center, w):
    with localcontext() as ctx:
        ctx.prec = deepzoom.digits_for(w) + 10
        return center[0] - w / 2, center[1] - w * HEIGHT / (2 * WIDTH)


def render(tmp, name, x, y, w, mult, palette='gray', mapping='histogram', extra=()):
    """Draw a view with mand-cpu; returns the path of its counts file (for recoloring)."""
    nu, bmp = os.path.join(tmp, name + '.nu'), os.path.join(tmp, name + '.bmp')
    cmd = [os.path.join(ROOT, 'mand-cpu'), str(x), str(y), str(w), bmp, str(mult)]
    if Decimal(w) < deepzoom.PERTURB_BELOW:
        ref = os.path.join(tmp, name + '.ref')
        deepzoom.write_reference(ref, x, y, w, deepzoom.ITERATIONS * mult)
        cmd.append(ref)
    subprocess.run(cmd + ['--nu-out=' + nu, '--palette=' + palette, '--mapping=' + mapping, *extra], check=True)
    return nu


def recolor(nu, out, *opts):
    subprocess.run([os.path.join(ROOT, 'colorize'), nu, out, *opts], check=True)
    return Image.open(out).convert('RGB')


def caption(img, text, size=30):
    d = ImageDraw.Draw(img, 'RGBA')
    f = ImageFont.truetype(FONT, size)
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle((12, 12, 12 + w + 24, 12 + h + 22), 10, fill=(0, 0, 0, 150))
    d.text((24, 20 - box[1] + 2), text, font=f, fill=(255, 255, 255, 255))
    return img


def sheet(tiles, cols, tile_w, gap=8):
    rows = (len(tiles) + cols - 1) // cols
    tile_h = tile_w * HEIGHT // WIDTH
    img = Image.new('RGB', (cols * tile_w + (cols + 1) * gap, rows * tile_h + (rows + 1) * gap), (45, 45, 45))
    for i, t in enumerate(tiles):
        img.paste(t.resize((tile_w, tile_h), Image.LANCZOS), (gap + (i % cols) * (tile_w + gap), gap + (i // cols) * (tile_h + gap)))
    return img


def adjustments(tmp):
    """4. gamma, brightness, contrast and the interior color, on one view"""
    x, y = corner(SEAHORSE, Decimal('0.02'))
    nu = render(tmp, 'adjust', x, y, Decimal('0.02'), 3)
    settings = [('plain', []), ('gamma 2.5', ['--gamma=2.5']), ('gamma 0.4', ['--gamma=0.4']),
                ('brightness +35', ['--brightness=35']), ('contrast +70', ['--contrast=70']),
                ('interior 1a2a6c', ['--interior=1a2a6c'])]
    tiles = [caption(recolor(nu, os.path.join(tmp, 'a%d.bmp' % i), '--palette=fire', *opts), label, 34)
             for i, (label, opts) in enumerate(settings)]
    sheet(tiles, 3, 480).save(os.path.join(OUT, 'adjustments.png'), optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only not in (None, 'adjustments', 'zoom-journey', 'palettes', 'mappings'):
        sys.exit('unknown picture %r' % only)
    with tempfile.TemporaryDirectory() as tmp:
        if only == 'adjustments':
            return adjustments(tmp)
        # 1. a journey from the whole set to far past double precision
        whole = render(tmp, 'whole', -2.75, Decimal('-1.333333'), 4, 1)
        views = [(whole, 'the whole set  (width 4)')]
        x, y = corner(SEAHORSE, Decimal('0.004'))
        views.append((render(tmp, 'sea', x, y, Decimal('0.004'), 3), 'seahorse valley  (width 4e-3)'))
        x, y = corner(SPIRAL, Decimal('1e-30'))
        views.append((render(tmp, 'sp30', x, y, Decimal('1e-30'), 10), 'a spiral  (width 1e-30)'))
        x, y = corner(SPIRAL, Decimal('1e-300'))
        views.append((render(tmp, 'sp300', x, y, Decimal('1e-300'), 10), 'the same spiral  (width 1e-300)'))
        tiles = [caption(recolor(nu, os.path.join(tmp, 't%d.bmp' % i), '--palette=gray'), label) for i, (nu, label) in enumerate(views)]
        sheet(tiles, 2, 640).save(os.path.join(OUT, 'zoom-journey.png'), optimize=True)

        # 2. one view in every palette
        x, y = corner(SEAHORSE, Decimal('0.02'))
        nu = render(tmp, 'gallery', x, y, Decimal('0.02'), 3)
        names = [l.split()[0] for l in subprocess.run([os.path.join(ROOT, 'colorize'), '--list-palettes'], capture_output=True,
                                                      text=True, check=True).stdout.splitlines()]
        tiles = [caption(recolor(nu, os.path.join(tmp, 'p%d.bmp' % i), '--palette=' + n), n, 34) for i, n in enumerate(names)]
        sheet(tiles, 3, 480).save(os.path.join(OUT, 'palettes.png'), optimize=True)

        # 3. the three ways of mapping counts to colors
        tiles = [caption(recolor(nu, os.path.join(tmp, 'm%d.bmp' % i), '--palette=ocean', '--mapping=' + m), m, 34)
                 for i, m in enumerate(['histogram', 'linear', 'log'])]
        sheet(tiles, 3, 480).save(os.path.join(OUT, 'mappings.png'), optimize=True)
        adjustments(tmp)


if __name__ == '__main__':
    main()
