#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "mtypes.h"
#include "bmp.h"
#define _bitsperpixel 32
#define _planes 1
#define _compression 0
#define _pixelpermeter 2835 /* 72 DPI */

int gen_bmp(const char *filename, const uint32_t *pixarray, const uint32_t width, const uint32_t height) {
    FILE *fp = fopen(filename, "wb");
    if (!fp) {
        perror(filename);
        return -1;
    }
    bitmap *pbitmap = (bitmap*)calloc(1, sizeof(bitmap));
    if (!pbitmap) {
        fclose(fp);
        return -1;
    }
    memcpy(pbitmap->fileheader.signature, "BM", 2);
    pbitmap->fileheader.filesize = sizeof(bitmap) + (width * height * sizeof(uint32_t));
    pbitmap->fileheader.fileoffset_to_pixelarray = sizeof(bitmap);
    pbitmap->bitmapinfoheader.dibheadersize = sizeof(bitmapinfoheader);
    pbitmap->bitmapinfoheader.width = width;
    pbitmap->bitmapinfoheader.height = height;
    pbitmap->bitmapinfoheader.planes = _planes;
    pbitmap->bitmapinfoheader.bitsperpixel = _bitsperpixel;
    pbitmap->bitmapinfoheader.compression = _compression;
    pbitmap->bitmapinfoheader.imagesize = width * height * sizeof(uint32_t);
    pbitmap->bitmapinfoheader.ypixelpermeter = _pixelpermeter;
    pbitmap->bitmapinfoheader.xpixelpermeter = _pixelpermeter;
    pbitmap->bitmapinfoheader.numcolorspallette = 0;
    /* file permissions come from the umask (typically 0644), not a forced world-writable mode */
    int ok = fwrite(pbitmap, 1, sizeof(bitmap), fp) == sizeof(bitmap) &&
             fwrite(pixarray, sizeof(uint32_t), (size_t)height * width, fp) == (size_t)height * width;
    free(pbitmap);
    if (fclose(fp) != 0)
        ok = 0;
    if (!ok)
        fprintf(stderr, "error writing %s\n", filename);
    return ok ? 0 : -1;
}
