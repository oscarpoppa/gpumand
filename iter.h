#ifndef __ITERS_H
#define ITERATIONS 2000
/* A pixel escapes when |z|^2 exceeds BAILOUT2 (|z| > 256). The radius is well past 2 so the
 * smooth iteration count (see pert.h) is accurate; reference orbits run to the same radius. */
#define BAILOUT2 65536.0
#define __ITERS_H
#endif
