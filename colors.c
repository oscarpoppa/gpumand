#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mtypes.h"
#include "iter.h"

static uint32_t count = 0;

void putpix(uint32_t *pp, const Pixel *pix) {
    uint8_t *cptr;
    if (count == ITERATIONS)
        return;
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
    Pixel white = {0xFF, 0xFF, 0xFF};
    ColorInfo *ret = (ColorInfo*)malloc(sizeof(ColorInfo));
    ret->pall = (uint32_t*)malloc(ITERATIONS*sizeof(uint32_t));
    uint32_t *pp = ret->pall;
    putpix(pp++, &current);
    while (1){
        current.red++; 
        putpix(pp++, &current);
        if (current.red == 0xFF)
            break;
    };  
    while (1){
        current.grn++; 
        putpix(pp++, &current);
        if (current.grn == 0xFF)
            break;
    };  
    while (1) {
        current.red--;
        putpix(pp++, &current);
        if (current.red == 0)
             break;
    };
    while (1) {
        current.blu++;
        putpix(pp++, &current);
        if (current.blu == 0xFF)
             break;
    };
    while (1) {
        current.grn--;
        putpix(pp++, &current);
        if (current.grn == 0)
            break; 
    }
    while (1)  {
        current.red++;
        putpix(pp++, &current);
        if (current.red == 0xFF)
            break;
    }
    while (1)  {
        current.grn++;
        putpix(pp++, &current);
        if (current.grn == 0xFF)
            break;
    }
    int j;
    for (j=count; j<=ITERATIONS; j++) {
        putpix(pp++, &white);
    }
    ret->size = count;
    return ret;
}

