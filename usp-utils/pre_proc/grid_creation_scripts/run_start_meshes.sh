#!/usr/bin/env bash
# Tropical meshes from the starting point sets (--start rings, icos, geo) at 480-120 to 60-15 km into
# $OUT/tropical-<coarse>-<fine>km-<start>/, JOBS at a time with one JIGSAW thread each, optm_qtol 1e-3 as the
# frontal-Delaunay family (a).
# Usage (on the host, MPAS image through run.sh): bash run_start_meshes.sh [OUT] [JOBS] [FINE km list]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
OUT=${1:-$root/meshes/tropical-ref}
JOBS=${2:-6}
FINE=${3:-"15 30 60 120"}
mkdir -p "$OUT/logs"
for r in $FINE; do for s in rings icos geo; do echo "$r $s"; done; done | xargs -P "$JOBS" -L1 bash -c '
  r=$0; s=$1; name=tropical-$((4*r))-${r}km-$s
  [ -f "'$OUT'/$name/$name.quality.json" ] || bash "'$root'/usp-utils/install/container/run.sh" \
    python -I "'$here'/create_tropical_refined_grid.py" -r $r --start $s --qtol 1e-3 --threads 1 -o "'$OUT'" \
    > "'$OUT'/logs/start-$name.out" 2>&1'
