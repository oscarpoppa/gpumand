#ifndef __MTYPES_H
#include <stdint.h>

typedef struct cstruct {
    double real;
    double imag;
    double length;
} Complex;

/* How smooth iteration counts become colours (see colorize.h). */
typedef struct {
    char palette[32];
    int mapping;        /* MAP_HISTOGRAM, MAP_LINEAR or MAP_LOG */
    double scale;       /* 0 = the mapping's default */
    double shift;       /* rotates the palette; 1 is a full turn */
    uint32_t interior;  /* 0x00RRGGBB for pixels that never escape */
} ColorOpts;

typedef struct {
    Complex lleft;
    char filename[256];
    char refname[256];
    char nuout[256];    /* optional: also write the raw smooth iteration counts here */
    uint32_t interleave;
    ColorOpts color;
} RunStart;

typedef struct {
    uint8_t red;
    uint8_t grn;
    uint8_t blu;
} Pixel;

#pragma pack(push,1)

typedef struct{
    uint8_t signature[2];
    uint32_t filesize;
    uint32_t reserved;
    uint32_t fileoffset_to_pixelarray;
} fileheader;

typedef struct{
    uint32_t dibheadersize;
    uint32_t width;
    uint32_t height;
    uint16_t planes;
    uint16_t bitsperpixel;
    uint32_t compression;
    uint32_t imagesize;
    uint32_t ypixelpermeter;
    uint32_t xpixelpermeter;
    uint32_t numcolorspallette;
    uint32_t mostimpcolor;
} bitmapinfoheader;

typedef struct {
    fileheader fileheader;
    bitmapinfoheader bitmapinfoheader;
} bitmap;

#pragma pack(pop)
#define __MTYPES_H
#endif
