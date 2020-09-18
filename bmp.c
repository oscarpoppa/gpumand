//$Id: bmp.c,v 1.6 2017/12/03 22:07:43 dan Exp $
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "aspect.h"
#include "mtypes.h"
#define _bitsperpixel 32
#define _planes 1
#define _compression 0
#define _xpixelpermeter 0x130B * _height / _width //2835 , 72 DPI
#define _ypixelpermeter 0x130B * _height / _width //2835 , 72 DPI

void gen_bmp(const char *filename, uint32_t *pixarray, const uint32_t width, const uint32_t height) {
    FILE *fp = fopen(filename,"wb");
    bitmap *pbitmap  = (bitmap*)calloc(1,sizeof(bitmap));
    strncpy((char*) pbitmap->fileheader.signature,"BM",2);
    pbitmap->fileheader.filesize = sizeof(bitmap) + (width * height * sizeof(uint32_t));
    pbitmap->fileheader.fileoffset_to_pixelarray = sizeof(bitmap);
    pbitmap->bitmapinfoheader.dibheadersize =sizeof(bitmapinfoheader);
    pbitmap->bitmapinfoheader.width = _width;
    pbitmap->bitmapinfoheader.height = _height;
    pbitmap->bitmapinfoheader.planes = _planes;
    pbitmap->bitmapinfoheader.bitsperpixel = _bitsperpixel;
    pbitmap->bitmapinfoheader.compression = _compression;
    pbitmap->bitmapinfoheader.imagesize = width * height * sizeof(uint32_t);
    pbitmap->bitmapinfoheader.ypixelpermeter = _ypixelpermeter ;
    pbitmap->bitmapinfoheader.xpixelpermeter = _xpixelpermeter ;
    pbitmap->bitmapinfoheader.numcolorspallette = 0;
    fwrite (pbitmap, 1, sizeof(bitmap),fp);
    fwrite(pixarray,4,height * width, fp);
    fclose(fp);
    free(pbitmap);
}
