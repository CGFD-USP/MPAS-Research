#!/usr/bin/env bash
#
# Lean MPAS dependency build: PnetCDF only (+ optional MPICH).
#
# Rationale:
#   MPAS v8 ships its own I/O layer (SMIOL) and uses it automatically whenever
#   the PIO environment variable is unset. In that mode the *only* external I/O
#   dependency is PnetCDF -- no PIO, NetCDF-C, NetCDF-Fortran, HDF5 or zlib.
#   Compilers and MPI should come from the system / HPC module stack whenever
#   possible (HPC sites usually ship MPI tuned for their interconnect). Building
#   MPICH here is therefore OPTIONAL and disabled by default.
#
# Usage:
#   # A) System / module MPI (preferred):
#   #      module load openmpi      # or mpich, whatever the site provides
#   #      bash mpas_lib_install.sh
#   #
#   # B) Build MPICH from the official source (no system MPI available):
#   #      BUILD_MPICH=1 bash mpas_lib_install.sh
#
# All settings below can be overridden from the environment.
#
set -euo pipefail

# ---- configuration -------------------------------------------------
LIBBASE="${MPAS_LIBS:-$HOME/mpas-build/libs}"      # install prefix
SRCDIR="${MPAS_SRC:-$HOME/mpas-build/sources}"     # tarball download/extract dir
BUILD_MPICH="${BUILD_MPICH:-0}"                    # 1 = build MPICH from source
MPICH_VERSION="${MPICH_VERSION:-4.2.3}"            # see https://www.mpich.org/downloads/
PNETCDF_VERSION="${PNETCDF_VERSION:-1.13.0}"       # see https://parallel-netcdf.github.io/
JOBS="${JOBS:-4}"

mkdir -p "$LIBBASE" "$SRCDIR"
export PATH="$LIBBASE/bin:$PATH"
export LD_LIBRARY_PATH="$LIBBASE/lib:${LD_LIBRARY_PATH:-}"

# gfortran >= 10 rejects the legacy mismatched-argument MPI calls by default;
# this downgrades it to a warning so configure tests pass.
export FFLAGS="${FFLAGS:-} -fallow-argument-mismatch"
export FCFLAGS="${FCFLAGS:-} -fallow-argument-mismatch"

# ---- optional: MPICH from the official source ----------------------
if [ "$BUILD_MPICH" = "1" ]; then
    echo "=== Building MPICH ${MPICH_VERSION} (https://www.mpich.org) ==="
    tarball="mpich-${MPICH_VERSION}.tar.gz"
    url="https://www.mpich.org/static/downloads/${MPICH_VERSION}/${tarball}"
    [ -f "$SRCDIR/$tarball" ] || curl -fL -o "$SRCDIR/$tarball" "$url"
    tar xzf "$SRCDIR/$tarball" -C "$SRCDIR"
    pushd "$SRCDIR/mpich-${MPICH_VERSION}" >/dev/null
    ./configure --prefix="$LIBBASE"
    make -j "$JOBS"
    make install
    popd >/dev/null
    rm -rf "$SRCDIR/mpich-${MPICH_VERSION}"
fi

# ---- pick MPI compiler wrappers (system module OR the MPICH above) --
export MPICC="${MPICC:-mpicc}"
export MPICXX="${MPICXX:-mpicxx}"
export MPIF77="${MPIF77:-mpif77}"
export MPIF90="${MPIF90:-mpif90}"
if ! command -v "$MPICC" >/dev/null || ! command -v "$MPIF90" >/dev/null; then
    echo "ERROR: MPI wrappers ($MPICC / $MPIF90) not found on PATH." >&2
    echo "       Load a system MPI module, or re-run with BUILD_MPICH=1." >&2
    exit 1
fi
echo "[INFO] Using MPI: $(command -v "$MPIF90")"

# ---- PnetCDF (the only required external I/O library) --------------
echo "=== Building PnetCDF ${PNETCDF_VERSION} ==="
tarball="pnetcdf-${PNETCDF_VERSION}.tar.gz"
url="https://parallel-netcdf.github.io/Release/${tarball}"
[ -f "$SRCDIR/$tarball" ] || curl -fL -o "$SRCDIR/$tarball" "$url"
tar xzf "$SRCDIR/$tarball" -C "$SRCDIR"
pushd "$SRCDIR/pnetcdf-${PNETCDF_VERSION}" >/dev/null
./configure --prefix="$LIBBASE"          # picks up MPICC/MPIF77/MPIF90/MPICXX from env
make -j "$JOBS"
make install
popd >/dev/null
rm -rf "$SRCDIR/pnetcdf-${PNETCDF_VERSION}"

echo
echo "=== Done. Lean MPAS dependencies installed under: $LIBBASE ==="
echo "Next steps:"
echo "  source \"\$(dirname \"\$0\")/mpas_build_env.sh\""
echo "  cd \"\$MPAS_ROOT\""
echo "  make gnu CORE=init_atmosphere AUTOCLEAN=true   # PIO unset -> bundled SMIOL"
echo "  make gnu CORE=atmosphere      AUTOCLEAN=true"
echo
echo "  (Builds in single precision, the MPAS default since v8.1/8.2 -- fine for"
echo "   most runs. Add PRECISION=double to BOTH cores if your analysis needs it;"
echo "   see README.md.)"
