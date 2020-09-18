mand: mand_main_kern.o bmp.o colors.o get_coords.o
	nvcc -arch=sm_50 -o mand mand_main_kern.o bmp.o colors.o get_coords.o

mand_gui.py:
	co -l mand_gui.py

mand_main_kern.o: mand_main_kern.cu bmp.h colors.h mtypes.h get_coords.h aspect.h
	nvcc -arch=sm_50 -c mand_main_kern.cu

get_coords.o: get_coords.c mtypes.h
	nvcc -arch=sm_50 -c get_coords.c

colors.o: colors.c
	nvcc -arch=sm_50 -c colors.c 

bmp.o: bmp.c aspect.h
	nvcc -arch=sm_50 -c bmp.c

colors.c: 
	co -l colors.c

get_coords.c: 
	co -l get_coords.c

bmp.c: 
	co -l bmp.c

mand_main_kern.cu:
	co -l mand_main_kern.cu

colors.h:
	co -l colors.h

mtypes.h:
	co -l mtypes.h

aspect.h:
	co -l aspect.h

bmp.h:
	co -l bmp.h

get_coords.h: mtypes.h
	co -l get_coords.h

clean:
	rm *.o
