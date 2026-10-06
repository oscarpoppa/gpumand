# gpumand

A Mandelbrot set explorer: drag a box around anything that looks interesting, press Run, and zoom in again, and again, far past the point
where ordinary floating point gives up. It runs on a CUDA GPU, or on plain CPU cores if you don't have one. Hours of fun -- seriously!

![The gpumand window: the image fills the screen, the controls sit in one dark column on the right](docs/images/gui.png)

## What it does

* **Point-and-zoom.** Drag a rectangle on the picture, press **Run** (or Enter), and that region is drawn full size. Every view you make is
  kept as a thumbnail, so **Back** and the thumbnails take you anywhere you have been.
* **Zooms past 1e-1000.** Plain double precision runs out near a view width of 1e-13. Below 1e-9 gpumand switches to *perturbation
  theory*: it works out one exact reference path with arbitrary-precision numbers, and every pixel only tracks its tiny difference from it.
  Coordinates are kept as exact decimals all the way, so repeated zooms never round off.
* **Smooth, pleasing colors.** Nine palettes, three ways of spreading them over the image, and no color banding. Changing a color setting
  repaints the picture instantly without drawing it again.
* **Save and reopen.** Saved pictures are PNG files that remember where they came from, so **Open a saved view** brings one back as a
  live view you can recolor and keep zooming into.
* **Tidy.** It cleans up after itself and asks before throwing anything away.

![From the whole set to a view 1e-300 wide](docs/images/zoom-journey.png)

## Install

You need Python 3 with PyQt5 and `gmpy2` (`pip install PyQt5 gmpy2`), and one of:

* **No GPU:** `gcc` with OpenMP. This builds the renderer `mand-cpu`.

      $ git clone https://github.com/oscarpoppa/gpumand.git
      $ cd gpumand
      $ make cpu            # builds mand-cpu and colorize

* **NVIDIA GPU:** CUDA's `nvcc`. This builds the renderer `mand-gpu`.

      $ make gpu            # builds mand-gpu (CUDA) and colorize; pass ARCH=sm_XX for your card, e.g. make ARCH=sm_86 (default sm_50)

  (Plain `make` does the same as `make gpu`, and `make all cpu` builds both.)

### Required: tell the GUI which renderer to use

The GUI draws pictures by running a separate program (the GUI starts it; you never run it yourself), and **you must set `renderer` in `mand-gui.ini` to the one you built**:

* `renderer=mand-cpu` if you built with `make cpu` (no GPU).
* `renderer=mand-gpu` if you built with `make gpu` (CUDA GPU).

If `renderer` is missing, the GUI assumes `mand-gpu`, so a CPU-only install will fail to render until you set it. The symptom is a
"Render failed" message: either the program cannot be run (it was never built), or `mand-gpu` starts and stops with "no CUDA-capable device". Edit `mand-gui.ini` (or copy it and pass your own with `--ini`). It also says where
the programs are and where saved pictures go by default:

    [paths]
    save_dir=/home/you/Pictures      # where Save starts
    bin_dir=/home/you/gpumand        # the folder with mand-cpu (or mand-gpu), colorize and mand-gui.py
    renderer=mand-cpu                # REQUIRED: mand-cpu (made by `make cpu`) or mand-gpu (made by `make gpu`)

The GUI starts either way, but it can only draw with a renderer that has been built, so set this before your first Run.

Run it:

    $ ./mand-gui.py [-i,--ini=your.ini]

## Using it

| Control | What it does |
|---|---|
| Drag on the picture | Draws a selection box (always the picture's own shape). Its exact coordinates appear on the right. |
| **Run** (or **Enter**) | Draws the selection. If you haven't made a new selection, it redraws the current view in place, which is how you apply a new iteration limit. |
| **Back**, thumbnails | Return to an earlier view. Every control (coordinates, multiplier, palette, mapping, scale, shift) then shows that view's own settings, and a region boxed from it starts from them, not from whatever you used last. The selected thumbnail has a tiny **×** in its corner: it deletes that view and all of its files (after asking), and shows the view before it. Views that were zoomed from the deleted one now hang from its parent, so **Back** always goes to the next real view back. The opening view has no ×. |
| **Save** | Writes the picture on screen as a PNG (see below). |
| **Open a saved view...** | Draws a view from a PNG this program saved. |
| **Reset** | Back to the whole set (it may ask about old files first). |
| Iterations dial / Multiplier | The most iterations a render may use is 2000 times the multiplier, up to 20 million (40 billion iterations). More iterations fill in black areas of deep views but take longer. At the top of the range a view with much of its area inside the set can take hours, because every inside pixel runs to the full limit, and the window stays busy until the render finishes. |
| Colors | Palette, mapping, Scale and Shift. Each change repaints at once. The **Restore** buttons put Scale and Shift back to their starting values. |

The coordinate boxes show long numbers in short form, such as `-0.743643887...6114774` and `1.23456789...8901234e-45`:
the first digits, the last digits and the power of ten. Hover over a box to see every digit.

### Colors

The colors blend smoothly from one to the next, with no visible bands or steps. There are nine palettes:

![The same view in each of the nine palettes](docs/images/palettes.png)

and three **mappings** that decide how counts become colors:

![histogram, linear and log mappings of the same view](docs/images/mappings.png)

* `histogram` (the default) spreads the colors evenly over whatever is in the picture, at any depth.
* `linear` gives each cycle of the palette a fixed number of iterations.
* `log` cycles the colors once per doubling of the iteration count.

**Scale** sets how many times the palette repeats, and what it measures depends on the mapping:

| Mapping | Scale means | Starting value | A bigger Scale gives |
|---|---|---|---|
| `histogram` | times the palette repeats across the picture | 2.5 | more repeats (busier) |
| `linear` | iterations in one repeat of the palette | 50 | fewer repeats (calmer) |
| `log` | repeats of the palette per doubling of the iteration count | 0.6 | more repeats (busier) |

The box shows `default` until you type a number, and `default` uses the built-in starting value for the mapping you have chosen (the table
above), so it changes when you change the mapping. The **Restore** button beside the box puts Scale back to `default`.

**Shift** adds an offset to the position of every color along the palette. Every color moves along it by the same amount, so the colors change
but the pattern does not. It is measured in palette lengths: for example 0.25 moves each color a quarter of the way along the palette, and 0.5
moves it halfway. The **Restore** button beside the box puts Shift back to its starting value.

### Saving, reopening and cleaning up

**Save** writes a PNG that remembers its view: the exact coordinates (every digit), the iteration multiplier, and the color settings, stored
as ordinary PNG text fields that any PNG tool can read (for example `exiftool`). **Open a saved view...** reads them back, checks every field,
and draws the view again as a new entry in the history. It only opens `.png` files that really are PNGs and that this program saved. Redrawing
takes as long as the original render did.

Every render leaves files in `pix/`: the picture, plus a `.nu` file of the raw counts that makes recoloring instant. Changing colors replaces a
view's picture in place and redrawing a view with a new iteration limit replaces its files, so nothing piles up. When you **quit** or **Reset**
with generated files around, it asks what to do:

* **Delete all** removes them.
* **Keep all...** asks for a folder, then keeps each view's picture there as a PNG that remembers its view (inside a new dated folder, so
  nothing is overwritten). The raw `.nu` counts are not kept. Choose `pix/` itself to leave everything where it is.
* **Cancel** stays open, or doesn't reset.

The × on a thumbnail deletes just that view's files (its picture, counts and any leftovers, matched by exact name). Only files the program made, by exact name in `pix/`, are ever deleted. Pictures you saved, kept pictures and the shipped `pix/whole.bmp` are
never touched. On Reset the opening view's own files are spared (it needs them), and if only those are left when you quit they are removed without
asking: they are redrawn at the next start.

## The CPU renderer

`mand-cpu` is the renderer the GUI runs when you have no GPU (`renderer=mand-cpu`). It uses the same per-pixel code as `mand-gpu`, spread
over your CPU cores with OpenMP. It is fast for ordinary and deep views, a couple of seconds even below 1e-300. The slow case is a very high
multiplier on a shallow view, which has nothing to skip. To limit how many cores it uses, set `OMP_NUM_THREADS` before starting the GUI, for
example `OMP_NUM_THREADS=4 ./mand-gui.py`.

## Tests

No GPU needed:

    $ python3 -m unittest discover -s tests

The suite (over a hundred tests) checks the deep-zoom math against exact arbitrary-precision iteration, the renderers against independent
re-implementations, the palettes, the PNG metadata reader, the cleanup rules, and the whole GUI, driven headlessly with both a fake and the
real renderer.

## Files

| | |
|---|---|
| `mand-gui.py` | The window. |
| `mand-gpu.cu`, `mand-cpu.c` | The GPU and CPU renderers. They share `pert.h` (the per-pixel code), `bla.c`, `colorize.c`, `refio.c`. |
| `deepzoom.py` | Reference orbits and exact coordinate math. |
| `colorize-main.c`, `colorize.c` | Palettes, mappings, and the recolor tool. |
| `meta.py` | The view description stored inside saved PNGs. |
| `cleanup.py` | Which files the program may remove, and how. |
| `docs/` | The pictures above. To redraw them: `make cpu`, then run `docs/make_images.py` and `docs/make_screenshot.py` (they need Pillow). |
| `tests/` | The test suite. |
