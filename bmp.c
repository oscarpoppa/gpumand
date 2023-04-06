//$Id: bmp.c,v 1.4 2017/12/31 05:17:32 dan Exp dan $
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include <sys/stat.h>
#include "aspect.h"
#include "mtypes.h"
#define _bitsperpixel 32
#define _planes 1
#define _compression 0
#define _xpixelpermeter 0x130B * HEIGHT / WIDTH //2835 , 72 DPI
#define _ypixelpermeter 0x130B * HEIGHT / WIDTH //2835 , 72 DPI

void gen_bmp(const char *filename, uint32_t *pixarray, const uint32_t width, const uint32_t height) {
    FILE *fp = fopen(filename,"wb");
    bitmap *pbitmap  = (bitmap*)calloc(1,sizeof(bitmap));
    strncpy((char*) pbitmap->fileheader.signature,"BM",2);
    pbitmap->fileheader.filesize = sizeof(bitmap) + (width * height * sizeof(uint32_t));
    pbitmap->fileheader.fileoffset_to_pixelarray = sizeof(bitmap);
    pbitmap->bitmapinfoheader.dibheadersize =sizeof(bitmapinfoheader);
    pbitmap->bitmapinfoheader.width = WIDTH;
    pbitmap->bitmapinfoheader.height = HEIGHT;
    pbitmap->bitmapinfoheader.planes = _planes;
    pbitmap->bitmapinfoheader.bitsperpixel = _bitsperpixel;
    pbitmap->bitmapinfoheader.compression = _compression;
    pbitmap->bitmapinfoheader.imagesize = width * height * sizeof(uint32_t);
    pbitmap->bitmapinfoheader.ypixelpermeter = _ypixelpermeter ;
    pbitmap->bitmapinfoheader.xpixelpermeter = _xpixelpermeter ;
    pbitmap->bitmapinfoheader.numcolorspallette = 0;
    fwrite (pbitmap, 1, sizeof(bitmap),fp);
    fwrite(pixarray,4,height * width, fp);
    fchmod(fileno(fp), S_IRGRP | S_IWGRP | S_IRUSR | S_IWUSR | S_IROTH | S_IWOTH);
    fclose(fp);
    free(pbitmap);
}
