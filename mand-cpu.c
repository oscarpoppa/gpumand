/*
 * CPU renderer: a drop-in for the CUDA `mand` that needs no GPU.
 *
 *   mand-cpu llreal llimag width filename interleave [reference_orbit_file] [options]
 *
 * Same arguments, same output file, same three paths as mand-main.cu (plain double, perturbation
 * with BLA, floatexp), sharing the per-pixel code in pert.h. Rows are spread over threads with
 * OpenMP; set OMP_NUM_THREADS to control how many, and MAND_VERBOSE=1 to have it say which path
 * it took on stderr. Pixels are computed as smooth iteration counts and coloured on the host
 * (colorize.h); options: --palette --mapping --scale --shift --interior, and --nu-out=FILE to also
 * save the raw counts so `colorize` can recolour the image without rendering again.
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

/* Plain double iteration, as MandKern in mand-main.cu. Good down to a view width of ~1e-9.
 * Returns the smooth iteration count, or -1 if the point never escapes. */
static double plain_pixel(double cx, double cy, int iterations) {
    double zx = 0.0, zy = 0.0;
    for (int cnt = 0; cnt < iterations; cnt++) {
        const double nux = zx * zx - zy * zy + cx;
        zy = 2.0 * zx * zy + cy;
        zx = nux;
        const double zz = zx * zx + zy * zy;
        if (zz > BAILOUT2)
            return smooth_nu(cnt, zz);
    }
    return -1.0;
}

int main(int argc, char **argv) {
    RunStart *init = get_coords(argc, argv);
    const int iterations = ITERATIONS * (int)init->interleave;
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
                    pert_pixel_fx(ref, refn, x - WIDTH / 2, y - HEIGHT / 2, rh.step_mant, rh.step_exp, iterations, NULL,
                                  &nu[(size_t)WIDTH * y + x]);
        } else {
            const double step = ldexp(rh.step_mant, rh.step_exp);
            BlaView bv;
            bv.nlev = 0;
            bv.tab = NULL;
            if (refn <= BLA_MAX_REF && bla_build(ref, refn, BLA_EPS, step * hypot(WIDTH / 2.0, HEIGHT / 2.0) * 1.01, &bv, &blamem)) {
                fprintf(stderr, "Out of memory building the BLA table\n");
                return 1;
            }
            say(bv.nlev > 0 ? "perturbation+BLA" : "perturbation");
            #pragma omp parallel for schedule(dynamic, 4)
            for (int y = 0; y < HEIGHT; y++)
                for (int x = 0; x < WIDTH; x++)
                    pert_pixel_dbl(ref, refn, bv, x - WIDTH / 2, y - HEIGHT / 2, step, iterations, NULL,
                                   &nu[(size_t)WIDTH * y + x]);
        }
    } else {
        say("plain");
        const double x0 = init->lleft.real, y0 = init->lleft.imag, edge = init->lleft.length;
        #pragma omp parallel for schedule(dynamic, 4)
        for (int y = 0; y < HEIGHT; y++)
            for (int x = 0; x < WIDTH; x++)
                nu[(size_t)WIDTH * y + x] = plain_pixel(x0 + edge * (double)x / WIDTH, y0 + edge * (double)y / WIDTH, iterations);
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
