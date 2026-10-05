#include <stdio.h>
#include <stdlib.h>
#include "refio.h"

Cd *load_ref(const char *path, RefHeader *h) {
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        perror(path);
        exit(1);
    }
    if (fread(h, sizeof(*h), 1, fp) != 1 || h->count < 2 || h->count > MAX_REF_POINTS || h->step_mant <= 0.0) {
        fprintf(stderr, "Bad reference orbit header: %s\n", path);
        exit(1);
    }
    Cd *buf = (Cd*)malloc(h->count * sizeof(Cd));
    if (!buf || fread(buf, sizeof(Cd), h->count, fp) != h->count) {
        fprintf(stderr, "Bad reference orbit data: %s\n", path);
        exit(1);
    }
    fclose(fp);
    return buf;
}
