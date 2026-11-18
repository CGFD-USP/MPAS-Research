#!/usr/bin/env bash
# Runs a command in the MPAS image, e.g. bash run.sh bash, bash run.sh make gnu
# CORE=atmosphere, bash run.sh mpirun -n 8 ./atmosphere_model.
# Binds the MPAS-Research tree and the existing folders of $MPAS_BIND (colon
# separated), sets MPAS_ROOT and PYTHONPATH as setup_environment.sh does, puts
# the writable Julia depot $MPAS_JULIA_DEPOT (default ~/.julia-mpas) ahead of
# the image's one, and hides the variables named in $MPAS_HIDE_ENV (space
# separated) from the image.
# Image: $MPAS_SIF, default <MPAS-Research>/.apptainer/mpas.sif.
# Apptainer: $APPTAINER, else apptainer or singularity on PATH.
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$here/../../.." && pwd)
sif=${MPAS_SIF:-$repo/.apptainer/mpas.sif}
[ -f "$sif" ] || { echo "no image at $sif, build it with bash $here/build.sh" >&2; exit 1; }
apptainer=${APPTAINER:-$(command -v apptainer || command -v singularity || true)}
[ -n "$apptainer" ] || { echo "apptainer not found, set APPTAINER to its path" >&2; exit 1; }

binds=(--bind "$repo")
IFS=: read -r -a extra <<< "${MPAS_BIND:-}"
for p in "${extra[@]}"; do
  [ -n "$p" ] && [ -d "$p" ] && binds+=(--bind "$p")
done
hide=()
for v in ${MPAS_HIDE_ENV:-}; do
  hide+=(-u "$v")
done
exec env "${hide[@]}" "$apptainer" exec "${binds[@]}" \
  --env MPAS_ROOT="$repo" \
  --env JULIA_DEPOT_PATH="${MPAS_JULIA_DEPOT:-$HOME/.julia-mpas}:/opt/julia-depot:" \
  --env PYTHONPATH="$repo/usp-utils/libs/py${PYTHONPATH:+:$PYTHONPATH}" \
  "$sif" "$@"
