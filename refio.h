#ifndef __REFIO_H
#define __REFIO_H
#include <stdint.h>
#include "pert.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Header of a reference orbit file written by deepzoom.py: the pixel step is
 * step_mant * 2^step_exp, followed by count (re, im) double pairs. */
typedef struct {
    uint32_t count;
    int32_t step_exp;
    double step_mant;
} RefHeader;

#define MAX_REF_POINTS (1u << 24)

/* Loads a reference orbit; prints a message and exits with status 1 on any problem. */
Cd *load_ref(const char *path, RefHeader *h);

#ifdef __cplusplus
}
#endif
#endif
