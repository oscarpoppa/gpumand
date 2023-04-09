# gpumand
CUDA/QT Double-precision-limited Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

![Screenshot from 2023-04-09 16-35-19](https://user-images.githubusercontent.com/69337264/230797611-11480687-11b6-4b05-b1d1-9d16802b8e50.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
