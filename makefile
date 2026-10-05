# `make` builds the CUDA renderer (mand) and the color tool; `make cpu` is the no-GPU build: the CPU
# renderer (mand-cpu) and the color tool, which the GUI also uses to recolor images.
# Override for your GPU, e.g.  make ARCH=sm_86   (or override CFLAGS wholesale)
ARCH ?= sm_50
CFLAGS = -Xptxas -O3 -Xcompiler -O3 -arch=$(ARCH)
CC = nvcc

.PHONY: all cpu
all: mand colorize

# No GPU (or no CUDA): everything the GUI needs with renderer=mand-cpu
cpu: mand-cpu colorize

mand: mand-main.o bmp.o colorize.o get-coords.o bla.o refio.o
	$(CC) $(CFLAGS) -o mand mand-main.o bmp.o colorize.o get-coords.o bla.o refio.o
	strip mand

mand-main.o: mand-main.cu iter.h bmp.h colorize.h mtypes.h get-coords.h aspect.h pert.h bla.h refio.h
	$(CC) $(CFLAGS) -c mand-main.cu

get-coords.o: get-coords.c get-coords.h colorize.h mtypes.h
	$(CC) $(CFLAGS) -c get-coords.c

bla.o: bla.c bla.h pert.h
	$(CC) $(CFLAGS) -c bla.c

refio.o: refio.c refio.h pert.h
	$(CC) $(CFLAGS) -c refio.c

colorize.o: colorize.c colorize.h mtypes.h
	$(CC) $(CFLAGS) -c colorize.c

bmp.o: bmp.c bmp.h aspect.h mtypes.h
	$(CC) $(CFLAGS) -c bmp.c

# CPU-only renderer: same arguments and output as mand, no GPU or nvcc needed.
# Build with `make mand-cpu` (threads: OMP_NUM_THREADS). -ffp-contract=off keeps results
# identical across CPUs regardless of CPUFLAGS.
CPUCC ?= gcc
CPUFLAGS ?= -O3
CPUSRC = mand-cpu.c colorize.c bmp.c get-coords.c bla.c refio.c
CPUHDR = colorize.h bmp.h get-coords.h bla.h refio.h pert.h mtypes.h iter.h aspect.h

mand-cpu: $(CPUSRC) $(CPUHDR)
	$(CPUCC) $(CPUFLAGS) -std=gnu99 -ffp-contract=off -fopenmp -Wall -Wextra -o mand-cpu $(CPUSRC) -lm

# Recolors saved smooth-iteration-count files (mand --nu-out=FILE) without rendering again.
colorize: colorize-main.c colorize.c bmp.c $(CPUHDR)
	$(CPUCC) $(CPUFLAGS) -std=gnu99 -Wall -Wextra -o colorize colorize-main.c colorize.c bmp.c -lm

.PHONY: clean
clean:
	rm -f *.o mand mand-cpu colorize
