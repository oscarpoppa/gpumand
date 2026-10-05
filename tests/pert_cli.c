/*
 * Native harness around the real per-pixel code in pert.h / bla.c, so the algorithm that
 * runs on the GPU can be tested without one.
 *
 *   pert_cli <mode> <reffile> <iterations> < pixels
 *
 * mode: dbl (double perturbation), bla (double + BLA table), fx (floatexp)
 * stdin: one "px py" pixel per line. stdout: "count steps" per pixel.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static int g_trace;
#define PERT_TRACE(n, len, cnt) do { if (g_trace) fprintf(stderr, "%d %d %d\n", n, len, cnt); } while (0)
#include "../bla.h"
#include "../aspect.h"

typedef struct {
    uint32_t count;
    int32_t step_exp;
    double step_mant;
} RefHeader;

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: pert_cli dbl|bla|fx reffile iterations\n");
        return 2;
    }
    const char *mode = argv[1];
    g_trace = getenv("PERT_TRACE") != NULL;
    const int iterations = atoi(argv[3]);
    FILE *fp = fopen(argv[2], "rb");
    RefHeader h;
    if (!fp || fread(&h, sizeof(h), 1, fp) != 1) {
        fprintf(stderr, "cannot read %s\n", argv[2]);
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
    BlaView bv;
    Bla *mem = NULL;
    memset(&bv, 0, sizeof(bv));
    if ((!strcmp(mode, "bla") || !strcmp(mode, "blatrace")) && bla_build(ref, refn, BLA_EPS, step * hypot(WIDTH / 2, HEIGHT / 2) * 1.01, &bv, &mem)) {
        fprintf(stderr, "out of memory\n");
        return 2;
    }
    if (!strcmp(mode, "blacheck")) {
        /* Property test of the table: inside an entry's stated radius, jumping 2^k iterations with
           d' = A d + B dc must agree with iterating them one by one. Prints "k maxrelerr". */
        const double dcmax = step * hypot(WIDTH / 2, HEIGHT / 2) * 1.01;
        if (bla_build(ref, refn, BLA_EPS, dcmax, &bv, &mem)) {
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
                    const long double rx = ref[(j << k) + i].x, ry = ref[(j << k) + i].y;
                    const long double nx = 2 * (rx * dx - ry * dy) + dx * dx - dy * dy + cx;
                    const long double ny = 2 * (rx * dy + ry * dx) + 2 * dx * dy + cy;
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
    int px, py;
    while (scanf("%d %d", &px, &py) == 2) {
        if (g_trace)
            fprintf(stderr, "pixel %d %d\n", px, py);
        uint32_t steps = 0;
        int cnt;
        if (!strcmp(mode, "fx"))
            cnt = pert_pixel_fx(ref, refn, px - WIDTH / 2, py - HEIGHT / 2, h.step_mant, h.step_exp, iterations, &steps);
        else
            cnt = pert_pixel_dbl(ref, refn, bv, px - WIDTH / 2, py - HEIGHT / 2, step, iterations, &steps);
        printf("%d %u\n", cnt, steps);
    }
    free(mem);
    free(ref);
    return 0;
}
