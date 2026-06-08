#!/usr/bin/env bash
#
# download_mpas_lib_sources.sh
#
# Download the source tarballs required by the NCAR MPAS library build
# (mpas_lib_install.sh). Versions here MUST match the ones expanded by that
# script, otherwise the `cd <dir>` steps will fail.
#
# Most sources come from the NCAR/MMM mirror used by the MPAS-Atmosphere
# tutorial (http://www2.mmm.ucar.edu/people/duda/files/mpas/sources/). The
# PnetCDF tarball is not on that mirror, so it is fetched from the official
# Parallel-netCDF release site.
#
# PIO is NOT downloaded here: mpas_lib_install.sh clones NCAR/ParallelIO
# (tag pio2_5_8) directly. Pass --with-pio to also stage that clone locally.
#
# Usage:
#   ./download_mpas_lib_sources.sh [LIBSRC_DIR] [--with-pio]
#
#   LIBSRC_DIR  Directory to download into (default: $HOME/mpas-build/sources,
#               or the LIBSRC env var if set). Point mpas_lib_install.sh's
#               LIBSRC variable at this same directory.
#
# The script is idempotent: a file that already exists and passes its archive
# integrity check is skipped (so it doubles as a resume/verify tool).

set -uo pipefail

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
INFO="${CYAN}[INFO]${NC}"; WARN="${YELLOW}[WARN]${NC}"; ERR="${RED}[ERROR]${NC}"; OK="${GREEN}[OK]${NC}"

# --- Argument parsing ---------------------------------------------------------
CLONE_PIO=0
LIBSRC="${LIBSRC:-$HOME/mpas-build/sources}"
for arg in "$@"; do
    case "$arg" in
        --with-pio) CLONE_PIO=1 ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
        *)          LIBSRC="$arg" ;;
    esac
done

NCAR="https://www2.mmm.ucar.edu/people/duda/files/mpas/sources"
PNETCDF_SRC="https://parallel-netcdf.github.io/Release"

# filename|download_url  (versions must match mpas_lib_install.sh)
FILES=(
    "mpich-3.3.1.tar.gz|${NCAR}/mpich-3.3.1.tar.gz"
    "zlib-1.2.11.tar.gz|${NCAR}/zlib-1.2.11.tar.gz"
    "hdf5-1.10.5.tar.bz2|${NCAR}/hdf5-1.10.5.tar.bz2"
    "pnetcdf-1.12.2.tar.gz|${PNETCDF_SRC}/pnetcdf-1.12.2.tar.gz"
    "netcdf-c-4.6.3.tar.gz|${NCAR}/netcdf-c-4.6.3.tar.gz"
    "netcdf-fortran-4.5.2.tar.gz|${NCAR}/netcdf-fortran-4.5.2.tar.gz"
)

# --- Helpers ------------------------------------------------------------------
# Verify a downloaded archive is not truncated/corrupt.
verify_archive() {
    local f="$1"
    case "$f" in
        *.tar.gz)  gzip  -t "$f" 2>/dev/null ;;
        *.tar.bz2) bzip2 -t "$f" 2>/dev/null ;;
        *)         return 0 ;;
    esac
}

# --- Download -----------------------------------------------------------------
mkdir -p "$LIBSRC"
echo -e "${INFO} Downloading MPAS library sources into: ${LIBSRC}"
echo -e "${INFO} (set LIBSRC=${LIBSRC} in mpas_lib_install.sh)"

failures=0
for entry in "${FILES[@]}"; do
    fname="${entry%%|*}"
    url="${entry#*|}"
    dest="${LIBSRC}/${fname}"

    if [ -f "$dest" ] && verify_archive "$dest"; then
        echo -e "${OK} ${fname} already present and valid — skipping"
        continue
    fi

    echo -e "${INFO} Fetching ${fname}"
    # -L follow redirects, -f fail on HTTP error, -C - resume, --retry transient errors
    if ! curl -fL -C - --retry 3 --retry-delay 5 -o "$dest" "$url"; then
        echo -e "${ERR} Download failed: ${fname} (${url})"
        rm -f "$dest"
        failures=$((failures+1))
        continue
    fi

    if ! verify_archive "$dest"; then
        echo -e "${ERR} Integrity check failed (corrupt/truncated): ${fname}"
        rm -f "$dest"
        failures=$((failures+1))
        continue
    fi
    echo -e "${OK} ${fname}"
done

# --- Optional: stage ParallelIO (PIO) -----------------------------------------
if [ "$CLONE_PIO" -eq 1 ]; then
    echo -e "${INFO} Staging ParallelIO (tag pio2_5_8)"
    if [ -d "${LIBSRC}/ParallelIO" ]; then
        echo -e "${OK} ParallelIO clone already present — skipping"
    elif git clone --quiet https://github.com/NCAR/ParallelIO "${LIBSRC}/ParallelIO" \
         && git -C "${LIBSRC}/ParallelIO" checkout --quiet -b pio-2.5.8 pio2_5_8; then
        echo -e "${OK} ParallelIO @ pio2_5_8"
    else
        echo -e "${ERR} Failed to clone/checkout ParallelIO"
        failures=$((failures+1))
    fi
fi

# --- Provenance manifest (sha256) ---------------------------------------------
echo -e "${INFO} Recording checksums in ${LIBSRC}/SHA256SUMS"
( cd "$LIBSRC" && sha256sum *.tar.gz *.tar.bz2 2>/dev/null > SHA256SUMS )

echo ""
if [ "$failures" -eq 0 ]; then
    echo -e "${OK} All sources downloaded and verified in ${LIBSRC}"
    echo -e "${INFO} Next: edit mpas_lib_install.sh (set LIBSRC and a writable LIBBASE), then run it."
    exit 0
else
    echo -e "${ERR} ${failures} download(s) failed — see messages above."
    exit 1
fi
