# Override for your GPU, e.g.  make ARCH=sm_86   (or override CFLAGS wholesale)
ARCH ?= sm_50
CFLAGS = -Xptxas -O3 -Xcompiler -O3 -arch=$(ARCH)
CC = nvcc

mand: mand-main.o bmp.o colors.o get-coords.o bla.o
	$(CC) $(CFLAGS) -o mand mand-main.o bmp.o colors.o get-coords.o bla.o
	strip mand

mand-main.o: mand-main.cu iter.h bmp.h colors.h mtypes.h get-coords.h aspect.h pert.h bla.h
	$(CC) $(CFLAGS) -c mand-main.cu

get-coords.o: get-coords.c get-coords.h mtypes.h
	$(CC) $(CFLAGS) -c get-coords.c

bla.o: bla.c bla.h pert.h
	$(CC) $(CFLAGS) -c bla.c

colors.o: colors.c colors.h iter.h mtypes.h
	$(CC) $(CFLAGS) -c colors.c

bmp.o: bmp.c bmp.h aspect.h mtypes.h
	$(CC) $(CFLAGS) -c bmp.c

.PHONY: clean
clean:
	rm -f *.o mand
