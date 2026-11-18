#!/usr/bin/env bash
# Prepares this machine for the MPAS tools from its profile (env.sh): checks
# apptainer, creates the data and build roots, builds the image when missing,
# and points the Julia environment of the image at the checkouts of
# <MPAS-Research>/external when there are any. Safe to run again.
# Usage: bash usp-utils/machines/setup.sh
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/env.sh"
container=$MPAS_ROOT/usp-utils/install/container
sif=${MPAS_SIF:-$MPAS_ROOT/.apptainer/mpas.sif}

echo "machine $MPAS_MACHINE, MPAS-Research $MPAS_ROOT"
"$APPTAINER" --version >/dev/null || { echo "apptainer not usable: $APPTAINER" >&2; exit 1; }
mkdir -p "$MPAS_DATA_ROOT" "$MPAS_BUILD_ROOT"
echo "data root $MPAS_DATA_ROOT, build root $MPAS_BUILD_ROOT"

if [ -f "$sif" ]; then
  echo "image $sif"
else
  bash "$container/build.sh" "$sif"
fi

if ls "$MPAS_ROOT"/external/*/Project.toml >/dev/null 2>&1; then
  echo "Julia packages from $MPAS_ROOT/external"
  MPAS_SIF=$sif bash "$container/run.sh" julia --startup-file=no \
    "$MPAS_ROOT/usp-utils/install/develop_julia_packages.jl" "$MPAS_ROOT/external"
fi
echo "done"
