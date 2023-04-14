#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mtypes.h"
#include "iter.h"

static uint32_t count = 0;

void putpix(uint32_t *pp, const Pixel *pix) {
    uint8_t *cptr;
    count++;
    cptr = (uint8_t*)pp;
    cptr[3] = 0;
    cptr[2] = pix->red;
    cptr[1] = pix->grn;
    cptr[0] = pix->blu;
    //printf("%i %i %i\n", pix->red, pix->grn, pix->blu);
    return;
}

ColorInfo *make_pall() {
    Pixel white = {0xFF, 0xFF, 0xFF};
    ColorInfo *ret = (ColorInfo*)malloc(sizeof(ColorInfo));
    ret->pall = (uint32_t*)malloc(5*ITERATIONS*sizeof(uint32_t));
    uint32_t *pp = ret->pall;
    Pixel current = {0x80, 0x01, 0x01};
    while(current.red++ < 0xFE)
        putpix(pp++, &current);
    while(current.grn++ < 0xFE)
        putpix(pp++, &current);
//yellow
    while(current.red-- > 0x01)
        putpix(pp++, &current);
//green
    while(current.blu++ < 0xFE)
        putpix(pp++, &current);
//cyan
    while(current.grn-- > 0x01)
        putpix(pp++, &current);
//blue     
    while(current.red++ < 0x7F)
        putpix(pp++, &current);
//purple     
    while(1) { //down to grayscale
        if (current.red > 0xE5)
            break;
        current.red++;
        current.grn+=0x02;
        putpix(pp++, &current);
    }
    while(current.red++ < 0xFE)
        putpix(pp++, &current);
    while(current.grn++ < 0xFE)
        putpix(pp++, &current);
    for (int i=0;i<12;i++)
        putpix(pp++, &current);
    ret->size = count;
    return ret;
}

