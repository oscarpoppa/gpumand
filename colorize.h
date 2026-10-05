#ifndef __COLORIZE_H
#define __COLORIZE_H
/*
 * Turns the renderers' smooth iteration counts (nu) into colors, on the host, so `mand`, `mand-cpu`
 * and the `colorize` tool all color identically and an image can be recolored without rendering
 * again.
 *
 * A palette is a table of PALETTE_SIZE colors forming a closed loop. nu is turned into a position
 * on the loop by a mapping (below); the pixel gets the entry at floor(frac(position) * PALETTE_SIZE).
 * Pixels that never escaped (nu < 0) get the interior color.
 */
#include <stddef.h>
#include <stdint.h>
#include "mtypes.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PALETTE_SIZE 4096

/* Mappings from nu to a position on the palette loop:
 *   histogram  rank of nu among the escaped pixels (0..1), times scale cycles. Spreads the colors
 *              evenly whatever the depth or iteration limit. scale = cycles over the range.
 *   linear     nu / scale: one cycle per `scale` iterations.
 *   log        log2(nu + 1) * scale: `scale` cycles per doubling of the count.
 * position += shift (a rotation of the palette, 0..1). A scale of 0 means "that mapping's default". */
enum { MAP_HISTOGRAM = 0, MAP_LINEAR = 1, MAP_LOG = 2 };

void colorize_defaults(ColorOpts *o);

/* Handles one "--name=value" command line option. Returns 1 if it was a color option and is
 * valid, 0 if it is not a color option, -1 if it is one but invalid (message in err). */
int colorize_parse_option(ColorOpts *o, const char *arg, char *err, size_t errlen);

/* Palettes, by name. palette_build fills table[PALETTE_SIZE] with 0x00RRGGBB colors; -1 if unknown. */
int palette_count(void);
const char *palette_name(int i);
const char *palette_description(int i);
int palette_build(const char *name, uint32_t *table);

/* Positions on the loop for n values of nu (before taking the fractional part); -1 for interior. */
void color_positions(const double *nu, size_t n, const ColorOpts *o, double *pos);

/* Colors a w x h image of nu values. Returns 0, or -1 if the palette name is unknown. */
int colorize_image(const double *nu, int w, int h, const ColorOpts *o, uint32_t *out);

/* Raw nu image files: "MNU1", uint32 w, uint32 h, then w*h doubles. */
int nu_write(const char *path, const double *nu, uint32_t w, uint32_t h);
double *nu_read(const char *path, uint32_t *w, uint32_t *h); /* malloc'd, or NULL with a message on stderr */

#ifdef __cplusplus
}
#endif
#endif
