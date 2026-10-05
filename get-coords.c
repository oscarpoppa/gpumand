#include "mtypes.h"
#include "colorize.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

#define USAGE "Arguments: llreal llimag width filename interleave [reference_orbit_file] [options]\n" \
              "Options: --palette=NAME --mapping=histogram|linear|log --scale=N --shift=N --interior=RRGGBB\n" \
              "         --nu-out=FILE (also save the raw smooth iteration counts for recolouring)\n"

static void usage_error(const char *why, const char *what) {
    if (why)
        fprintf(stderr, "%s%s%s\n", why, what ? ": " : "", what ? what : "");
    fprintf(stderr, USAGE);
    exit(1);
}

RunStart *get_coords(int argc, char *argv[]) {
    RunStart *ret = (RunStart*)calloc(1, sizeof(RunStart));
    const char *pos[8];
    int npos = 0;
    char err[200];
    if (!ret) {
        perror("calloc");
        exit(1);
    }
    colorize_defaults(&ret->color);
    /* "--name=value" options may appear anywhere; everything else is positional */
    for (int i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "--", 2)) {
            if (!strncmp(argv[i], "--nu-out=", 9)) {
                if (strlen(argv[i] + 9) == 0 || strlen(argv[i] + 9) >= sizeof(ret->nuout))
                    usage_error("bad --nu-out file name", NULL);
                strcpy(ret->nuout, argv[i] + 9);
                continue;
            }
            const int r = colorize_parse_option(&ret->color, argv[i], err, sizeof(err));
            if (r < 0)
                usage_error(err, NULL);
            if (r == 0)
                usage_error("unknown option", argv[i]);
        } else if (npos < 8) {
            pos[npos++] = argv[i];
        } else {
            usage_error("too many arguments", NULL);
        }
    }
    if ((npos == 5 || npos == 6) &&
        sscanf(pos[0], "%lf", &ret->lleft.real) == 1 &&
        sscanf(pos[1], "%lf", &ret->lleft.imag) == 1 &&
        sscanf(pos[2], "%lf", &ret->lleft.length) == 1 &&
        sscanf(pos[3], "%255s", ret->filename) == 1 &&
        sscanf(pos[4], "%u", &ret->interleave) == 1 && ret->interleave >= 1 &&
        (npos == 5 || sscanf(pos[5], "%255s", ret->refname) == 1) &&
        /* with a reference orbit the exact pixel step comes from its header, because the
           width itself may be too small for a double and parse as 0 */
        (ret->refname[0] || ret->lleft.length > 0.0)) {
        return ret;
    }
    usage_error(NULL, NULL);
    return NULL;
}
