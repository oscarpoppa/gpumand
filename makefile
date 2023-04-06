CFLAGS = -Xptxas -O3 -Xcompiler -O3 -arch=sm_50
CC = nvcc

mand: mand_main_retry.o bmp.o colors.o get_coords.o
	$(CC) $(CFLAGS) -o mand mand_main_retry.o bmp.o colors.o get_coords.o
	strip mand

mand_main_retry.o: mand_main_retry.cu bmp.h colors.h mtypes.h get_coords.h aspect.h
	$(CC) $(CFLAGS) -c mand_main_retry.cu

get_coords.o: get_coords.c mtypes.h
	$(CC) $(CFLAGS) -c get_coords.c

colors.o: colors.c
	$(CC) $(CFLAGS) -c colors.c 

bmp.o: bmp.c aspect.h
	$(CC) $(CFLAGS) -c bmp.c

clean:
	rm *.o
