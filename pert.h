#ifndef __PERT_H
#define __PERT_H
/*
 * Per-pixel perturbation iteration, shared by the CUDA kernels in mand-gpu.cu
 * and by the native test harness (tests/pert_cli.c). Plain C so both can use it.
 *
 * ref[0..refn-1] is the reference orbit Z_n of the image center (Z_0 = 0). A pixel at
 * offset dc from the center follows z_n = Z_n + d_n with
 *     d_{n+1} = 2*Z_n*d_n + d_n^2 + dc.
 * Both loops "rebase" (d = z, n = 0) when the reference runs out, and also when |z| < |d|,
 * the standard safeguard against the reference being a poor match for a pixel (glitches).
 * Note: the tests cover the first case; no test view has yet been found where the |z| < |d|
 * case changes the result, so it is kept as a precaution rather than demonstrated necessary.
 *
 * Return value: the 0-based index of the iteration that escaped (|z|^2 > BAILOUT2), or
 * `iterations` if the pixel never escaped. If nu is not NULL it receives the smooth
 * (continuous) iteration count of an escaped pixel, or -1 for one that never escaped.
 */
#include <math.h>
#include <float.h>
#include <stdint.h>
#include "iter.h"

#ifdef __CUDACC__
#define HD __host__ __device__
#else
#define HD
#endif

/* Continuous iteration count for a pixel that escaped at 0-based iteration idx (so idx+1 updates
 * had been applied) with |z|^2 = zz > BAILOUT2. It is the same on both sides of an iteration-count
 * band edge (z_n ~ z_{n-1}^2), so coloring by it has no bands. Never negative. */
HD static inline double smooth_nu(iter_t idx, double zz) {
    const double nu = (double)idx + 2.0 - log2(0.5 * log2(zz));
    return nu > 0.0 ? nu : 0.0;
}

/* Views whose pixel spacing is below 2^FX_STEP_EXP (~1e-271) leave plain double too little
 * exponent headroom for the deltas, so renderers switch to the floatexp loop. */
#ifndef FX_STEP_EXP /* tests override this to exercise the floatexp path cheaply */
#define FX_STEP_EXP (-900)
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

HD static inline iter_t pert_pixel_dbl(const Cd *ref, int refn, BlaView bv, double ox, double oy,
                                    double step, iter_t iterations, uint32_t *steps, double *nu) {
    const double dcx = ox * step, dcy = oy * step;
    const int last = refn - 1;
    double dx = 0.0, dy = 0.0;
    int n = 0;
    iter_t cnt = 0;
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
        if (zz > BAILOUT2) {
            if (steps) *steps = taken;
            if (nu) *nu = smooth_nu(cnt - 1, zz);
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
    if (nu) *nu = -1.0;
    return iterations;
}

/* ---- "floatexp" perturbation (view widths below ~1e-250) ---------------------
 * Values past the ~1e-308 limit of a double's exponent are held as Fx: (x + iy) * 2^e with
 * max(|x|,|y|) in [0.5, 1), or exactly zero. The fast loop below uses Fx only for setup,
 * rebases and near-zero references; the per-iteration work is plain double arithmetic.
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

/* |a| < |b| for normalized values (compares max-norms) */
HD static inline int fx_less(Fx a, Fx b) {
    if (fx_zero(a)) return !fx_zero(b);
    if (fx_zero(b)) return 0;
    if (a.e != b.e) return a.e < b.e;
    return fmax(fabs(a.x), fabs(a.y)) < fmax(fabs(b.x), fabs(b.y));
}

/* Below this exponent 2^k is too small to hold in a double, so d^2 (which is scaled by 2^k)
 * is dropped: it is then below 2^-900 relative to d, far under double's precision. */
#define FX_SCALE_MIN (-1000)

HD static inline double fx_scale(int k) { return k >= FX_SCALE_MIN ? ldexp(1.0, k) : 0.0; }

/*
 * Floatexp perturbation, fast form. The offset is d = (ex + i*ey) * 2^k, with (ex, ey) an ordinary
 * double pair, so the loop is plain double arithmetic; frexp/ldexp are only needed on the rare
 * events that change k (the offset outgrowing the mantissa, or a rebase).
 *
 * In units of 2^k the recurrence d' = 2*Z*d + d^2 + dc reads
 *     e' = 2*Z*e + 2^k * e^2 + dcs,   with dcs = dc * 2^-k   (kept up to date whenever k changes).
 * step = step_mant * 2^step_exp is the pixel spacing; ox, oy are pixel offsets from the center.
 */
HD static inline iter_t pert_pixel_fx(const Cd *ref, int refn, double ox, double oy,
                                   double step_mant, int step_exp, iter_t iterations, uint32_t *steps, double *nu) {
    const Fx dc = fx_norm(ox * step_mant, oy * step_mant, step_exp);
    const int last = refn - 1;
    double ex = 0.0, ey = 0.0;
    int k = fx_zero(dc) ? 0 : dc.e;
    double dcx = dc.x, dcy = dc.y;          /* dc * 2^-k */
    double sk = fx_scale(k);                /* 2^k, or 0 when it is too small for a double */
    int n = 0;
    iter_t cnt = 0;
    uint32_t taken = 0;
    while (cnt < iterations) {
        taken++;
        const double rx = ref[n].x, ry = ref[n].y;
        const double nex = 2.0 * (rx * ex - ry * ey) + sk * (ex * ex - ey * ey) + dcx;
        const double ney = 2.0 * (rx * ey + ry * ex) + sk * (2.0 * ex * ey) + dcy;
        n++;
        cnt++;
        const double zrx = ref[n].x, zry = ref[n].y;
        const double zx = zrx + nex * sk, zy = zry + ney * sk;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2) {
            if (steps) *steps = taken;
            if (nu) *nu = smooth_nu(cnt - 1, zz);
            return cnt - 1;
        }
        /* rebase when the reference runs out, or when |z| < |d| (max-norms) */
        int rebase = n >= last;
        const double zmax = fmax(fabs(zrx), fabs(zry));
        if (!rebase) {
            if (zmax < 4.909093465297727e-91 /* 2^-300 */) {
                /* the reference is nearly zero here: compare exactly, in floatexp */
                const Fx ndf = fx_norm(nex, ney, k);
                rebase = fx_less(fx_add(fx_norm(zrx, zry, 0), ndf), ndf);
            } else if (k >= FX_SCALE_MIN) {
                rebase = fmax(fabs(zx), fabs(zy)) < fmax(fabs(nex), fabs(ney)) * sk;
            }
            /* else |d| <= 2^-900 while |Z| >= 2^-300, so |z| < |d| is impossible */
        }
        if (rebase) {
            const Fx z = fx_add(fx_norm(zrx, zry, 0), fx_norm(nex, ney, k));
            if (fx_zero(z)) {
                ex = ey = 0.0;
                k = fx_zero(dc) ? 0 : dc.e;
                dcx = dc.x;
                dcy = dc.y;
            } else {
                ex = z.x;
                ey = z.y;
                k = z.e;
                dcx = fx_zero(dc) ? 0.0 : ldexp(dc.x, dc.e - k);
                dcy = fx_zero(dc) ? 0.0 : ldexp(dc.y, dc.e - k);
            }
            sk = fx_scale(k);
            n = 0;
        } else {
            ex = nex;
            ey = ney;
            const double emax = fmax(fabs(ex), fabs(ey));
            if (emax > 1.2676506002282294e+30 /* 2^100 */) {
                /* move the excess into k so e stays near 1 */
                int m;
                frexp(emax, &m);
                ex = ldexp(ex, -m);
                ey = ldexp(ey, -m);
                dcx = ldexp(dcx, -m);
                dcy = ldexp(dcy, -m);
                k += m;
                sk = fx_scale(k);
            }
        }
    }
    if (steps) *steps = taken;
    if (nu) *nu = -1.0;
    return iterations;
}


/* ======================== z^d + c (whole d, POWER_MIN_DEGREE .. POWER_MAX_DEGREE) =======================
 * The same three paths as above for the map z -> z^d + c. With z = Z + d the perturbation recurrence is
 *     d' = (Z + d)^p - Z^p + dc = d * q(Z, d) + dc,      q(Z, y) = sum_{m=0}^{p-1} C(p, m+1) Z^(p-1-m) y^m
 * (written with the exponent p to keep it apart from the offset d). It has no cancelling terms: the
 * Z^p that the plain map would subtract away never appears. q is evaluated by Horner's rule in y.
 */

typedef struct {
    int d;                                  /* the exponent */
    double logd;                            /* ln d, for the smooth iteration count */
    double binom[POWER_MAX_DEGREE + 1];     /* binom[j] = C(d, j) */
} Pow;

/* Host-side setup. Pascal's triangle in exact integers (C(64, 32) < 2^63), then one rounding to double. */
static inline void pow_init(Pow *p, int d) {
    unsigned long long row[POWER_MAX_DEGREE + 1];
    for (int j = 0; j <= POWER_MAX_DEGREE; j++)
        row[j] = 0;
    row[0] = 1;
    for (int i = 1; i <= d; i++)
        for (int j = i; j >= 1; j--)
            row[j] += row[j - 1];
    p->d = d;
    p->logd = log((double)d);
    for (int j = 0; j <= POWER_MAX_DEGREE; j++)
        p->binom[j] = (double)row[j];
}

/* (zx + i zy)^d by repeated squaring, d >= 1 */
HD static inline void cpow_int(double zx, double zy, int d, double *rx, double *ry) {
    double ax = 1.0, ay = 0.0, bx = zx, by = zy;
    while (d > 0) {
        if (d & 1) {
            const double t = ax * bx - ay * by;
            ay = ax * by + ay * bx;
            ax = t;
        }
        d >>= 1;
        if (d) {                            /* (no last squaring: it could overflow for nothing) */
            const double t = bx * bx - by * by;
            by = 2.0 * bx * by;
            bx = t;
        }
    }
    *rx = ax;
    *ry = ay;
}

/* The smooth iteration count for z^d + c: continuous across iteration-count bands because
 * z_{n+1} ~ z_n^d makes log_d(log|z|) grow by exactly 1 per iteration. For d = 2 it differs from
 * smooth_nu() only in the last bits of the logarithm. */
HD static inline double smooth_nu_pow(iter_t idx, double zz, double logd) {
    const double nu = (double)idx + 2.0 - log(0.5 * log2(zz)) / logd;
    return nu > 0.0 ? nu : 0.0;
}

/* q(Z, y), see above; (Z + d)^p - Z^p = d * q(Z, d) */
HD static inline void pow_q(const Pow *p, double zx, double zy, double yx, double yy, double *qx, double *qy) {
    double px[POWER_MAX_DEGREE], py[POWER_MAX_DEGREE];      /* Z^0 .. Z^(p-1) */
    const int d = p->d;
    px[0] = 1.0;
    py[0] = 0.0;
    for (int k = 1; k < d; k++) {
        px[k] = px[k - 1] * zx - py[k - 1] * zy;
        py[k] = px[k - 1] * zy + py[k - 1] * zx;
    }
    double ax = 1.0, ay = 0.0;                              /* m = p-1: C(p, p) Z^0 */
    for (int m = d - 2; m >= 0; m--) {
        const double tx = ax * yx - ay * yy, ty = ax * yy + ay * yx;
        const double c = p->binom[m + 1];
        ax = c * px[d - 1 - m] + tx;
        ay = c * py[d - 1 - m] + ty;
    }
    *qx = ax;
    *qy = ay;
}

/* Double-precision perturbation, as pert_pixel_dbl; the BLA table must come from bla_build_pow. */
HD static inline iter_t pert_pixel_dbl_pow(const Cd *ref, int refn, BlaView bv, const Pow *pw, double ox, double oy,
                                           double step, iter_t iterations, uint32_t *steps, double *nu) {
    const double dcx = ox * step, dcy = oy * step;
    const int last = refn - 1;
    double dx = 0.0, dy = 0.0;
    int n = 0;
    iter_t cnt = 0;
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
            double qx, qy;
            pow_q(pw, ref[n].x, ref[n].y, dx, dy, &qx, &qy);
            ndx = dx * qx - dy * qy + dcx;
            ndy = dx * qy + dy * qx + dcy;
        }
        PERT_TRACE(n, len, cnt);
        n += len;
        cnt += len;
        const double zx = ref[n].x + ndx;
        const double zy = ref[n].y + ndy;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2) {
            if (steps) *steps = taken;
            if (nu) *nu = smooth_nu_pow(cnt - 1, zz, pw->logd);
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
    if (nu) *nu = -1.0;
    return iterations;
}

/* Floatexp perturbation, as pert_pixel_fx. In units of 2^k, with y = e * 2^k,
 *     e' = e * q(Z, y) + dcs,
 * and when 2^k is too small for a double (y = 0) only the linear term p Z^(p-1) e is left. */
HD static inline iter_t pert_pixel_fx_pow(const Cd *ref, int refn, const Pow *pw, double ox, double oy,
                                          double step_mant, int step_exp, iter_t iterations, uint32_t *steps, double *nu) {
    const Fx dc = fx_norm(ox * step_mant, oy * step_mant, step_exp);
    const int last = refn - 1;
    double ex = 0.0, ey = 0.0;
    int k = fx_zero(dc) ? 0 : dc.e;
    double dcx = dc.x, dcy = dc.y;          /* dc * 2^-k */
    double sk = fx_scale(k);                /* 2^k, or 0 when it is too small for a double */
    int n = 0;
    iter_t cnt = 0;
    uint32_t taken = 0;
    while (cnt < iterations) {
        taken++;
        const double rx = ref[n].x, ry = ref[n].y;
        double qx, qy;
        pow_q(pw, rx, ry, ex * sk, ey * sk, &qx, &qy);
        const double nex = ex * qx - ey * qy + dcx;
        const double ney = ex * qy + ey * qx + dcy;
        n++;
        cnt++;
        const double zrx = ref[n].x, zry = ref[n].y;
        const double zx = zrx + nex * sk, zy = zry + ney * sk;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2) {
            if (steps) *steps = taken;
            if (nu) *nu = smooth_nu_pow(cnt - 1, zz, pw->logd);
            return cnt - 1;
        }
        /* rebase when the reference runs out, or when |z| < |d| (max-norms) */
        int rebase = n >= last;
        const double zmax = fmax(fabs(zrx), fabs(zry));
        if (!rebase) {
            if (zmax < 4.909093465297727e-91 /* 2^-300 */) {
                /* the reference is nearly zero here: compare exactly, in floatexp */
                const Fx ndf = fx_norm(nex, ney, k);
                rebase = fx_less(fx_add(fx_norm(zrx, zry, 0), ndf), ndf);
            } else if (k >= FX_SCALE_MIN) {
                rebase = fmax(fabs(zx), fabs(zy)) < fmax(fabs(nex), fabs(ney)) * sk;
            }
            /* else |d| <= 2^-900 while |Z| >= 2^-300, so |z| < |d| is impossible */
        }
        if (rebase) {
            const Fx z = fx_add(fx_norm(zrx, zry, 0), fx_norm(nex, ney, k));
            if (fx_zero(z)) {
                ex = ey = 0.0;
                k = fx_zero(dc) ? 0 : dc.e;
                dcx = dc.x;
                dcy = dc.y;
            } else {
                ex = z.x;
                ey = z.y;
                k = z.e;
                dcx = fx_zero(dc) ? 0.0 : ldexp(dc.x, dc.e - k);
                dcy = fx_zero(dc) ? 0.0 : ldexp(dc.y, dc.e - k);
            }
            sk = fx_scale(k);
            n = 0;
        } else {
            ex = nex;
            ey = ney;
            const double emax = fmax(fabs(ex), fabs(ey));
            if (emax > 1.2676506002282294e+30 /* 2^100 */) {
                /* move the excess into k so e stays near 1 */
                int m;
                frexp(emax, &m);
                ex = ldexp(ex, -m);
                ey = ldexp(ey, -m);
                dcx = ldexp(dcx, -m);
                dcy = ldexp(dcy, -m);
                k += m;
                sk = fx_scale(k);
            }
        }
    }
    if (steps) *steps = taken;
    if (nu) *nu = -1.0;
    return iterations;
}

#endif
