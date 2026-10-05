#include <stdlib.h>
#include <math.h>
#include <float.h>
#include "bla.h"

static int finite_d(double v) { return fabs(v) <= DBL_MAX; }

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
    view->nlev = nlev;
    view->tab = tab;
    *mem = tab;
    return 0;
}
