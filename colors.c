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

    while(current.red++ != 0xFF)
        putpix(pp++, &current);
    while(current.grn++ != 0xFF)
        putpix(pp++, &current);
    while(current.red-- != 0x00)
        putpix(pp++, &current);
    while(current.blu++ != 0xFF)
        putpix(pp++, &current);
    while(current.grn-- != 0x00)
        putpix(pp++, &current);
    while(current.red++ != 0xFF)
        putpix(pp++, &current);
    while(current.grn++ != 0xFF)
        putpix(pp++, &current);
    while(current.blu-- != 0x00)
        putpix(pp++, &current);
    while(current.grn-- != 0x00)
        putpix(pp++, &current);
    while(current.red-- != 0x00)
        putpix(pp++, &current);
    ret->size = count;
    return ret;
}

