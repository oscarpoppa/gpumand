#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include "mtypes.h"
#include "colors.h"
#include "bmp.h"
#include "iter.h"
#include "aspect.h"
#include "get-coords.h"
#include "pert.h"
#include "bla.h"

#define BLOCK_SIZE 16
#define MAX_REF_POINTS (1u << 24)
// Pixel spacings below 2^FX_STEP_EXP (~1e-271) leave plain double too little exponent
// headroom for the deltas, so those views use the floatexp kernel.
#define FX_STEP_EXP (-900)

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

// Header of a reference orbit file written by deepzoom.py.
typedef struct {
    uint32_t count;
    int32_t step_exp;
    double step_mant;
} RefHeader;

// Plain double-precision iteration. Good down to a view width of ~1e-9.
__global__ void MandKern(const uint32_t* dev_col_ptr, uint32_t* dev_pix_ptr, const Init* dev_init_ptr, const uint32_t palsz) {
    int cnt = 0;
    const int iterations = ITERATIONS * dev_init_ptr->ilev;
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    // pixels are square: both axes advance by ledg/WIDTH (the view height is ledg*HEIGHT/WIDTH)
    const double cx = dev_init_ptr->llft.x + dev_init_ptr->ledg * (double)pix_x / WIDTH;
    const double cy = dev_init_ptr->llft.y + dev_init_ptr->ledg * (double)pix_y / WIDTH;
    double zx = 0.0, zy = 0.0;
    for (; cnt<iterations; cnt++) {
        const double nux = zx * zx - zy * zy + cx;
        zy = 2.0 * zx * zy + cy;
        zx = nux;
        if (zx * zx + zy * zy > 4.0)
            break;
    }
    if (cnt == iterations)
        dev_pix_ptr[WIDTH*pix_y+pix_x] = 0x00000000;
    else
        dev_pix_ptr[WIDTH*pix_y+pix_x] = dev_col_ptr[(uint64_t)cnt*palsz/iterations];
}

// Perturbation off an arbitrary-precision reference orbit (see pert.h), with BLA skipping
// when bv.nlev > 0. Pixel spacing `step` is a double, so views down to ~1e-250.
__global__ void MandKernPert(const Cd* ref, const int refn, const BlaView bv, const double step, const uint32_t* dev_col_ptr, uint32_t* dev_pix_ptr, const int iterations, const uint32_t palsz) {
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    const int cnt = pert_pixel_dbl(ref, refn, bv, pix_x - WIDTH / 2, pix_y - HEIGHT / 2, step, iterations, NULL);
    if (cnt == iterations)
        dev_pix_ptr[WIDTH*pix_y+pix_x] = 0x00000000;
    else
        dev_pix_ptr[WIDTH*pix_y+pix_x] = dev_col_ptr[(uint64_t)cnt*palsz/iterations];
}

// Same, for views too deep for a double's exponent: the delta carries its own exponent.
__global__ void MandKernPertFx(const Cd* ref, const int refn, const double step_mant, const int step_exp, const uint32_t* dev_col_ptr, uint32_t* dev_pix_ptr, const int iterations, const uint32_t palsz) {
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    const int cnt = pert_pixel_fx(ref, refn, pix_x - WIDTH / 2, pix_y - HEIGHT / 2, step_mant, step_exp, iterations, NULL);
    if (cnt == iterations)
        dev_pix_ptr[WIDTH*pix_y+pix_x] = 0x00000000;
    else
        dev_pix_ptr[WIDTH*pix_y+pix_x] = dev_col_ptr[(uint64_t)cnt*palsz/iterations];
}

// Reads a reference orbit written by deepzoom.py: a RefHeader, then count (re, im) doubles.
static Cd *load_ref(const char *path, RefHeader *h) {
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        perror(path);
        exit(1);
    }
    if (fread(h, sizeof(*h), 1, fp) != 1 || h->count < 2 || h->count > MAX_REF_POINTS || h->step_mant <= 0.0) {
        fprintf(stderr, "Bad reference orbit header: %s\n", path);
        exit(1);
    }
    Cd *buf = (Cd*)malloc(h->count * sizeof(Cd));
    if (!buf || fread(buf, sizeof(Cd), h->count, fp) != h->count) {
        fprintf(stderr, "Bad reference orbit data: %s\n", path);
        exit(1);
    }
    fclose(fp);
    return buf;
}

int main(int argc, char **argv) {
    Init istruct, *dev_init_ptr;
    uint32_t *dev_pix_ptr, *dev_col_ptr;
    Cd *refhost = NULL, *dev_ref_ptr = NULL;
    Bla *blahost = NULL, *dev_bla_ptr = NULL;
    RefHeader rh;
    RunStart *init = get_coords(argc, argv);
    ColorInfo *colors = make_pall();
    istruct.llft.x = init->lleft.real;
    istruct.llft.y = init->lleft.imag;
    istruct.ledg = init->lleft.length;
    istruct.ilev = init->interleave;
    const int iterations = ITERATIONS * (int)init->interleave;
    if (init->refname[0])
        refhost = load_ref(init->refname, &rh);
    CUDA_CHECK(cudaSetDevice(0));
    CUDA_CHECK(cudaMalloc(&dev_init_ptr, sizeof(Init)));
    CUDA_CHECK(cudaMalloc(&dev_pix_ptr, WIDTH*HEIGHT*sizeof(uint32_t)));
    CUDA_CHECK(cudaMalloc(&dev_col_ptr, colors->size*sizeof(uint32_t)));
    CUDA_CHECK(cudaMemcpy(dev_init_ptr, &istruct, sizeof(Init), cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dev_col_ptr, colors->pall, colors->size*sizeof(uint32_t), cudaMemcpyHostToDevice));
    dim3 dimBlock(BLOCK_SIZE, BLOCK_SIZE);
    dim3 dimGrid(WIDTH/BLOCK_SIZE, HEIGHT/BLOCK_SIZE);
    if (refhost) {
        const int refn = (int)rh.count;
        CUDA_CHECK(cudaMalloc(&dev_ref_ptr, rh.count*sizeof(Cd)));
        CUDA_CHECK(cudaMemcpy(dev_ref_ptr, refhost, rh.count*sizeof(Cd), cudaMemcpyHostToDevice));
        if (rh.step_exp < FX_STEP_EXP) {
            MandKernPertFx<<<dimGrid, dimBlock>>>(dev_ref_ptr, refn, rh.step_mant, rh.step_exp, dev_col_ptr, dev_pix_ptr, iterations, colors->size);
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
            MandKernPert<<<dimGrid, dimBlock>>>(dev_ref_ptr, refn, bv, step, dev_col_ptr, dev_pix_ptr, iterations, colors->size);
        }
    } else {
        MandKern<<<dimGrid, dimBlock>>>(dev_col_ptr, dev_pix_ptr, dev_init_ptr, colors->size);
    }
    CUDA_CHECK(cudaGetLastError());
    uint32_t *pixarr = (uint32_t*)malloc(HEIGHT*WIDTH*sizeof(uint32_t));
    CUDA_CHECK(cudaMemcpy(pixarr, dev_pix_ptr, HEIGHT*WIDTH*sizeof(uint32_t), cudaMemcpyDeviceToHost));
    const int write_failed = gen_bmp(init->filename, pixarr, WIDTH, HEIGHT);
    cudaFree(dev_bla_ptr);
    cudaFree(dev_ref_ptr);
    cudaFree(dev_init_ptr);
    cudaFree(dev_pix_ptr);
    cudaFree(dev_col_ptr);
    free(blahost);
    free(refhost);
    free(pixarr);
    free(colors->pall);
    free(colors);
    free(init);
    return write_failed ? 1 : 0;
}
