# gpumand
CUDA/QT Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun -- seriously!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

Zoom depth is not limited by double precision: views narrower than 1e-9 are rendered by perturbation theory. `deepzoom.py` computes one arbitrary-precision reference orbit at the centre of the view (needs `gmpy2`), and the GPU iterates each pixel's small offset from it in double. The GUI keeps coordinates as exact `Decimal`s, so repeated zooms never round through a float.

Going deeper:

* **Iteration multiplier** goes up to 1000 (2,000,000 iterations); deep views need far more iterations than shallow ones.
* **BLA skipping** (`bla.c`, `pert.h`): bilinear-approximation tables let each pixel skip runs of up to thousands of iterations at once while its offset from the reference is tiny, e.g. ~15x fewer loop steps at width 1e-200. Reference orbits above ~4M points get no table (memory).
* **Floatexp** (`pert.h`): below a pixel step of ~1e-271 the offsets carry their own exponent, so views past double's ~1e-308 limit render (tested to 1e-1000). This path does no BLA skipping, so it is slower per iteration.

![Screenshot from 2023-04-14 13-35-07](https://user-images.githubusercontent.com/69337264/232128593-e9c0c536-9531-4595-b062-1b32749685e2.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Test (no GPU needed):

    $ python3 -m unittest discover -s tests

Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
