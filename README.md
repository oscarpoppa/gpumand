# gpumand
CUDA/QT Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun -- seriously!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

Zoom depth is not limited by double precision: views narrower than 1e-9 are rendered by perturbation theory. `deepzoom.py` computes one arbitrary-precision reference orbit at the centre of the view (needs `gmpy2`), and the GPU iterates each pixel's small offset from it in double. The GUI keeps coordinates as exact `Decimal`s, so repeated zooms never round through a float.

Going deeper:

* **Iteration multiplier** goes up to 1000 (2,000,000 iterations); deep views need far more iterations than shallow ones.
* **BLA skipping** (`bla.c`, `pert.h`): bilinear-approximation tables let each pixel skip runs of up to thousands of iterations at once while its offset from the reference is tiny, e.g. ~15x fewer loop steps at width 1e-200. Reference orbits above ~4M points get no table (memory).
* **Floatexp** (`pert.h`): below a pixel step of ~1e-271 the offsets carry their own exponent, so views past double's ~1e-308 limit render (tested to 1e-1000). The offset is kept as an ordinary double plus a separate exponent, so it costs about the same per iteration as the double path (a 1e-400 view takes ~2.5 s on 8 CPU cores); it does no BLA skipping.

![Screenshot from 2023-04-14 13-35-07](https://user-images.githubusercontent.com/69337264/232128593-e9c0c536-9531-4595-b062-1b32749685e2.png)


No GPU? `make mand-cpu colorize` builds a CPU-only renderer with the same arguments and output (needs only `gcc` with OpenMP). Point the GUI at it with `renderer=mand-cpu` in the ini file. It is fast for ordinary and deep views (a couple of seconds even below 1e-300); the slow case is very high iteration multipliers on shallow views, which have no skipping. `OMP_NUM_THREADS` sets the thread count and `MAND_VERBOSE=1` reports which render path was taken.

Iterations: the Iterations dial in the GUI sets how many iterations a render may use (the multiplier times 2000, shown under the dial, up to
2,000,000); the multiplier box beside it picks an exact value. A higher limit fills in black areas of deep views, at the cost of time.

Colours: images are coloured from a *smooth* iteration count (no visible bands) through one of several palettes
(`twilight` is the default; `fire`, `ocean`, `aurora`, `ice`, `sunset`, `gray`, `rainbow`, and the original `classic`). The Colours box in the GUI
changes palette, mapping, scale and shift on the image you are looking at instantly, without rendering again. Mappings: `histogram` (default,
spreads the colours evenly whatever the depth), `linear` (a fixed number of iterations per colour cycle) and `log`. On the command line,
`mand` and `mand-cpu` accept `--palette=NAME --mapping=histogram|linear|log --scale=N --shift=N --interior=RRGGBB` (anywhere on the line), and
`--nu-out=FILE` to save the raw smooth counts; `colorize FILE.nu OUT.bmp [options]` recolours saved counts without rendering, and
`colorize --list-palettes` lists the palettes.

Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make            # builds mand (CUDA) and colorize; pass ARCH=sm_XX for your GPU, e.g. make ARCH=sm_86 (default sm_50)

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Test (no GPU needed):

    $ python3 -m unittest discover -s tests

Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
