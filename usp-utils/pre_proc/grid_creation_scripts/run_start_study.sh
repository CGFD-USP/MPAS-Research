#!/usr/bin/env bash
# JIGSAW from almost regular starting point sets (create_tropical_refined_grid.py --start) on the tropical designs,
# every variant below, JOBS at a time with one JIGSAW thread each. The fine cell widths of CASES (km) give the
# 4x coarser design as well, e.g. 120 for 480-120 km.
# Meshes go to $OUT/t<coarse>-<fine>-<start>-<variant>/ with quality json and log json (times).
# Usage (on the host, MPAS image through run.sh): bash run_start_study.sh [OUT] [JOBS] [CASES]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
OUT=${1:-$root/meshes/tropical-ref/start-tests}
JOBS=${2:-8}
CASES=${3:-"120 60"}
mkdir -p "$OUT"
# variant|options. Merge and split of cells (zip, div) are off in q3, q6, mesh, odt and lim1 and on in zd.
F="--jig optm_zip_=False --jig optm_div_=False"
variants=(
  "q3|--qtol 1e-3 $F"
  "q6|--qtol 1e-6 $F"
  "zd|--qtol 1e-6 --jig optm_zip_=True --jig optm_div_=True"
  "mesh|--qtol 1e-6 --mesh-iter 5000000 $F"
  "odt|--qtol 1e-6 --jig optm_kern=odt+dqdx $F"
  "lim1|--qtol 1e-6 --qlim 1.0 $F"
)
for r in $CASES; do
  for s in rings icos geo; do
    for v in "${variants[@]}"; do
      echo "t$((4*r))-$r-$s-${v%%|*}|-r $r --start $s ${v#*|}"
    done
  done
done | xargs -P "$JOBS" -I{} bash -c '
  line="{}"; name=${line%%|*}; opts=${line#*|}
  [ -f "'$OUT'/$name/$name.quality.json" ] || bash "'$root'/usp-utils/install/container/run.sh" \
    python -I "'$here'/create_tropical_refined_grid.py" $opts --threads 1 -o "'$OUT'" --name $name > "'$OUT'/$name.out" 2>&1'
