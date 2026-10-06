/*
 * colorize: recolor raw smooth-iteration-count files (written by `mand-gpu --nu-out=`) without rendering.
 *
 *   colorize IN.nu OUT.bmp [--palette=NAME] [--mapping=...] [--scale=N] [--shift=N]
 *                          [--gamma=N] [--brightness=N] [--contrast=N] [--interior=RRGGBB]
 *   colorize --list-palettes
 *   colorize --dump-palette=NAME      one 0xRRGGBB entry per line (PALETTE_SIZE lines)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "colorize.h"
#include "bmp.h"

int main(int argc, char **argv) {
    ColorOpts opts;
    char err[200];
    const char *files[2];
    int nfiles = 0;
    colorize_defaults(&opts);
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--list-palettes")) {
            for (int p = 0; p < palette_count(); p++)
                printf("%-9s %s\n", palette_name(p), palette_description(p));
            return 0;
        }
        if (!strncmp(argv[i], "--dump-palette=", 15)) {
            uint32_t table[PALETTE_SIZE];
            if (palette_build(argv[i] + 15, table)) {
                fprintf(stderr, "unknown palette '%s'\n", argv[i] + 15);
                return 1;
            }
            for (int k = 0; k < PALETTE_SIZE; k++)
                printf("%06x\n", table[k]);
            return 0;
        }
        const int r = colorize_parse_option(&opts, argv[i], err, sizeof(err));
        if (r < 0) {
            fprintf(stderr, "%s\n", err);
            return 1;
        }
        if (r == 0) {
            if (!strncmp(argv[i], "--", 2) || nfiles == 2) {
                fprintf(stderr, "unexpected argument: %s\n", argv[i]);
                return 1;
            }
            files[nfiles++] = argv[i];
        }
    }
    if (nfiles != 2) {
        fprintf(stderr, "usage: colorize IN.nu OUT.bmp [--palette=NAME] [--mapping=histogram|linear|log]\n"
                        "                [--scale=N] [--shift=N] [--gamma=N] [--brightness=N] [--contrast=N]\n"
                        "                [--interior=RRGGBB]\n"
                        "       colorize --list-palettes | --dump-palette=NAME\n");
        return 1;
    }
    uint32_t w, h;
    double *nu = nu_read(files[0], &w, &h);
    if (!nu)
        return 1;
    uint32_t *pix = (uint32_t*)malloc((size_t)w * h * sizeof(uint32_t));
    if (!pix) {
        perror("malloc");
        return 1;
    }
    if (colorize_image(nu, (int)w, (int)h, &opts, pix)) {
        fprintf(stderr, "unknown palette '%s'\n", opts.palette);
        return 1;
    }
    const int rc = gen_bmp(files[1], pix, w, h);
    free(pix);
    free(nu);
    return rc ? 1 : 0;
}
