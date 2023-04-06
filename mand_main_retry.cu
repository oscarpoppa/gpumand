#include <stdio.h>
#include <stdint.h>
#include "mtypes.h"
#include "colors.h"
#include "bmp.h"
#include "aspect.h"
#include "get_coords.h"

#define BLOCK_SIZE 16

typedef double2 cudaDoubleComplex;

typedef struct {
    cudaDoubleComplex llft;
    double ledg;
    size_t pitch;
    int colsz;
    int ilev;
} Init;

__global__ void MandKern(cudaDoubleComplex* dev_cst_ptr, const uint32_t* dev_col_ptr, uint32_t* dev_pix_ptr, const Init* dev_init_ptr) {
    int cnt = 0; 
    const int iterations = dev_init_ptr->colsz * dev_init_ptr->ilev;
    const int pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    const int pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    __shared__ cudaDoubleComplex row[BLOCK_SIZE];
    row[threadIdx.x].x = 0.0; 
    row[threadIdx.x].y = 0.0;
    cudaDoubleComplex *locconst = (cudaDoubleComplex*)((char*)dev_cst_ptr+pix_y*dev_init_ptr->pitch);
    locconst[pix_x].x = dev_init_ptr->llft.x+dev_init_ptr->ledg*(double)pix_x/WIDTH; 
    locconst[pix_x].y = dev_init_ptr->llft.y+dev_init_ptr->ledg*(double)pix_y/WIDTH;
    #pragma unroll 165
    for (; cnt<iterations; cnt++) {
        double nux = row[threadIdx.x].x * row[threadIdx.x].x - row[threadIdx.x].y * row[threadIdx.x].y + locconst[pix_x].x;
        row[threadIdx.x].y = 2.0 * row[threadIdx.x].x * row[threadIdx.x].y + locconst[pix_x].y; 
        row[threadIdx.x].x = nux;
        if (sqrt(pow(row[threadIdx.x].y,2.0)+pow(row[threadIdx.x].y,2.0)) > 2.0)
            break; 
    }
    if (cnt == iterations)
        dev_pix_ptr[WIDTH*pix_y+pix_x] = 0;
    else
        dev_pix_ptr[WIDTH*pix_y+pix_x] = dev_col_ptr[cnt/dev_init_ptr->ilev];
}

int main(int argc, char **argv) {
    Init istruct, *dev_init_ptr;
    size_t pitch;
    uint32_t *dev_pix_ptr, *dev_col_ptr;
    cudaDoubleComplex* dev_cst_ptr;
    RunStart *init = get_coords(argc, argv);
    ColorInfo *colors = make_pall();
    istruct.colsz = colors->size;
    istruct.llft.x = init->lleft.real;
    istruct.llft.y = init->lleft.imag;
    istruct.ledg = init->lleft.length;
    istruct.ilev = init->interleave;
    cudaSetDevice(0);
    cudaMallocPitch(&dev_cst_ptr, &pitch, WIDTH*sizeof(cudaDoubleComplex), HEIGHT);
    istruct.pitch = pitch;
    cudaMalloc(&dev_init_ptr, sizeof(Init));
    cudaMalloc(&dev_pix_ptr, WIDTH*HEIGHT*sizeof(uint32_t));
    cudaMalloc(&dev_col_ptr, colors->size*sizeof(uint32_t));
    cudaMemcpy(dev_init_ptr, &istruct, sizeof(Init), cudaMemcpyHostToDevice);
    cudaMemcpy(dev_col_ptr, colors->pall, colors->size*sizeof(uint32_t), cudaMemcpyHostToDevice);
    dim3 dimBlock(BLOCK_SIZE, BLOCK_SIZE);
    dim3 dimGrid(WIDTH/BLOCK_SIZE, HEIGHT/BLOCK_SIZE);
    MandKern<<<dimGrid, dimBlock>>>(dev_cst_ptr, dev_col_ptr, dev_pix_ptr, dev_init_ptr);
    uint32_t *pixarr = (uint32_t*)malloc(HEIGHT*WIDTH*sizeof(uint32_t));
    cudaMemcpy(pixarr, dev_pix_ptr, HEIGHT*WIDTH*sizeof(uint32_t), cudaMemcpyDeviceToHost); 
    gen_bmp(init->filename, pixarr, WIDTH, HEIGHT);
    cudaFree(dev_cst_ptr);
    cudaFree(dev_init_ptr);
    cudaFree(dev_pix_ptr);
    cudaFree(dev_col_ptr);
    free(pixarr);
    free(colors);
    free(init);
    return 0;
}

