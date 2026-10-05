#include "mtypes.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

RunStart *get_coords(int argc, char *argv[]) {
    RunStart *ret = (RunStart*)calloc(1, sizeof(RunStart));
    if (!ret) {
        perror("calloc");
        exit(1);
    }
    if ((argc == 6 || argc == 7) &&
        sscanf(argv[1], "%lf", &ret->lleft.real) == 1 &&
        sscanf(argv[2], "%lf", &ret->lleft.imag) == 1 &&
        sscanf(argv[3], "%lf", &ret->lleft.length) == 1 &&
        sscanf(argv[4], "%255s", ret->filename) == 1 &&
        sscanf(argv[5], "%u", &ret->interleave) == 1 && ret->interleave >= 1 &&
        (argc == 6 || sscanf(argv[6], "%255s", ret->refname) == 1) &&
        /* with a reference orbit the exact pixel step comes from its header, because the
           width itself may be too small for a double and parse as 0 */
        (ret->refname[0] || ret->lleft.length > 0.0)) {
        return ret;
    }
    fprintf(stderr, "Arguments: llreal llimag width filename interleave [reference_orbit_file]\n");
    exit(1);
}
