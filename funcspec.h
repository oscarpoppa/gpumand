#ifndef __FUNCSPEC_H
#define __FUNCSPEC_H
/*
 * The --func=FILE option: a small text file saying which function the renderer iterates. Without it
 * the renderers draw the built-in z^2 + c. The file is written by funcspec.py, for example
 *
 *     gpumand-func 1
 *     kind power
 *     degree 3
 *
 * draws z^3 + c. The first line is exactly "gpumand-func 1", every other line is "key value", each key
 * appears once, and an unknown key is an error, so a file that is not understood is never half-used.
 */
#include <stddef.h>
#include "mtypes.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Reads and checks a function file. Returns 0 and fills *f, or -1 with a message in err. */
int funcspec_load(const char *path, FuncSpec *f, char *err, size_t errlen);

#ifdef __cplusplus
}
#endif
#endif
