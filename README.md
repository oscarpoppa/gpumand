# gpumand
CUDA/QT Double-precision-limited Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.


![Screenshot from 2023-04-14 13-35-07](https://user-images.githubusercontent.com/69337264/232128593-e9c0c536-9531-4595-b062-1b32749685e2.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
