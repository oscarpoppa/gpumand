struct {
    double2 real;
    double2 imag;
} Dcmp;

//squaring
Dcmp curr;
Dcmp const;

//Real
double nurb = curr.real.x * curr.real.x - curr.imag.x * curr.imag.x + const.real.x;
double nurs = 2.0 * curr.real.y * curr.real.x + curr.real.y * curr.real.y - 2.0 * curr.imag.x * curr.imag.y - curr.imag.y * curr.imag.y + const.real.y;

//Imag
double nuib = 2.0 * curr.real.x * curr.imag.x + const.imag.x;
double nuis = 2.0 * (curr.real.x * curr.imag.y + curr.real.y * curr.imag.x + curr.real.y * curr.imag.y) + const.imag.y;

curr.real.x = nurb;
curr.real.y = nurs;
curr.imag.x = nuib;
curr.imag.y = nuis;


//Size
sqrt(curr.real.x * curr.real.x + curr.imag.x * curr.imag.x + 2.0 * curr.real.x * curr.real.y + curr.real.y * curr.real.y + 2.0 * curr.imag.x * curr.imag.y + curr.imag.y * curr.imag.y)
