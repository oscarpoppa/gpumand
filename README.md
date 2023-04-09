# gpumand
CUDA/QT Double-precision-limited Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

![Screenshot from 2023-04-09 18-53-54](https://user-images.githubusercontent.com/69337264/230802349-8dfa632b-c778-4523-9ec9-cd830e7882fb.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
