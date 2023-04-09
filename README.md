# gpumand
CUDA/QT Double-precision-limited Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

![Screenshot from 2023-04-08 20-29-21](https://user-images.githubusercontent.com/69337264/230749647-ff4ba9d5-7f5b-4620-93e9-63422c754914.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
