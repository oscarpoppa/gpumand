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
    Pixel lgr = {0xF0, 0xF0, 0xF0};
    ColorInfo *ret = (ColorInfo*)malloc(sizeof(ColorInfo));
    ret->pall = (uint32_t*)malloc(5*ITERATIONS*sizeof(uint32_t));
    uint32_t *pp = ret->pall;
    Pixel current = {0xC0, 0x03, 0x03};
    while(current.grn++ < 0xFC) {
        putpix(pp++, &current);
        current.grn++;
        current.grn++;
    }
//yellow
    while(current.red-- > 0x03) {
        putpix(pp++, &current);
        current.red--;
        current.red--;
    }
//green
    while(current.blu++ < 0xFC)
        putpix(pp++, &current);
//cyan
    while(current.grn-- > 0x03)
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
    while(current.red++ < 0xFC)
        putpix(pp++, &current);
    while(current.grn++ < 0xFC)
        putpix(pp++, &current);
    for (int i=0;i<12;i++)
        putpix(pp++, &lgr);
    ret->size = count;
    return ret;
}

