# gpumand
CUDA/QT Double-precision-limited Mandelbrot set browser/explorer for CUDA-enabled workstations. Hours of fun!

Allows successive/recursive, cursor-based zoom-ins of screen selections, and the ability to save images.

![mynubg](![Screenshot from 2023-04-08 20-24-55](https://user-images.githubusercontent.com/69337264/230749575-d99d252f-e2da-4c7a-aa66-0946b92ef653.png)
https://user-images.githubusercontent.com/69337264/230671103-c5b9b33e-a099-4a79-8345-51d0a84b1fa9.png)


Install:

    
    $ git clone https://github.com/oscarpoppa/gpumand.git
    
    $ cd gpumand
    
    $ make

    > Update mand-gui.ini, or supply your own (with --ini option) to reflect your install


Run:
    
    $ mand-gui.py [-i,--ini=your.ini]
