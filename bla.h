#ifndef __BLA_H
#define __BLA_H
#include "pert.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Default tolerance: a skip is used only while the dropped d^2 term stays below
 * BLA_EPS times the kept linear term. */
#define BLA_EPS 5.9604644775390625e-8 /* 2^-24 */

/* Reference orbits longer than this get no BLA table (memory: ~80 bytes per point). */
#define BLA_MAX_REF (1 << 22)

/*
 * Builds the BLA table for ref[0..refn-1]. dcmax bounds |dc| over every pixel of the
 * image. On success *mem is a malloc'd table (free it) and view->tab points into it;
 * view->nlev is 0 (and *mem NULL) if refn is too short to need one. Returns 0 on
 * success, nonzero if out of memory.
 */
int bla_build(const Cd *ref, int refn, double eps, double dcmax, BlaView *view, Bla **mem);

#ifdef __cplusplus
}
#endif
#endif
