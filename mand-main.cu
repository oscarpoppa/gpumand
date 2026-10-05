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

#define BLOCK_SIZE 16

#define CUDA_CHECK(call) do { \
    cudaError_t err_ = (call); \
    if (err_ != cudaSuccess) { \
        fprintf(stderr, "CUDA error: %s (%s:%d)\n", cudaGetErrorString(err_), __FILE__, __LINE__); \
        exit(1); \
    } \
} while (0)

typedef double2 cudaDoubleComplex;

typedef struct {
    cudaDoubleComplex llft;
    double ledg;
    int ilev;
} Init;

// The kernels write one smooth iteration count per pixel (-1 where the point never escapes);
// coloring happens afterwards on the host (colorize.h), the same code the CPU renderer uses.

// Plain double-precision iteration. Good down to a view width of ~1e-9.
__global__ void MandKern(double* dev_nu_ptr, const Init* dev_init_ptr) {
    int cnt = 0;
    const int iterations = ITERATIONS * dev_init_ptr->ilev;
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    // pixels are square: both axes advance by ledg/WIDTH (the view height is ledg*HEIGHT/WIDTH)
    const double cx = dev_init_ptr->llft.x + dev_init_ptr->ledg * (double)pix_x / WIDTH;
    const double cy = dev_init_ptr->llft.y + dev_init_ptr->ledg * (double)pix_y / WIDTH;
    double zx = 0.0, zy = 0.0, zz = 0.0;
    for (; cnt<iterations; cnt++) {
        const double nux = zx * zx - zy * zy + cx;
        zy = 2.0 * zx * zy + cy;
        zx = nux;
        zz = zx * zx + zy * zy;
        if (zz > BAILOUT2)
            break;
    }
    dev_nu_ptr[WIDTH*pix_y+pix_x] = cnt == iterations ? -1.0 : smooth_nu(cnt, zz);
}

// Perturbation off an arbitrary-precision reference orbit (see pert.h), with BLA skipping
// when bv.nlev > 0. Pixel spacing `step` is a double, so views down to ~1e-250.
__global__ void MandKernPert(const Cd* ref, const int refn, const BlaView bv, const double step, double* dev_nu_ptr, const int iterations) {
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    pert_pixel_dbl(ref, refn, bv, pix_x - WIDTH / 2, pix_y - HEIGHT / 2, step, iterations, NULL, &dev_nu_ptr[WIDTH*pix_y+pix_x]);
}

// Same, for views too deep for a double's exponent: the delta carries its own exponent.
__global__ void MandKernPertFx(const Cd* ref, const int refn, const double step_mant, const int step_exp, double* dev_nu_ptr, const int iterations) {
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    pert_pixel_fx(ref, refn, pix_x - WIDTH / 2, pix_y - HEIGHT / 2, step_mant, step_exp, iterations, NULL, &dev_nu_ptr[WIDTH*pix_y+pix_x]);
}

int main(int argc, char **argv) {
    Init istruct, *dev_init_ptr;
    double *dev_nu_ptr;
    Cd *refhost = NULL, *dev_ref_ptr = NULL;
    Bla *blahost = NULL, *dev_bla_ptr = NULL;
    RefHeader rh;
    RunStart *init = get_coords(argc, argv);
    istruct.llft.x = init->lleft.real;
    istruct.llft.y = init->lleft.imag;
    istruct.ledg = init->lleft.length;
    istruct.ilev = init->interleave;
    const int iterations = ITERATIONS * (int)init->interleave;
    if (init->refname[0])
        refhost = load_ref(init->refname, &rh);
    CUDA_CHECK(cudaSetDevice(0));
    CUDA_CHECK(cudaMalloc(&dev_init_ptr, sizeof(Init)));
    CUDA_CHECK(cudaMalloc(&dev_nu_ptr, (size_t)WIDTH*HEIGHT*sizeof(double)));
    CUDA_CHECK(cudaMemcpy(dev_init_ptr, &istruct, sizeof(Init), cudaMemcpyHostToDevice));
    dim3 dimBlock(BLOCK_SIZE, BLOCK_SIZE);
    dim3 dimGrid(WIDTH/BLOCK_SIZE, HEIGHT/BLOCK_SIZE);
    if (refhost) {
        const int refn = (int)rh.count;
        CUDA_CHECK(cudaMalloc(&dev_ref_ptr, rh.count*sizeof(Cd)));
        CUDA_CHECK(cudaMemcpy(dev_ref_ptr, refhost, rh.count*sizeof(Cd), cudaMemcpyHostToDevice));
        if (rh.step_exp < FX_STEP_EXP) {
            MandKernPertFx<<<dimGrid, dimBlock>>>(dev_ref_ptr, refn, rh.step_mant, rh.step_exp, dev_nu_ptr, iterations);
        } else {
            const double step = ldexp(rh.step_mant, rh.step_exp);
            BlaView bv;
            bv.nlev = 0;
            bv.tab = NULL;
            if (refn <= BLA_MAX_REF) {
                if (bla_build(refhost, refn, BLA_EPS, step * hypot(WIDTH / 2.0, HEIGHT / 2.0) * 1.01, &bv, &blahost)) {
                    fprintf(stderr, "Out of memory building the BLA table\n");
                    exit(1);
                }
                if (bv.nlev > 0) {
                    size_t total = (size_t)bv.off[bv.nlev - 1] + (size_t)((refn - 1) >> (bv.nlev - 1));
                    CUDA_CHECK(cudaMalloc(&dev_bla_ptr, total*sizeof(Bla)));
                    CUDA_CHECK(cudaMemcpy(dev_bla_ptr, blahost, total*sizeof(Bla), cudaMemcpyHostToDevice));
                    bv.tab = dev_bla_ptr;
                }
            }
            MandKernPert<<<dimGrid, dimBlock>>>(dev_ref_ptr, refn, bv, step, dev_nu_ptr, iterations);
        }
    } else {
        MandKern<<<dimGrid, dimBlock>>>(dev_nu_ptr, dev_init_ptr);
    }
    CUDA_CHECK(cudaGetLastError());
    double *nu = (double*)malloc((size_t)HEIGHT*WIDTH*sizeof(double));
    uint32_t *pixarr = (uint32_t*)malloc((size_t)HEIGHT*WIDTH*sizeof(uint32_t));
    if (!nu || !pixarr) {
        perror("malloc");
        exit(1);
    }
    CUDA_CHECK(cudaMemcpy(nu, dev_nu_ptr, (size_t)HEIGHT*WIDTH*sizeof(double), cudaMemcpyDeviceToHost));
    int failed = 0;
    if (init->nuout[0] && nu_write(init->nuout, nu, WIDTH, HEIGHT))
        failed = 1;
    if (colorize_image(nu, WIDTH, HEIGHT, &init->color, pixarr)) {
        fprintf(stderr, "unknown palette '%s'\n", init->color.palette);
        failed = 1;
    } else if (gen_bmp(init->filename, pixarr, WIDTH, HEIGHT)) {
        failed = 1;
    }
    cudaFree(dev_bla_ptr);
    cudaFree(dev_ref_ptr);
    cudaFree(dev_init_ptr);
    cudaFree(dev_nu_ptr);
    free(blahost);
    free(refhost);
    free(pixarr);
    free(nu);
    free(init);
    return failed ? 1 : 0;
}
