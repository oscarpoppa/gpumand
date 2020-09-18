//$Id: mand_main_kern.cu,v 1.3 2017/12/06 20:51:29 dan Exp $
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <malloc.h>
#include "bmp.h"
#include "colors.h"
#include "mtypes.h"
#include "get_coords.h"
#include "aspect.h"
#define _block_size 20
#define cudaCheckError() { \
    cudaError_t e=cudaGetLastError(); \
    if(e!=cudaSuccess) { \
        fprintf(stderr, "Cuda failure %s:%d: '%s'\n",__FILE__,__LINE__,cudaGetErrorString(e)); \
        exit(0); \
    } \
}

__device__ 
void domult(Complex *ret, const Complex *cons) {
    double nureal, nuimag;
    nureal = pow(ret->real,2.0) - pow(ret->imag,2.0) + cons->real; 
    nuimag = 2.0 * ret->real * ret->imag + cons->imag;
    ret->imag = nuimag;
    ret->real = nureal;
    ret->length = sqrt(pow(nureal,2.0) + pow(nuimag,2.0));
}

__global__
void pixKern(uint32_t *pixarr, const Complex *log_lowleft, const uint32_t *colors, const uint32_t size, const uint32_t interleave) {
    uint32_t pix_x, pix_y, itr, iterations = size * interleave;
    double log_edge = log_lowleft->length;
    pix_x = blockIdx.x * blockDim.x + threadIdx.x;
    pix_y = blockIdx.y * blockDim.y + threadIdx.y;
    Complex ret = {0.0, 0.0, 0.0};
    Complex cons;
    cons.real = log_lowleft->real + (double)log_edge * (double)pix_x / _width;
    cons.imag = log_lowleft->imag + (double)log_edge * (double)pix_y / _width;
    cons.length = sqrt(pow(cons.real,2.0) + pow(cons.imag,2.0));
    for (itr=0; itr<iterations; itr++) {
        domult(&ret, &cons);
        if (ret.length > 2.0)
            break;
    }
    if (itr == iterations)
        pixarr[_width*pix_y+pix_x] = 0;
    else
        pixarr[_width*pix_y+pix_x] = colors[itr / interleave];
}

int main(int argc, char *argv[]) {
    const unsigned arlen = _width * _height * sizeof(uint32_t);
    uint32_t *d_colors, *d_pixarray, *pixarray = (uint32_t*)malloc(arlen);
    RunStart *init = get_coords(argc, argv);
    Complex *d_log_lowleft, *log_lowleft = (Complex*)malloc(sizeof(Complex));
    log_lowleft->real = init->lleft.real;
    log_lowleft->imag = init->lleft.imag;
    log_lowleft->length = init->lleft.length;
    ColorInfo *colors = make_pall(); 
    cudaSetDevice(0);
    cudaMalloc(&d_colors, colors->size * sizeof(uint32_t));
    cudaMalloc(&d_log_lowleft, sizeof(Complex));
    cudaMemcpy(d_log_lowleft, log_lowleft, sizeof(Complex), cudaMemcpyHostToDevice);
    cudaMemcpy(d_colors, colors->pall, colors->size * sizeof(uint32_t), cudaMemcpyHostToDevice);
    cudaMalloc(&d_pixarray, arlen);
    dim3 dimBlock(_block_size, _block_size);
    dim3 dimGrid(_width / _block_size, _height / _block_size);
    pixKern<<<dimGrid, dimBlock>>>(d_pixarray, d_log_lowleft, d_colors, colors->size, init->interleave);
    cudaMemcpy(pixarray, d_pixarray, arlen, cudaMemcpyDeviceToHost);
    cudaFree(d_log_lowleft);
    cudaFree(d_colors);
    free(log_lowleft);
    cudaCheckError();
    gen_bmp(init->filename, pixarray, _width, _height);
    cudaFree(d_pixarray);
    free(pixarray);
    free(init);
    free(colors->pall);
    free(colors);
    return 0;
}

