#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mtypes.h"
#define _numcols 2000

static uint32_t count = 0;

void putpix(uint32_t *pp, const Pixel *pix) {
    uint8_t *cptr;
    count++;
    cptr = (uint8_t*)pp;
    cptr[3] = 0;
    cptr[2] = pix->red;
    cptr[1] = pix->grn;
    cptr[0] = pix->blu;
    return;
}

ColorInfo *make_pall() {
    Pixel current = {0x00, 0x00, 0x00};
    ColorInfo *ret = (ColorInfo*)malloc(sizeof(ColorInfo));
    ret->pall = (uint32_t*)malloc(_numcols*sizeof(uint32_t));
    uint32_t *pp = ret->pall;
    putpix(pp, &current);
    pp++;
    while (1){
        current.red++; 
        putpix(pp, &current);
        pp++;
        if (current.red == 0xFF)
            break;
    };  
    while (1){
        current.grn++; 
        current.red--; 
        putpix(pp, &current);
        pp++;
        if (current.grn == 0xFF)
            break;
    };  
    while (1) {
        current.grn--;
        current.blu++;
        putpix(pp, &current);
        pp++;
        if (current.red == 0)
             break;
    };
    while (1) {
        current.blu--;
        current.red++; 
        putpix(pp, &current);
        pp++;
        if (current.blu == 0xFF)
             break;
    };
    int j;
    Pixel white = {0xFF, 0xFF, 0xFF};
    for (j=0; j<=12; j++) {
        putpix(pp, &white);
        pp++;
    }
    ret->size = count;
    return ret;
}

