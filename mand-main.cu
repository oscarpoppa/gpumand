#include <stdio.h>
#include <stdint.h>
#include "mtypes.h"
#include "colors.h"
#include "bmp.h"
#include "iter.h"
#include "aspect.h"
#include "get-coords.h"

#define BLOCK_SIZE 16

typedef double2 cudaDoubleComplex;

typedef struct {
    cudaDoubleComplex llft;
    double ledg;
    int ilev;
} Init;

__global__ void MandKern(const uint32_t* dev_col_ptr, uint32_t* dev_pix_ptr, const Init* dev_init_ptr, const uint32_t palsz) {
    int cnt = 0; 
    const int iterations = ITERATIONS * dev_init_ptr->ilev;
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
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
        dev_pix_ptr[WIDTH*pix_y+pix_x] = dev_col_ptr[cnt*palsz/iterations];
}

int main(int argc, char **argv) {
    Init istruct, *dev_init_ptr;
    uint32_t *dev_pix_ptr, *dev_col_ptr;
    RunStart *init = get_coords(argc, argv);
    ColorInfo *colors = make_pall();
    istruct.llft.x = init->lleft.real;
    istruct.llft.y = init->lleft.imag;
    istruct.ledg = init->lleft.length;
    istruct.ilev = init->interleave;
    cudaSetDevice(0);
    cudaMalloc(&dev_init_ptr, sizeof(Init));
    cudaMalloc(&dev_pix_ptr, WIDTH*HEIGHT*sizeof(uint32_t));
    cudaMalloc(&dev_col_ptr, colors->size*sizeof(uint32_t));
    cudaMemcpy(dev_init_ptr, &istruct, sizeof(Init), cudaMemcpyHostToDevice);
    cudaMemcpy(dev_col_ptr, colors->pall, colors->size*sizeof(uint32_t), cudaMemcpyHostToDevice);
    dim3 dimBlock(BLOCK_SIZE, BLOCK_SIZE);
    dim3 dimGrid(WIDTH/BLOCK_SIZE, HEIGHT/BLOCK_SIZE);
    MandKern<<<dimGrid, dimBlock>>>(dev_col_ptr, dev_pix_ptr, dev_init_ptr, colors->size);
    uint32_t *pixarr = (uint32_t*)malloc(HEIGHT*WIDTH*sizeof(uint32_t));
    cudaMemcpy(pixarr, dev_pix_ptr, HEIGHT*WIDTH*sizeof(uint32_t), cudaMemcpyDeviceToHost); 
    gen_bmp(init->filename, pixarr, WIDTH, HEIGHT);
    cudaFree(dev_init_ptr);
    cudaFree(dev_pix_ptr);
    cudaFree(dev_col_ptr);
    free(pixarr);
    free(colors->pall);
    free(colors);
    free(init);
    return 0;
}

