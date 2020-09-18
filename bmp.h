//$Id: bmp.h,v 1.4 2017/12/04 05:45:29 dan Exp $
#ifndef __BMP_H
#include <stdint.h>
extern "C" {
void gen_bmp(const char *, uint32_t *, const uint32_t, const uint32_t);
};
#define ___BMP_H
#endif
