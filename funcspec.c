#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "iter.h"
#include "funcspec.h"

#define MAX_LINES 32        /* a function file is a handful of short lines */

static int fail(char *err, size_t errlen, const char *path, int line, const char *what) {
    if (err && errlen) {
        if (line > 0)
            snprintf(err, errlen, "%s, line %d: %s", path, line, what);
        else
            snprintf(err, errlen, "%s: %s", path, what);
    }
    return -1;
}

int funcspec_load(const char *path, FuncSpec *f, char *err, size_t errlen) {
    FILE *fp = fopen(path, "r");
    char line[256];
    int lineno = 0, have_kind = 0, have_degree = 0;
    FuncSpec out = { FUNC_MANDELBROT, 0 };
    if (!fp)
        return fail(err, errlen, path, 0, "cannot open the function file");
    while (fgets(line, sizeof(line), fp)) {
        char key[32], val[64];
        int used = 0;
        size_t len = strlen(line);
        lineno++;
        if (lineno > MAX_LINES) {
            fclose(fp);
            return fail(err, errlen, path, 0, "too many lines for a function file");
        }
        if (len > 0 && line[len - 1] == '\n') {
            line[--len] = 0;
        } else if (!feof(fp)) {
            fclose(fp);
            return fail(err, errlen, path, lineno, "line too long");
        }
        if (len > 0 && line[len - 1] == '\r')
            line[--len] = 0;
        if (lineno == 1) {
            if (strcmp(line, "gpumand-func 1")) {
                fclose(fp);
                return fail(err, errlen, path, 1, "not a function file (the first line must be \"gpumand-func 1\")");
            }
            continue;
        }
        if (len == 0)
            continue;
        if (sscanf(line, "%31s %63s %n", key, val, &used) < 2 || line[used] != 0) {
            fclose(fp);
            return fail(err, errlen, path, lineno, "expected \"key value\"");
        }
        if (!strcmp(key, "kind")) {
            if (have_kind) {
                fclose(fp);
                return fail(err, errlen, path, lineno, "kind appears twice");
            }
            if (strcmp(val, "power")) {
                fclose(fp);
                return fail(err, errlen, path, lineno, "unknown kind (only \"power\" is supported)");
            }
            out.kind = FUNC_POWER;
            have_kind = 1;
        } else if (!strcmp(key, "degree")) {
            char *end;
            long d;
            if (have_degree) {
                fclose(fp);
                return fail(err, errlen, path, lineno, "degree appears twice");
            }
            d = strtol(val, &end, 10);
            if (*val == 0 || *end || d < POWER_MIN_DEGREE || d > POWER_MAX_DEGREE) {
                char what[96];
                snprintf(what, sizeof(what), "degree must be a whole number from %d to %d", POWER_MIN_DEGREE, POWER_MAX_DEGREE);
                fclose(fp);
                return fail(err, errlen, path, lineno, what);
            }
            out.degree = (int)d;
            have_degree = 1;
        } else {
            fclose(fp);
            return fail(err, errlen, path, lineno, "unknown key");
        }
    }
    fclose(fp);
    if (lineno == 0)
        return fail(err, errlen, path, 0, "empty file");
    if (!have_kind)
        return fail(err, errlen, path, 0, "no kind line");
    if (!have_degree)
        return fail(err, errlen, path, 0, "no degree line");
    *f = out;
    return 0;
}
