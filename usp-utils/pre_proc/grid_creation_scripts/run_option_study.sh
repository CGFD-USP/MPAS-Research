#!/usr/bin/env bash
# JIGSAW option study on the edge-point offset: every variant below on the 480-120 km tropical
# mesh and on a uniform 240 km mesh, JOBS at a time, one JIGSAW thread each.
# Meshes go to $OUT/<case>-<variant>/ with quality json and log json (times).
# Usage (on the host, MPAS image through run.sh): bash run_option_study.sh [OUT] [JOBS]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
OUT=${1:-$root/meshes/options}
JOBS=${2:-8}
mkdir -p "$OUT"
# variant|create_tropical_refined_grid.py options
variants=(
  "base|--qtol 1e-3"
  "q6|--qtol 1e-6"
  "cvt|--qtol 1e-6 --jig optm_kern=cvt+dqdx"
  "cvt10|--qtol 1e-10 --jig optm_kern=cvt+dqdx"
  "skew|--qtol 1e-6 --jig optm_cost=skew-cos"
  "cvtskew|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig optm_cost=skew-cos"
  "dual|--qtol 1e-6 --jig optm_dual=True"
  "dualw|--qtol 1e-6 --jig optm_dual=True --jig optm_wmin=-0.99 --jig optm_wmax=0.5"
  "cvtdual|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig optm_dual=True"
  "cvtdualw|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig optm_dual=True --jig optm_wmin=-0.99 --jig optm_wmax=0.5"
  "cvtskewdual|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig optm_cost=skew-cos --jig optm_dual=True"
  "cvtnomom|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig optm_beta=0 --jig optm_zeta=0"
  "cvtq99|--qtol 1e-6 --qlim 0.99 --jig optm_kern=cvt+dqdx"
  "cvtq1|--qtol 1e-6 --qlim 1.0 --jig optm_kern=cvt+dqdx"
  "h95|--qtol 1e-6 --optm-iter 200 --jig optm_kern=h95+dqdx"
  "h95dual|--qtol 1e-6 --optm-iter 200 --jig optm_kern=h95+dqdx --jig optm_dual=True"
  "cvtrad|--qtol 1e-6 --jig optm_kern=cvt+dqdx --jig mesh_rad2=1.0 --jig mesh_off2=0.8"
)
cases=("ref480|-r 120" "uni240|-r 240 --ratio 1")
for c in "${cases[@]}"; do
  for v in "${variants[@]}"; do
    echo "${c%%|*}-${v%%|*}|${c#*|} ${v#*|}"
  done
done | xargs -P "$JOBS" -I{} bash -c '
  line="{}"; name=${line%%|*}; opts=${line#*|}
  [ -f "'$OUT'/$name/$name.quality.json" ] || bash "'$root'/usp-utils/install/container/run.sh" \
    python -I "'$here'/create_tropical_refined_grid.py" $opts --threads 1 -o "'$OUT'" --name $name > "'$OUT'/$name.out" 2>&1'
