/*
 * The original, slow floatexp loop (every operation renormalizes through frexp/ldexp), kept as the
 * golden reference the fast loop in pert.h is tested against. Test code only.
 */
#ifndef __FX_REFERENCE_H
#define __FX_REFERENCE_H
#include "../pert.h"

/* step = step_mant * 2^step_exp is the pixel spacing; ox, oy are pixel offsets from the center */
HD static inline iter_t pert_pixel_fx_ref(const Cd *ref, int refn, double ox, double oy,
                                   double step_mant, int step_exp, iter_t iterations, uint32_t *steps, double *nu) {
    const Fx dc = fx_norm(ox * step_mant, oy * step_mant, step_exp);
    const int last = refn - 1;
    Fx d = fx_norm(0.0, 0.0, 0);
    int n = 0;
    iter_t cnt = 0;
    uint32_t taken = 0;
    while (cnt < iterations) {
        taken++;
        const double rx = ref[n].x, ry = ref[n].y;
        const Fx t1 = fx_norm(2.0 * (rx * d.x - ry * d.y), 2.0 * (rx * d.y + ry * d.x), d.e);
        const Fx t2 = fx_norm(d.x * d.x - d.y * d.y, 2.0 * d.x * d.y, 2 * d.e);
        const Fx nd = fx_add(fx_add(t1, t2), dc);
        n++;
        cnt++;
        const Fx z = fx_add(fx_norm(ref[n].x, ref[n].y, 0), nd);
        const double zx = ldexp(z.x, z.e), zy = ldexp(z.y, z.e);
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2) {
            if (steps) *steps = taken;
            if (nu) *nu = smooth_nu(cnt - 1, zz);
            return cnt - 1;
        }
        if (fx_less(z, nd) || n >= last)
            d = z, n = 0;
        else
            d = nd;
    }
    if (steps) *steps = taken;
    if (nu) *nu = -1.0;
    return iterations;
}


#endif
