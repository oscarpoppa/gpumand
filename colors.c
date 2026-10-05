#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mtypes.h"
#include "iter.h"

#define PALETTE_CAPACITY (5 * ITERATIONS)

/* Appends one colour at *pp and advances it; refuses to write past end. */
static void putpix(uint32_t **pp, const uint32_t *end, const Pixel *pix) {
    uint8_t *cptr;
    if (*pp >= end) {
        fprintf(stderr, "palette overflow (capacity %d)\n", PALETTE_CAPACITY);
        exit(1);
    }
    cptr = (uint8_t*)*pp;
    cptr[3] = 0;
    cptr[2] = pix->red;
    cptr[1] = pix->grn;
    cptr[0] = pix->blu;
    (*pp)++;
}

ColorInfo *make_pall() {
    Pixel lgr = {0xF0, 0xF0, 0xF0};
    ColorInfo *ret = (ColorInfo*)malloc(sizeof(ColorInfo));
    if (!ret) {
        perror("malloc");
        exit(1);
    }
    ret->pall = (uint32_t*)malloc(PALETTE_CAPACITY*sizeof(uint32_t));
    if (!ret->pall) {
        perror("malloc");
        exit(1);
    }
    uint32_t *pp = ret->pall;
    const uint32_t *end = ret->pall + PALETTE_CAPACITY;
    Pixel current = {0xC0, 0x03, 0x03};
    while(current.grn++ < 0xFC) {
        putpix(&pp, end, &current);
        current.grn++;
        current.grn++;
    }
//yellow
    while(current.red-- > 0x03) {
        putpix(&pp, end, &current);
        current.red--;
        current.red--;
    }
//green
    while(current.blu++ < 0xFC)
        putpix(&pp, end, &current);
//cyan
    while(current.grn-- > 0x03)
        putpix(&pp, end, &current);
//blue     
    while(current.red++ < 0x7F)
        putpix(&pp, end, &current);
//purple     
    while(1) { //down to grayscale
        if (current.red > 0xE5)
            break;
        current.red++;
        current.grn+=0x02;
        putpix(&pp, end, &current);
    }
    while(current.red++ < 0xFC)
        putpix(&pp, end, &current);
    while(current.grn++ < 0xFC)
        putpix(&pp, end, &current);
    for (int i=0;i<12;i++)
        putpix(&pp, end, &lgr);
    ret->size = (uint32_t)(pp - ret->pall);
    return ret;
}

