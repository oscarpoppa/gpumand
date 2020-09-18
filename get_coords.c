//$Id: get_coords.c,v 1.5 2017/12/06 20:51:29 dan Exp $
#include "mtypes.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

RunStart *get_coords(int argc, char *argv[]) {
    RunStart *ret = (RunStart*)malloc(sizeof(RunStart));
    switch (argc) {
        case 6:
            sscanf(argv[1], "%lf", &ret->lleft.real);
            sscanf(argv[2], "%lf", &ret->lleft.imag);
            sscanf(argv[3], "%lf", &ret->lleft.length);
            sscanf(argv[4], "%s", ret->filename);
            sscanf(argv[5], "%d", &ret->interleave);
            break;
        default:
            fprintf(stderr, "Arguments: llreal llimag log_edge filename interleave\n");
            exit(0);
    };  
    strcat(ret->filename, ".bmp");
    return ret;
}
