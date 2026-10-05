#ifndef __BMP_H
#define __BMP_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Writes a width x height 32-bit BMP. Returns 0 on success, -1 on any I/O error. */
int gen_bmp(const char *, const uint32_t *, const uint32_t, const uint32_t);

#ifdef __cplusplus
}
#endif
#endif
