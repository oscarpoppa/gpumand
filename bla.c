#include <stdlib.h>
#include <math.h>
#include <float.h>
#include "bla.h"

static int finite_d(double v) { return fabs(v) <= DBL_MAX; }

/* Builds levels 1.. from level 0 (already filled in): each entry is two entries of the level below, run
 * one after the other. This composition is the same for any map whose one-step approximation is
 * d' = A d + B dc. */
static void merge_levels(Bla *tab, int nlev, int steps, double dcmax, BlaView *view) {
    for (int k = 1; k < nlev; k++) {
        const int count = steps >> k;
        for (int j = 0; j < count; j++) {
            const Bla x = tab[view->off[k - 1] + 2 * j];       /* first half  */
            const Bla y = tab[view->off[k - 1] + 2 * j + 1];   /* second half */
            Bla *e = &tab[view->off[k] + j];
            /* x then y:  d -> A_x d + B_x dc -> A_y (A_x d + B_x dc) + B_y dc */
            e->ax = y.ax * x.ax - y.ay * x.ay;
            e->ay = y.ax * x.ay + y.ay * x.ax;
            e->bx = y.ax * x.bx - y.ay * x.by + y.bx;
            e->by = y.ax * x.by + y.ay * x.bx + y.by;
            /* valid while |d| < r_x and |A_x d + B_x dc| < r_y */
            double room = y.r - hypot(x.bx, x.by) * dcmax;
            if (room < 0.0)
                room = 0.0;
            const double absax = hypot(x.ax, x.ay);
            const double r2 = absax > 0.0 ? room / absax : INFINITY;
            e->r = x.r < r2 ? x.r : r2;
            if (!finite_d(e->ax) || !finite_d(e->ay) || !finite_d(e->bx) || !finite_d(e->by) || !(e->r >= 0.0))
                e->r = 0.0;
        }
    }
}

int bla_build(const Cd *ref, int refn, double eps, double dcmax, BlaView *view, Bla **mem) {
    const int steps = refn - 1;  /* single iterations Z_i -> Z_{i+1}, i = 0 .. steps-1 */
    int nlev = 0;
    size_t total = 0;
    *mem = NULL;
    view->nlev = 0;
    view->tab = NULL;
    if (steps < 2)
        return 0;
    while (nlev < BLA_MAX_LEVELS && (steps >> nlev) >= 1) {
        view->off[nlev] = (int)total;
        total += (size_t)(steps >> nlev);
        nlev++;
    }
    Bla *tab = (Bla*)calloc(total, sizeof(Bla));
    if (!tab)
        return 1;
    for (int i = 0; i < steps; i++) {
        Bla *e = &tab[i];
        e->ax = 2.0 * ref[i].x;
        e->ay = 2.0 * ref[i].y;
        e->bx = 1.0;
        e->by = 0.0;
        e->r = eps * hypot(ref[i].x, ref[i].y);
    }
    merge_levels(tab, nlev, steps, dcmax, view);
    view->nlev = nlev;
    view->tab = tab;
    *mem = tab;
    return 0;
}

/* The same table for z -> z^d + c. One step is d' = (Z+d)^p - Z^p + dc (p the exponent), whose linear part is
 * A = p Z^(p-1), B = 1. The terms dropped are about (p-1)/2 * |d|/|Z| times the linear one, so the
 * validity radius is eps*|Z|/(p-1), which for p = 2 is the radius of bla_build. */
int bla_build_pow(const Cd *ref, int refn, double eps, double dcmax, int p, BlaView *view, Bla **mem) {
    const int steps = refn - 1;
    int nlev = 0;
    size_t total = 0;
    *mem = NULL;
    view->nlev = 0;
    view->tab = NULL;
    if (steps < 2)
        return 0;
    while (nlev < BLA_MAX_LEVELS && (steps >> nlev) >= 1) {
        view->off[nlev] = (int)total;
        total += (size_t)(steps >> nlev);
        nlev++;
    }
    Bla *tab = (Bla*)calloc(total, sizeof(Bla));
    if (!tab)
        return 1;
    for (int i = 0; i < steps; i++) {
        Bla *e = &tab[i];
        double px, py;
        cpow_int(ref[i].x, ref[i].y, p - 1, &px, &py);      /* Z^(p-1) */
        e->ax = p * px;
        e->ay = p * py;
        e->bx = 1.0;
        e->by = 0.0;
        e->r = eps * hypot(ref[i].x, ref[i].y) / (p - 1);
        if (!finite_d(e->ax) || !finite_d(e->ay))
            e->r = 0.0;
    }
    merge_levels(tab, nlev, steps, dcmax, view);
    view->nlev = nlev;
    view->tab = tab;
    *mem = tab;
    return 0;
}
