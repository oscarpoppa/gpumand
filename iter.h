#ifndef __ITERS_H
#define ITERATIONS 2000
/* Iteration limits are ITERATIONS * multiplier, which passes 2^31 for the largest multipliers. */
typedef long long iter_t;
/* A pixel escapes when |z|^2 exceeds BAILOUT2 (|z| > 256). The radius is well past 2 so the
 * smooth iteration count (see pert.h) is accurate; reference orbits run to the same radius. */
#define BAILOUT2 65536.0
/* z^d + c is offered for whole d from POWER_MIN_DEGREE to POWER_MAX_DEGREE: with the bailout above, the
 * largest value an iteration can produce is 256^64 = 2^512, comfortably inside a double. */
#define POWER_MIN_DEGREE 2
#define POWER_MAX_DEGREE 64
#define __ITERS_H
#endif
