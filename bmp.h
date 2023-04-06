//$Id: bmp.h,v 1.1 2017/12/19 20:00:20 dan Exp $
#ifndef __BMP_H
#include <stdint.h>
extern "C" {
void gen_bmp(const char *, uint32_t *, const uint32_t, const uint32_t);
};
#define ___BMP_H
#endif
