#!/usr/bin/env bash
#
# Build environment for compiling MPAS against the lean dependency set built by
# mpas_lib_install.sh (PnetCDF only). Source this before running `make`:
#
#   source usp-utils/install/mpas_build_env.sh
#   cd /path/to/MPAS-Research   # repo root (folder with top-level Makefile)
#   make gnu CORE=init_atmosphere AUTOCLEAN=true
#   make gnu CORE=atmosphere      AUTOCLEAN=true
#
# That builds in single precision, the MPAS default since v8.1/8.2 -- faster,
# lighter, and fine for most runs. Add PRECISION=double to BOTH cores if your
# analysis relies on small residuals of large terms (energy budgets, energetics
# diagnostics); see README.md for the trade-off.
#
# No PIO / NetCDF / HDF5: with PIO unset, MPAS v8 links its bundled SMIOL I/O
# layer and only needs PnetCDF. MPI + compilers should come from the system /
# HPC module stack; set MPI_HOME only if you built MPICH yourself.
#
# `make gnu` and `make gfortran` differ only in two compile-time diagnostic
# flags in the gnu recipe (-std=f2008 -fimplicit-none); the produced binaries
# are numerically identical. `make gnu` is the stricter (recommended) target.

# --- configuration (override via environment before sourcing) -------
: "${MPAS_LIBS:=$HOME/mpas-build/libs}"   # prefix where PnetCDF was installed
: "${MPI_HOME:=}"                         # set ONLY for a self-built / non-system MPI

# Self-built MPICH installed into $MPAS_LIBS, or a separate $MPI_HOME, on PATH.
# For a system/module MPI: leave MPI_HOME empty and `module load` it beforehand.
export PATH="$MPAS_LIBS/bin:$PATH"

if [ -n "$MPI_HOME" ]; then
    export PATH="$MPI_HOME/bin:$PATH"
    if [ -n "${LD_LIBRARY_PATH:-}" ]; then
        export LD_LIBRARY_PATH="$MPI_HOME/lib:$LD_LIBRARY_PATH"
    else
        export LD_LIBRARY_PATH="$MPI_HOME/lib"
    fi
fi

export PNETCDF="$MPAS_LIBS"
unset PIO NETCDF                          # -> SMIOL path, no stray NetCDF linkage

if [ -n "${LD_LIBRARY_PATH:-}" ]; then
    export LD_LIBRARY_PATH="$MPAS_LIBS/lib:$LD_LIBRARY_PATH"
else
    export LD_LIBRARY_PATH="$MPAS_LIBS/lib"
fi

echo "[INFO] MPAS lean env: PNETCDF=$PNETCDF  (PIO/NETCDF unset -> SMIOL I/O)"
echo "[INFO] mpif90 -> $(command -v mpif90 || echo 'NOT FOUND - load a system MPI or set MPI_HOME')"
