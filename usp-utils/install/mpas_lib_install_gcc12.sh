#!/usr/bin/env bash

#
# gcc/gfortran-12 variant of mpas_lib_install.sh.
#
# Why: MPAS v8.4 miscompiles with gfortran 13 (the model builds but crashes at
# run time); gfortran 12 is the version the NCAR MPAS tutorial uses and builds a
# working model. This script builds the I/O library stack with gcc/gfortran 12
# from a conda env, into a SEPARATE prefix (libs-gcc12) so a gfortran-13 build in
# ../libs is preserved.
#
# Prerequisites: a conda env that provides gcc/gfortran 12, e.g.
#   conda create -n mpas-gcc12 -c conda-forge 'gfortran=12' 'gcc=12' 'gxx=12'
#   conda activate mpas-gcc12
#
# This is a versioned TEMPLATE with placeholder paths — do not edit in place.
# Copy it to a personal *.local.sh (git-ignored) and edit LIBSRC/LIBBASE there:
#   cp install/mpas_lib_install_gcc12.sh install/mpas_lib_install_gcc12.local.sh
#
# Sources for all libraries used in this script can be found at
# http://www2.mmm.ucar.edu/people/duda/files/mpas/sources/
#

# Where to find sources for libraries - generally, the directory into which
# you have downloaded the sources from the URL, above
export LIBSRC=$HOME/mpas-build/sources

# Where to install libraries - this directory must be writable by you
# (separate prefix so a gfortran-13 build in ../libs is preserved)
export LIBBASE=$HOME/mpas-build/libs-gcc12

# Compilers — gcc/gfortran 12 from the active conda env (e.g. 'mpas-gcc12').
# These are the conda-forge compiler wrapper names; activate the env first.
export SERIAL_FC=x86_64-conda-linux-gnu-gfortran
export SERIAL_F77=x86_64-conda-linux-gnu-gfortran
export SERIAL_CC=x86_64-conda-linux-gnu-gcc
export SERIAL_CXX=x86_64-conda-linux-gnu-g++
export MPI_FC=mpifort
export MPI_F77=mpifort
export MPI_CC=mpicc
export MPI_CXX=mpic++


export CC=$SERIAL_CC
export CXX=$SERIAL_CXX
export F77=$SERIAL_F77
export FC=$SERIAL_FC
unset F90  # This seems to be set by default on NCAR's Cheyenne and is problematic
unset F90FLAGS
export CFLAGS="-g"
# gfortran >= 10 (incl. 12) needs -fallow-argument-mismatch in FFLAGS for MPICH 3.3.1
export FFLAGS="-g -fbacktrace -fallow-argument-mismatch"
export FCFLAGS="-g -fbacktrace -fallow-argument-mismatch"
export F77FLAGS="-g -fbacktrace -fallow-argument-mismatch"


########################################
# MPICH
########################################
tar xzvf ${LIBSRC}/mpich-3.3.1.tar.gz
cd mpich-3.3.1
./configure --prefix=${LIBBASE}
make -j 4
#make check
make install
#make testing
export PATH=${LIBBASE}/bin:$PATH
export LD_LIBRARY_PATH=${LIBBASE}/lib:$LD_LIBRARY_PATH
cd ..
rm -rf mpich-3.3.1

########################################
# zlib
########################################
tar xzvf ${LIBSRC}/zlib-1.2.11.tar.gz
cd zlib-1.2.11
./configure --prefix=${LIBBASE} --static
make -j 4
make install
cd ..
rm -rf zlib-1.2.11

########################################
# HDF5
########################################
tar xjvf ${LIBSRC}/hdf5-1.10.5.tar.bz2
cd hdf5-1.10.5
export FC=$MPI_FC
export CC=$MPI_CC
export CXX=$MPI_CXX
./configure --prefix=${LIBBASE} --enable-parallel --with-zlib=${LIBBASE} --disable-shared
make -j 4
#make check
make install
cd ..
rm -rf hdf5-1.10.5

########################################
# Parallel-netCDF
########################################
tar xzvf ${LIBSRC}/pnetcdf-1.12.2.tar.gz
cd pnetcdf-1.12.2
export CC=$SERIAL_CC
export CXX=$SERIAL_CXX
export F77=$SERIAL_F77
export FC=$SERIAL_FC
export MPICC=$MPI_CC
export MPICXX=$MPI_CXX
export MPIF77=$MPI_F77
export MPIF90=$MPI_FC
### Will also need gcc in path
./configure --prefix=${LIBBASE}
make -j 4
#make check
#make ptest
#make testing
make install
export PNETCDF=${LIBBASE}
cd ..
rm -rf pnetcdf-1.12.2

########################################
# netCDF (C library)
########################################
tar xzvf ${LIBSRC}/netcdf-c-4.6.3.tar.gz
cd netcdf-c-4.6.3
export CPPFLAGS="-I${LIBBASE}/include"
export LDFLAGS="-L${LIBBASE}/lib"
export LIBS="-lhdf5_hl -lhdf5 -lz -ldl"
export CC=$MPI_CC
./configure --prefix=${LIBBASE} --disable-dap --enable-netcdf4 --enable-pnetcdf --enable-cdf5 --enable-parallel-tests --disable-shared
make -j 4
#make check
make install
export NETCDF=${LIBBASE}
cd ..
rm -rf netcdf-c-4.6.3

########################################
# netCDF (Fortran interface library)
########################################
tar xzvf ${LIBSRC}/netcdf-fortran-4.5.2.tar.gz
cd netcdf-fortran-4.5.2
export FC=$MPI_FC
export F77=$MPI_F77
export LIBS="-lnetcdf -lpnetcdf ${LIBS}"
./configure --prefix=${LIBBASE} --enable-parallel-tests --disable-shared
make -j 4
#make check
make install
cd ..
rm -rf netcdf-fortran-4.5.2

########################################
# PIO
########################################
git clone https://github.com/NCAR/ParallelIO
cd ParallelIO
git checkout -b pio-2.5.8 pio2_5_8
export PIOSRC=`pwd`
cd ..
mkdir pio
cd pio
export CC=$MPI_CC
export FC=$MPI_FC
cmake -DNetCDF_C_PATH=$NETCDF -DNetCDF_Fortran_PATH=$NETCDF -DPnetCDF_PATH=$PNETCDF -DHDF5_PATH=$NETCDF -DCMAKE_INSTALL_PREFIX=$LIBBASE -DPIO_USE_MALLOC=ON -DCMAKE_VERBOSE_MAKEFILE=1 -DPIO_ENABLE_TIMING=OFF $PIOSRC
make
#make check
make install
cd ..
rm -rf pio ParallelIO
export PIO=$LIBBASE

########################################
# Other environment vars needed by MPAS
########################################
export MPAS_EXTERNAL_LIBS="-L${LIBBASE}/lib -lhdf5_hl -lhdf5 -ldl -lz"
export MPAS_EXTERNAL_INCLUDES="-I${LIBBASE}/include"
