#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "colorize.h"

/* ---- color spaces: palettes are interpolated in OKLab so that blends look even ---------------- */

typedef struct { double L, a, b; } Lab;

static double srgb_to_lin(double c) { return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4); }
static double lin_to_srgb(double c) {
    if (c < 0.0) c = 0.0;
    if (c > 1.0) c = 1.0;
    return c <= 0.0031308 ? 12.92 * c : 1.055 * pow(c, 1.0 / 2.4) - 0.055;
}

static Lab rgb_to_lab(uint32_t rgb) {
    const double r = srgb_to_lin(((rgb >> 16) & 255) / 255.0), g = srgb_to_lin(((rgb >> 8) & 255) / 255.0),
                 b = srgb_to_lin((rgb & 255) / 255.0);
    const double l = cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const double m = cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const double s = cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    Lab o = { 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
              1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
              0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s };
    return o;
}

static uint32_t lab_to_rgb(Lab c) {
    const double l_ = c.L + 0.3963377774 * c.a + 0.2158037573 * c.b;
    const double m_ = c.L - 0.1055613458 * c.a - 0.0638541728 * c.b;
    const double s_ = c.L - 0.0894841775 * c.a - 1.2914855480 * c.b;
    const double l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
    const double r = lin_to_srgb(+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
    const double g = lin_to_srgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
    const double b = lin_to_srgb(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
    return ((uint32_t)(r * 255.0 + 0.5) << 16) | ((uint32_t)(g * 255.0 + 0.5) << 8) | (uint32_t)(b * 255.0 + 0.5);
}

/* ---- the palettes: closed loops through a few key colors, smoothed with a periodic Catmull-Rom spline */

#define MAX_STOPS 16
typedef struct {
    const char *name;
    const char *desc;
    int n;
    uint32_t stops[MAX_STOPS];
} Gradient;

static const Gradient GRADIENTS[] = {
    { "twilight", "deep indigo through violet and coral to gold and aqua", 9,
      { 0x0b1040, 0x3a2a8f, 0x8e44ad, 0xd6458d, 0xff7f50, 0xffd166, 0xbde7f0, 0x2a9d8f, 0x14305a } },
    { "fire", "embers: black-red, red, orange, yellow, white-hot and back", 10,
      { 0x100000, 0x7a0f0a, 0xe03a10, 0xff9a1a, 0xffe45e, 0xfff8e1, 0xffcf4a, 0xff7a18, 0xc02a0c, 0x4a0805 } },
    { "ocean", "navy, blue, turquoise and foam", 8,
      { 0x03045e, 0x0077b6, 0x00b4d8, 0x90e0ef, 0xcaf0f8, 0x48cae4, 0x0096c7, 0x023e8a } },
    { "aurora", "midnight green, emerald, mint, violet and pink", 9,
      { 0x0b132b, 0x1c6e5d, 0x3ddc97, 0xb8f2e6, 0x7b6cf6, 0xc64fd3, 0xff8fb1, 0x2fbf9b, 0x123a3a } },
    { "ice", "pale ice blue to deep blue and back", 6,
      { 0xf4faff, 0xbfe3ff, 0x6eb5ff, 0x2f6bd6, 0x14307a, 0x2f6bd6 } },
    { "sunset", "plum, rose, orange and gold", 7,
      { 0x2b1055, 0x7b2d8b, 0xd94f70, 0xff8c42, 0xffd56b, 0xff8c42, 0xd94f70 } },
    { "gray", "smooth black-to-white-and-back, for contrast", 4,
      { 0x000000, 0x808080, 0xffffff, 0x808080 } },
};
#define N_GRADIENTS ((int)(sizeof(GRADIENTS) / sizeof(GRADIENTS[0])))

/* extra palettes that are not a fixed list of stops: "rainbow" and the original "classic" */
static const char *EXTRA_NAMES[] = { "rainbow", "classic" };
static const char *EXTRA_DESCS[] = { "every hue, evenly spaced in perceived brightness", "the original red-yellow-green-cyan-blue-purple-gray ramp (mirrored)" };
#define N_EXTRA 2

int palette_count(void) { return N_GRADIENTS + N_EXTRA; }
const char *palette_name(int i) { return i < N_GRADIENTS ? GRADIENTS[i].name : EXTRA_NAMES[i - N_GRADIENTS]; }
const char *palette_description(int i) { return i < N_GRADIENTS ? GRADIENTS[i].desc : EXTRA_DESCS[i - N_GRADIENTS]; }

static Lab catmull_rom(Lab p0, Lab p1, Lab p2, Lab p3, double u) {
    const double u2 = u * u, u3 = u2 * u;
    const double w0 = -0.5 * u3 + u2 - 0.5 * u, w1 = 1.5 * u3 - 2.5 * u2 + 1.0, w2 = -1.5 * u3 + 2.0 * u2 + 0.5 * u,
                 w3 = 0.5 * u3 - 0.5 * u2;
    Lab o = { w0 * p0.L + w1 * p1.L + w2 * p2.L + w3 * p3.L, w0 * p0.a + w1 * p1.a + w2 * p2.a + w3 * p3.a,
              w0 * p0.b + w1 * p1.b + w2 * p2.b + w3 * p3.b };
    return o;
}

static void build_gradient(const Gradient *g, uint32_t *table) {
    Lab lab[MAX_STOPS];
    for (int i = 0; i < g->n; i++)
        lab[i] = rgb_to_lab(g->stops[i]);
    for (int k = 0; k < PALETTE_SIZE; k++) {
        const double s = (double)k * g->n / PALETTE_SIZE;
        const int i = (int)s;
        const double u = s - i;
        table[k] = lab_to_rgb(catmull_rom(lab[(i + g->n - 1) % g->n], lab[i % g->n], lab[(i + 1) % g->n],
                                          lab[(i + 2) % g->n], u));
    }
}

static void build_rainbow(uint32_t *table) {
    for (int k = 0; k < PALETTE_SIZE; k++) {
        const double h = 6.283185307179586 * k / PALETTE_SIZE;
        Lab c = { 0.78, 0.13 * cos(h), 0.13 * sin(h) };
        table[k] = lab_to_rgb(c);
    }
}

/* The original palette, unchanged: 952 colors ramping red -> yellow -> green -> cyan -> blue ->
 * purple -> gray. It does not close on itself, so the loop plays it forwards then backwards. */
static int classic_ramp(uint32_t *pp) {
    uint32_t *start = pp;
    uint8_t current[3] = { 0xC0, 0x03, 0x03 }; /* red, green, blue */
#define PUT() do { *pp++ = ((uint32_t)current[0] << 16) | ((uint32_t)current[1] << 8) | current[2]; } while (0)
    while (current[1]++ < 0xFC) {
        PUT();
        current[1]++;
        current[1]++;
    }
    while (current[0]-- > 0x03) {
        PUT();
        current[0]--;
        current[0]--;
    }
    while (current[2]++ < 0xFC)
        PUT();
    while (current[1]-- > 0x03)
        PUT();
    while (current[0]++ < 0x7F)
        PUT();
    while (1) {
        if (current[0] > 0xE5)
            break;
        current[0]++;
        current[1] += 0x02;
        PUT();
    }
    while (current[0]++ < 0xFC)
        PUT();
    while (current[1]++ < 0xFC)
        PUT();
    for (int i = 0; i < 12; i++) {
        current[0] = current[1] = current[2] = 0xF0;
        PUT();
    }
#undef PUT
    return (int)(pp - start);
}

static void build_classic(uint32_t *table) {
    uint32_t ramp[2048];
    const int n = classic_ramp(ramp);
    for (int k = 0; k < PALETTE_SIZE; k++) {
        const double t = (double)k / PALETTE_SIZE;
        const double u = t < 0.5 ? 2.0 * t : 2.0 - 2.0 * t;   /* 0 -> 1 -> 0 */
        int i = (int)(u * (n - 1) + 0.5);
        table[k] = ramp[i];
    }
}

int palette_build(const char *name, uint32_t *table) {
    for (int i = 0; i < N_GRADIENTS; i++)
        if (!strcmp(name, GRADIENTS[i].name)) {
            build_gradient(&GRADIENTS[i], table);
            return 0;
        }
    if (!strcmp(name, "rainbow")) {
        build_rainbow(table);
        return 0;
    }
    if (!strcmp(name, "classic")) {
        build_classic(table);
        return 0;
    }
    return -1;
}

/* ---- options ----------------------------------------------------------------------------------- */

#define DEFAULT_PALETTE "twilight"

void colorize_defaults(ColorOpts *o) {
    memset(o, 0, sizeof(*o));
    strcpy(o->palette, DEFAULT_PALETTE);
    o->mapping = MAP_HISTOGRAM;
    o->scale = 0.0;
    o->shift = 0.0;
    o->gamma = 1.0;
    o->brightness = 0.0;
    o->contrast = 0.0;
    o->interior = 0x000000;
}

static void fail(char *err, size_t errlen, const char *fmt, const char *a) {
    if (err && errlen)
        snprintf(err, errlen, fmt, a);
}

int colorize_parse_option(ColorOpts *o, const char *arg, char *err, size_t errlen) {
    const char *eq = strchr(arg, '=');
    if (strncmp(arg, "--", 2) || !eq)
        return 0;
    const size_t klen = (size_t)(eq - arg);
    const char *val = eq + 1;
    char *end;
    if (klen == 9 && !strncmp(arg, "--palette", 9)) {
        uint32_t scratch[PALETTE_SIZE];
        if (strlen(val) >= sizeof(o->palette) || palette_build(val, scratch)) {
            fail(err, errlen, "unknown palette '%s' (see colorize --list-palettes)", val);
            return -1;
        }
        strcpy(o->palette, val);
        return 1;
    }
    if (klen == 9 && !strncmp(arg, "--mapping", 9)) {
        if (!strcmp(val, "histogram")) o->mapping = MAP_HISTOGRAM;
        else if (!strcmp(val, "linear")) o->mapping = MAP_LINEAR;
        else if (!strcmp(val, "log")) o->mapping = MAP_LOG;
        else {
            fail(err, errlen, "unknown mapping '%s' (histogram, linear or log)", val);
            return -1;
        }
        return 1;
    }
    if (klen == 7 && !strncmp(arg, "--scale", 7)) {
        const double v = strtod(val, &end);
        if (*val == 0 || *end || !(v >= 0.0) || v > 1e9) {
            fail(err, errlen, "bad --scale value '%s' (a number >= 0; 0 means the mapping's default)", val);
            return -1;
        }
        o->scale = v;
        return 1;
    }
    if (klen == 7 && !strncmp(arg, "--shift", 7)) {
        const double v = strtod(val, &end);
        if (*val == 0 || *end || !(v > -1e9 && v < 1e9)) {
            fail(err, errlen, "bad --shift value '%s' (a number; 1 is a full turn of the palette)", val);
            return -1;
        }
        o->shift = v;
        return 1;
    }
    if (klen == 7 && !strncmp(arg, "--gamma", 7)) {
        const double v = strtod(val, &end);
        if (*val == 0 || *end || !(v >= 0.1 && v <= 10.0)) {
            fail(err, errlen, "bad --gamma value '%s' (a number from 0.1 to 10; 1 changes nothing)", val);
            return -1;
        }
        o->gamma = v;
        return 1;
    }
    if (klen == 12 && !strncmp(arg, "--brightness", 12)) {
        const double v = strtod(val, &end);
        if (*val == 0 || *end || !(v >= -100.0 && v <= 100.0)) {
            fail(err, errlen, "bad --brightness value '%s' (a number from -100 to 100; 0 changes nothing)", val);
            return -1;
        }
        o->brightness = v;
        return 1;
    }
    if (klen == 10 && !strncmp(arg, "--contrast", 10)) {
        const double v = strtod(val, &end);
        if (*val == 0 || *end || !(v >= -100.0 && v <= 100.0)) {
            fail(err, errlen, "bad --contrast value '%s' (a number from -100 to 100; 0 changes nothing)", val);
            return -1;
        }
        o->contrast = v;
        return 1;
    }
    if (klen == 10 && !strncmp(arg, "--interior", 10)) {
        const unsigned long v = strtoul(val, &end, 16);
        if (strlen(val) != 6 || *end || v > 0xFFFFFF) {
            fail(err, errlen, "bad --interior color '%s' (six hex digits, e.g. 000000)", val);
            return -1;
        }
        o->interior = (uint32_t)v;
        return 1;
    }
    return 0;
}

/* ---- nu -> position -> color ------------------------------------------------------------------- */

static int cmp_double(const void *a, const void *b) {
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

void color_positions(const double *nu, size_t n, const ColorOpts *o, double *pos) {
    double scale = o->scale;
    if (o->mapping == MAP_HISTOGRAM) {
        if (scale == 0.0) scale = 2.5;
        double *sorted = (double *)malloc((n ? n : 1) * sizeof(double));
        size_t m = 0;
        if (!sorted) {
            fprintf(stderr, "out of memory\n");
            exit(1);
        }
        for (size_t i = 0; i < n; i++)
            if (nu[i] >= 0.0)
                sorted[m++] = nu[i];
        qsort(sorted, m, sizeof(double), cmp_double);
        for (size_t i = 0; i < n; i++) {
            if (nu[i] < 0.0) {
                pos[i] = -1.0;
                continue;
            }
            size_t lo = 0, hi = m;          /* first element >= nu[i]: equal values share one rank */
            while (lo < hi) {
                const size_t mid = lo + (hi - lo) / 2;
                if (sorted[mid] < nu[i]) lo = mid + 1;
                else hi = mid;
            }
            pos[i] = ((double)lo + 0.5) / (double)m * scale + o->shift;
        }
        free(sorted);
        return;
    }
    if (scale == 0.0) scale = o->mapping == MAP_LINEAR ? 50.0 : 0.6;
    for (size_t i = 0; i < n; i++) {
        if (nu[i] < 0.0)
            pos[i] = -1.0;
        else if (o->mapping == MAP_LINEAR)
            pos[i] = nu[i] / scale + o->shift;
        else
            pos[i] = log2(nu[i] + 1.0) * scale + o->shift;
    }
}

/* Brightness and contrast act on the palette's own colors (not the interior color): each channel c becomes
 * (c - 127.5) * (1 + contrast/100) + 127.5 + brightness * 2.55, rounded and limited to 0..255. */
static void adjust_table(uint32_t *table, const ColorOpts *o) {
    if (o->brightness == 0.0 && o->contrast == 0.0)
        return;
    const double k = 1.0 + o->contrast / 100.0, add = o->brightness * 2.55;
    for (int i = 0; i < PALETTE_SIZE; i++) {
        uint32_t c = 0;
        for (int shift = 0; shift <= 16; shift += 8) {
            const double ch = (double)((table[i] >> shift) & 0xFF);
            double v = floor((ch - 127.5) * k + 127.5 + add + 0.5);
            if (v < 0.0) v = 0.0;
            if (v > 255.0) v = 255.0;
            c |= (uint32_t)v << shift;
        }
        table[i] = c;
    }
}

int colorize_image(const double *nu, int w, int h, const ColorOpts *o, uint32_t *out) {
    uint32_t table[PALETTE_SIZE];
    if (palette_build(o->palette, table))
        return -1;
    adjust_table(table, o);
    const size_t n = (size_t)w * h;
    double *pos = (double *)malloc((n ? n : 1) * sizeof(double));
    if (!pos) {
        fprintf(stderr, "out of memory\n");
        exit(1);
    }
    color_positions(nu, n, o, pos);
    for (size_t i = 0; i < n; i++) {
        if (nu[i] < 0.0) {
            out[i] = o->interior;
            continue;
        }
        double f = pos[i] - floor(pos[i]);
        if (o->gamma != 1.0)
            f = pow(f, o->gamma);
        int k = (int)(f * PALETTE_SIZE);
        if (k >= PALETTE_SIZE) k = PALETTE_SIZE - 1;
        out[i] = table[k];
    }
    free(pos);
    return 0;
}

/* ---- nu files ----------------------------------------------------------------------------------- */

int nu_write(const char *path, const double *nu, uint32_t w, uint32_t h) {
    FILE *fp = fopen(path, "wb");
    if (!fp) {
        perror(path);
        return -1;
    }
    const uint32_t head[3] = { 0x31554e4d /* "MNU1" little-endian */, w, h };
    const size_t n = (size_t)w * h;
    int ok = fwrite(head, sizeof(head[0]), 3, fp) == 3 && fwrite(nu, sizeof(double), n, fp) == n;
    if (fclose(fp) != 0)
        ok = 0;
    if (!ok)
        fprintf(stderr, "error writing %s\n", path);
    return ok ? 0 : -1;
}

double *nu_read(const char *path, uint32_t *w, uint32_t *h) {
    FILE *fp = fopen(path, "rb");
    uint32_t head[3];
    if (!fp) {
        perror(path);
        return NULL;
    }
    if (fread(head, sizeof(head[0]), 3, fp) != 3 || head[0] != 0x31554e4d || head[1] == 0 || head[2] == 0 ||
        (uint64_t)head[1] * head[2] > (1u << 28)) {
        fprintf(stderr, "%s: not a nu file\n", path);
        fclose(fp);
        return NULL;
    }
    const size_t n = (size_t)head[1] * head[2];
    double *nu = (double *)malloc(n * sizeof(double));
    if (!nu || fread(nu, sizeof(double), n, fp) != n) {
        fprintf(stderr, "%s: truncated nu file\n", path);
        free(nu);
        fclose(fp);
        return NULL;
    }
    fclose(fp);
    *w = head[1];
    *h = head[2];
    return nu;
}
