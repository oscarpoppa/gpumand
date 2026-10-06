/*
 * CPU renderer: a drop-in for the CUDA `mand-gpu` that needs no GPU.
 *
 *   mand-cpu llreal llimag width filename interleave [reference_orbit_file] [options]
 *
 * With --func=FILE (see funcspec.h) it draws z^d + c for a whole d instead of z^2 + c; with the
 * file absent every code path is the original z^2 one.
 *
 * Same arguments, same output file, same three paths as mand-gpu.cu (plain double, perturbation
 * with BLA, floatexp), sharing the per-pixel code in pert.h. Rows are spread over threads with
 * OpenMP; set OMP_NUM_THREADS to control how many, and MAND_VERBOSE=1 to have it say which path
 * it took on stderr. Pixels are computed as smooth iteration counts and colored on the host
 * (colorize.h); options: --palette --mapping --scale --shift --gamma --brightness --contrast --interior, and --nu-out=FILE to also
 * save the raw counts so `colorize` can recolor the image without rendering again.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include "mtypes.h"
#include "colorize.h"
#include "bmp.h"
#include "iter.h"
#include "aspect.h"
#include "get-coords.h"
#include "pert.h"
#include "bla.h"
#include "refio.h"

static void say(const char *path) {
    if (getenv("MAND_VERBOSE"))
        fprintf(stderr, "mand-cpu: %s path\n", path);
}

/* Plain double iteration, as MandKern in mand-gpu.cu. Good down to a view width of ~1e-9.
 * Returns the smooth iteration count, or -1 if the point never escapes. */
static double plain_pixel(double cx, double cy, iter_t iterations) {
    double zx = 0.0, zy = 0.0;
    for (iter_t cnt = 0; cnt < iterations; cnt++) {
        const double nux = zx * zx - zy * zy + cx;
        zy = 2.0 * zx * zy + cy;
        zx = nux;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2)
            return smooth_nu(cnt, zz);
    }
    return -1.0;
}

/* The same for z^d + c: the hand-written z^2 loop above is left exactly as it was. */
static double plain_pixel_pow(double cx, double cy, iter_t iterations, const Pow *pw) {
    double zx = 0.0, zy = 0.0;
    for (iter_t cnt = 0; cnt < iterations; cnt++) {
        double px, py;
        cpow_int(zx, zy, pw->d, &px, &py);
        zx = px + cx;
        zy = py + cy;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2)
            return smooth_nu_pow(cnt, zz, pw->logd);
    }
    return -1.0;
}

int main(int argc, char **argv) {
    RunStart *init = get_coords(argc, argv);
    const int power = init->func.kind == FUNC_POWER;
    Pow pw;
    if (power)
        pow_init(&pw, init->func.degree);
    const iter_t iterations = (iter_t)ITERATIONS * init->interleave;
    double *nu = (double*)malloc((size_t)HEIGHT * WIDTH * sizeof(double));
    uint32_t *pixarr = (uint32_t*)malloc((size_t)HEIGHT * WIDTH * sizeof(uint32_t));
    if (!nu || !pixarr) {
        perror("malloc");
        return 1;
    }
    Cd *ref = NULL;
    Bla *blamem = NULL;
    RefHeader rh;

    if (init->refname[0]) {
        ref = load_ref(init->refname, &rh);
        const int refn = (int)rh.count;
        if (rh.step_exp < FX_STEP_EXP) {
            say("floatexp");
            #pragma omp parallel for schedule(dynamic, 4)
            for (int y = 0; y < HEIGHT; y++)
                for (int x = 0; x < WIDTH; x++)
                    if (power)
                        pert_pixel_fx_pow(ref, refn, &pw, x - WIDTH / 2, y - HEIGHT / 2, rh.step_mant, rh.step_exp, iterations, NULL,
                                          &nu[(size_t)WIDTH * y + x]);
                    else
                        pert_pixel_fx(ref, refn, x - WIDTH / 2, y - HEIGHT / 2, rh.step_mant, rh.step_exp, iterations, NULL,
                                      &nu[(size_t)WIDTH * y + x]);
        } else {
            const double step = ldexp(rh.step_mant, rh.step_exp);
            BlaView bv;
            bv.nlev = 0;
            bv.tab = NULL;
            const double dcmax = step * hypot(WIDTH / 2.0, HEIGHT / 2.0) * 1.01;
            if (refn <= BLA_MAX_REF && (power ? bla_build_pow(ref, refn, BLA_EPS, dcmax, pw.d, &bv, &blamem)
                                              : bla_build(ref, refn, BLA_EPS, dcmax, &bv, &blamem))) {
                fprintf(stderr, "Out of memory building the BLA table\n");
                return 1;
            }
            say(bv.nlev > 0 ? "perturbation+BLA" : "perturbation");
            #pragma omp parallel for schedule(dynamic, 4)
            for (int y = 0; y < HEIGHT; y++)
                for (int x = 0; x < WIDTH; x++)
                    if (power)
                        pert_pixel_dbl_pow(ref, refn, bv, &pw, x - WIDTH / 2, y - HEIGHT / 2, step, iterations, NULL,
                                           &nu[(size_t)WIDTH * y + x]);
                    else
                        pert_pixel_dbl(ref, refn, bv, x - WIDTH / 2, y - HEIGHT / 2, step, iterations, NULL,
                                       &nu[(size_t)WIDTH * y + x]);
        }
    } else {
        say("plain");
        const double x0 = init->lleft.real, y0 = init->lleft.imag, edge = init->lleft.length;
        #pragma omp parallel for schedule(dynamic, 4)
        for (int y = 0; y < HEIGHT; y++)
            for (int x = 0; x < WIDTH; x++)
                nu[(size_t)WIDTH * y + x] = power ? plain_pixel_pow(x0 + edge * (double)x / WIDTH, y0 + edge * (double)y / WIDTH, iterations, &pw)
                                                  : plain_pixel(x0 + edge * (double)x / WIDTH, y0 + edge * (double)y / WIDTH, iterations);
    }

    int failed = 0;
    if (init->nuout[0] && nu_write(init->nuout, nu, WIDTH, HEIGHT))
        failed = 1;
    if (colorize_image(nu, WIDTH, HEIGHT, &init->color, pixarr)) {
        fprintf(stderr, "unknown palette '%s'\n", init->color.palette);
        failed = 1;
    } else if (gen_bmp(init->filename, pixarr, WIDTH, HEIGHT)) {
        failed = 1;
    }
    free(blamem);
    free(ref);
    free(pixarr);
    free(nu);
    free(init);
    return failed ? 1 : 0;
}
