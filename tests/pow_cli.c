/*
 * Native harness around the z^d + c code in pert.h / bla.c (the code the GPU build shares), so it can be
 * tested here against exact arithmetic done in Python.
 *
 *   pow_cli delta < "p zx zy dx dy" lines
 *       prints (Z+d)^p - Z^p as computed by d * pow_q(), two numbers per line in hex-float form (%a).
 *   pow_cli blacheck p reffile
 *       the property test of bla_build_pow: inside an entry's stated radius, jumping 2^k iterations with
 *       d' = A d + B dc must agree with iterating them one by one (in long double). Prints "k used maxrelerr".
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../bla.h"
#include "../aspect.h"

typedef struct {
    uint32_t count;
    int32_t step_exp;
    double step_mant;
} RefHeader;

/* the same Horner evaluation as pow_q, in long double, for the step-by-step side of blacheck */
static void step_ld(const Pow *pw, long double zx, long double zy, long double dx, long double dy,
                    long double cx, long double cy, long double *nx, long double *ny) {
    long double px[POWER_MAX_DEGREE], py[POWER_MAX_DEGREE];
    const int d = pw->d;
    px[0] = 1;
    py[0] = 0;
    for (int k = 1; k < d; k++) {
        px[k] = px[k - 1] * zx - py[k - 1] * zy;
        py[k] = px[k - 1] * zy + py[k - 1] * zx;
    }
    long double ax = 1, ay = 0;
    for (int m = d - 2; m >= 0; m--) {
        const long double tx = ax * dx - ay * dy, ty = ax * dy + ay * dx;
        ax = pw->binom[m + 1] * px[d - 1 - m] + tx;
        ay = pw->binom[m + 1] * py[d - 1 - m] + ty;
    }
    *nx = dx * ax - dy * ay + cx;
    *ny = dx * ay + dy * ax + cy;
}

int main(int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "delta")) {
        int p;
        double zx, zy, dx, dy;
        while (scanf("%d %la %la %la %la", &p, &zx, &zy, &dx, &dy) == 5) {
            Pow pw;
            double qx, qy;
            pow_init(&pw, p);
            pow_q(&pw, zx, zy, dx, dy, &qx, &qy);
            printf("%a %a\n", dx * qx - dy * qy, dx * qy + dy * qx);
        }
        return 0;
    }
    if (argc != 4 || strcmp(argv[1], "blacheck")) {
        fprintf(stderr, "usage: pow_cli delta | pow_cli blacheck p reffile\n");
        return 2;
    }
    const int p = atoi(argv[2]);
    FILE *fp = fopen(argv[3], "rb");
    RefHeader h;
    if (p < POWER_MIN_DEGREE || p > POWER_MAX_DEGREE || !fp || fread(&h, sizeof(h), 1, fp) != 1) {
        fprintf(stderr, "bad arguments or unreadable %s\n", argv[3]);
        return 2;
    }
    Cd *ref = (Cd*)malloc(h.count * sizeof(Cd));
    if (!ref || fread(ref, sizeof(Cd), h.count, fp) != h.count) {
        fprintf(stderr, "short reference file\n");
        return 2;
    }
    fclose(fp);
    const int refn = (int)h.count;
    const double step = ldexp(h.step_mant, h.step_exp);
    const double dcmax = step * hypot(WIDTH / 2, HEIGHT / 2) * 1.01;
    BlaView bv;
    Bla *mem = NULL;
    Pow pw;
    memset(&bv, 0, sizeof(bv));
    pow_init(&pw, p);
    if (bla_build_pow(ref, refn, BLA_EPS, dcmax, p, &bv, &mem)) {
        fprintf(stderr, "out of memory\n");
        return 2;
    }
    srand(12345);
    for (int k = 0; k < bv.nlev; k++) {
        const int count = (refn - 1) >> k;
        double worst = 0.0;
        int used = 0;
        for (int t = 0; t < 400; t++) {
            const int j = rand() % count;
            const Bla e = bv.tab[bv.off[k] + j];
            if (!(e.r > 0.0))
                continue;
            const double u = 0.5 + 0.49 * (rand() / (double)RAND_MAX);
            const double v = rand() / (double)RAND_MAX;
            const double th = 6.283185307179586 * (rand() / (double)RAND_MAX);
            const double ph = 6.283185307179586 * (rand() / (double)RAND_MAX);
            long double dx = e.r * u / 1.4142135623730951 * cosl(th), dy = e.r * u / 1.4142135623730951 * sinl(th);
            const long double cx = dcmax * v * cosl(ph), cy = dcmax * v * sinl(ph);
            const long double d0x = dx, d0y = dy;
            for (int i = 0; i < (1 << k); i++) {
                long double nx, ny;
                step_ld(&pw, ref[(j << k) + i].x, ref[(j << k) + i].y, dx, dy, cx, cy, &nx, &ny);
                dx = nx;
                dy = ny;
            }
            const long double bx = e.ax * d0x - e.ay * d0y + e.bx * cx - e.by * cy;
            const long double by = e.ax * d0y + e.ay * d0x + e.bx * cy + e.by * cx;
            const long double scale = hypotl(e.ax * d0x - e.ay * d0y, e.ax * d0y + e.ay * d0x) + hypotl(e.bx * cx - e.by * cy, e.bx * cy + e.by * cx);
            if (scale > 0.0L) {
                const double err = (double)(hypotl(dx - bx, dy - by) / scale);
                if (err > worst)
                    worst = err;
                used++;
            }
        }
        printf("%d %d %.6e\n", k, used, worst);
    }
    free(mem);
    free(ref);
    return 0;
}
