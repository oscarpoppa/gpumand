#$Id: makefile,v 1.1 2017/12/22 18:35:18 dan Exp $
CFLAGS = -Xptxas -O3 -Xcompiler -O3 -arch=sm_50
CC = nvcc

mand: mand_main_retry.o bmp.o colors.o get_coords.o
	$(CC) $(CFLAGS) -o mand mand_main_retry.o bmp.o colors.o get_coords.o
	strip mand

mand_gui.py:
	#co -l mand_gui.py

mand_main_retry.o: mand_main_retry.cu bmp.h colors.h mtypes.h get_coords.h aspect.h
	$(CC) $(CFLAGS) -c mand_main_retry.cu

get_coords.o: get_coords.c mtypes.h
	$(CC) $(CFLAGS) -c get_coords.c

colors.o: colors.c
	$(CC) $(CFLAGS) -c colors.c 

bmp.o: bmp.c aspect.h
	$(CC) $(CFLAGS) -c bmp.c

colors.c: 
	#co -l colors.c

get_coords.c: 
	#co -l get_coords.c

bmp.c: 
	#co -l bmp.c

mand_main_retry.cu:
	#co -l mand_main_retry.cu

colors.h:
	#co -l colors.h

mtypes.h:
	#co -l mtypes.h

align.h:
	#co -l align.h

aspect.h:
	#co -l aspect.h

bmp.h:
	#co -l bmp.h

get_coords.h: mtypes.h
	#co -l get_coords.h

clean:
	rm *.o
