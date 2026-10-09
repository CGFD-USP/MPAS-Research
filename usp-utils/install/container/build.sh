#!/usr/bin/env bash
# Builds the MPAS image, by default <MPAS-Research>/.apptainer/mpas.sif. The
# build context holds libs/cgfd-usp-mpas.yml and install/install_julia_environment.jl,
# so the image has the Python and Julia environments of a native install.
# Apptainer: $APPTAINER, else apptainer or singularity on PATH.
# Usage: bash build.sh [image]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
utils=$(dirname "$(dirname "$here")")
repo=$(dirname "$utils")
sif=${1:-$repo/.apptainer/mpas.sif}
apptainer=${APPTAINER:-$(command -v apptainer || command -v singularity || true)}
[ -n "$apptainer" ] || { echo "apptainer not found, set APPTAINER to its path" >&2; exit 1; }

ctx=$(mktemp -d "${TMPDIR:-/tmp}/mpas_image.XXXXXX")
trap 'rm -rf "$ctx"' EXIT
cp "$here/mpas.def" "$here/precompile_julia.jl" "$utils/libs/cgfd-usp-mpas.yml" \
  "$utils/install/install_julia_environment.jl" "$ctx/"

mkdir -p "$(dirname "$sif")"
rm -f "$sif.part"
cd "$ctx"
"$apptainer" build "$sif.part" mpas.def
mv "$sif.part" "$sif"
echo "built $sif"
