#ifndef __PERT_H
#define __PERT_H
/*
 * Per-pixel perturbation iteration, shared by the CUDA kernels in mand-main.cu
 * and by the native test harness (tests/pert_cli.c). Plain C so both can use it.
 *
 * ref[0..refn-1] is the reference orbit Z_n of the image centre (Z_0 = 0). A pixel at
 * offset dc from the centre follows z_n = Z_n + d_n with
 *     d_{n+1} = 2*Z_n*d_n + d_n^2 + dc.
 * Both loops "rebase" (d = z, n = 0) when the reference runs out, and also when |z| < |d|,
 * the standard safeguard against the reference being a poor match for a pixel (glitches).
 * Note: the tests cover the first case; no test view has yet been found where the |z| < |d|
 * case changes the result, so it is kept as a precaution rather than demonstrated necessary.
 *
 * Return value: the 0-based index of the iteration that escaped (|z| > 2), or
 * `iterations` if the pixel never escaped.
 */
#include <math.h>
#include <float.h>
#include <stdint.h>

#ifdef __CUDACC__
#define HD __host__ __device__
#else
#define HD
#endif

/* Test hook: called once per loop pass of pert_pixel_dbl with the reference index n, the number
 * of iterations len about to be taken and the count so far. Empty unless a test defines it. */
#ifndef PERT_TRACE
#define PERT_TRACE(n, len, cnt)
#endif

typedef struct { double x, y; } Cd;

/* ---- bilinear approximation (BLA) table -------------------------------------
 * An entry skips 2^k iterations at once: d' = A*d + B*dc, valid while |d| < r.
 * Level k holds (refn-1) >> k entries; entry j covers iterations [j*2^k, (j+1)*2^k).
 */
#define BLA_MAX_LEVELS 32

typedef struct { double ax, ay, bx, by, r; } Bla;

typedef struct {
    int nlev;                 /* 0 disables BLA */
    int off[BLA_MAX_LEVELS];  /* index of each level's first entry in tab */
    const Bla *tab;
} BlaView;

/* ---- double-precision perturbation (view widths down to ~1e-250) ------------ */

HD static inline int pert_pixel_dbl(const Cd *ref, int refn, BlaView bv, double ox, double oy,
                                    double step, int iterations, uint32_t *steps) {
    const double dcx = ox * step, dcy = oy * step;
    const int last = refn - 1;
    double dx = 0.0, dy = 0.0;
    int n = 0, cnt = 0;
    uint32_t taken = 0;
    while (cnt < iterations) {
        double ndx, ndy;
        int len = 1;
        int done = 0;
        taken++;
        if (bv.nlev > 0) {
            const double mag = fmax(fabs(dx), fabs(dy)) * 1.4142135623730951;
            for (int k = bv.nlev - 1; k >= 0; k--) {
                const int span = 1 << k;
                if ((n & (span - 1)) != 0 || n + span > last || cnt + span > iterations)
                    continue;
                const Bla e = bv.tab[bv.off[k] + (n >> k)];
                if (mag < e.r) {
                    ndx = e.ax * dx - e.ay * dy + e.bx * dcx - e.by * dcy;
                    ndy = e.ax * dy + e.ay * dx + e.bx * dcy + e.by * dcx;
                    len = span;
                    done = 1;
                    break;
                }
            }
        }
        if (!done) {
            const double rx = ref[n].x, ry = ref[n].y;
            ndx = 2.0 * (rx * dx - ry * dy) + dx * dx - dy * dy + dcx;
            ndy = 2.0 * (rx * dy + ry * dx) + 2.0 * dx * dy + dcy;
        }
        PERT_TRACE(n, len, cnt);
        n += len;
        cnt += len;
        const double zx = ref[n].x + ndx;
        const double zy = ref[n].y + ndy;
        const double zz = zx * zx + zy * zy;
        if (zz > 4.0) {
            if (steps) *steps = taken;
            return cnt - 1;
        }
        if (zz < ndx * ndx + ndy * ndy || n >= last) {
            dx = zx;
            dy = zy;
            n = 0;
        } else {
            dx = ndx;
            dy = ndy;
        }
    }
    if (steps) *steps = taken;
    return iterations;
}

/* ---- "floatexp" perturbation (view widths below ~1e-250) ---------------------
 * d is held as (x + iy) * 2^e with max(|x|,|y|) in [0.5, 1) (or exactly zero), so it
 * keeps going far past the ~1e-308 limit of a double's exponent.
 */
typedef struct { double x, y; int e; } Fx;

HD static inline Fx fx_norm(double x, double y, int e) {
    Fx r;
    const double m = fmax(fabs(x), fabs(y));
    if (m == 0.0) {
        r.x = r.y = 0.0;
        r.e = 0;
        return r;
    }
    int k;
    frexp(m, &k);
    r.x = ldexp(x, -k);
    r.y = ldexp(y, -k);
    r.e = e + k;
    return r;
}

HD static inline int fx_zero(Fx a) { return a.x == 0.0 && a.y == 0.0; }

HD static inline Fx fx_add(Fx a, Fx b) {
    if (fx_zero(a)) return b;
    if (fx_zero(b)) return a;
    const int e = a.e > b.e ? a.e : b.e;
    return fx_norm(ldexp(a.x, a.e - e) + ldexp(b.x, b.e - e),
                   ldexp(a.y, a.e - e) + ldexp(b.y, b.e - e), e);
}

/* |a| < |b| for normalised values (compares max-norms) */
HD static inline int fx_less(Fx a, Fx b) {
    if (fx_zero(a)) return !fx_zero(b);
    if (fx_zero(b)) return 0;
    if (a.e != b.e) return a.e < b.e;
    return fmax(fabs(a.x), fabs(a.y)) < fmax(fabs(b.x), fabs(b.y));
}

/* step = step_mant * 2^step_exp is the pixel spacing; ox, oy are pixel offsets from the centre */
HD static inline int pert_pixel_fx(const Cd *ref, int refn, double ox, double oy,
                                   double step_mant, int step_exp, int iterations, uint32_t *steps) {
    const Fx dc = fx_norm(ox * step_mant, oy * step_mant, step_exp);
    const int last = refn - 1;
    Fx d = fx_norm(0.0, 0.0, 0);
    int n = 0, cnt = 0;
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
        if (zx * zx + zy * zy > 4.0) {
            if (steps) *steps = taken;
            return cnt - 1;
        }
        if (fx_less(z, nd) || n >= last)
            d = z, n = 0;
        else
            d = nd;
    }
    if (steps) *steps = taken;
    return iterations;
}

#endif
