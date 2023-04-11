CFLAGS = -Xptxas -O3 -Xcompiler -O3 -arch=sm_50
CC = nvcc

mand: mand-main.o bmp.o colors.o get-coords.o
	$(CC) $(CFLAGS) -o mand mand-main.o bmp.o colors.o get-coords.o
	strip mand

mand-main.o: mand-main.cu bmp.h colors.h mtypes.h get-coords.h aspect.h
	$(CC) $(CFLAGS) -c mand-main.cu

get-coords.o: get-coords.c mtypes.h
	$(CC) $(CFLAGS) -c get-coords.c

colors.o: colors.c iter.h
	$(CC) $(CFLAGS) -c colors.c 

bmp.o: bmp.c aspect.h
	$(CC) $(CFLAGS) -c bmp.c

clean:
	rm *.o
