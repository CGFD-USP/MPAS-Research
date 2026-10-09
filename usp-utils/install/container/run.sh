#!/usr/bin/env bash
# Runs a command in the MPAS image, e.g. bash run.sh bash, bash run.sh make gnu
# CORE=atmosphere, bash run.sh mpirun -n 8 ./atmosphere_model.
# Binds the MPAS-Research tree and the existing folders of $MPAS_BIND (colon
# separated), and sets MPAS_ROOT and PYTHONPATH as setup_environment.sh does.
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
exec "$apptainer" exec "${binds[@]}" \
  --env MPAS_ROOT="$repo" \
  --env PYTHONPATH="$repo/usp-utils/libs/py${PYTHONPATH:+:$PYTHONPATH}" \
  "$sif" "$@"
