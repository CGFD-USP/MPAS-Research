#!/usr/bin/env bash
# Continuation in the density (create_tropical_refined_grid.py --start continuation), the variants of VARIANTS for the
# fine cell widths of CASES (km), JOBS at a time with one JIGSAW thread each.
# Meshes go to $OUT/t<coarse>-<fine>-c<steps>-q<qtol>-p<power>/ with quality and log json.
# Usage (on the host, MPAS image through run.sh, MPAS_BIND set to the folder of OUT):
#   bash run_continuation_study.sh OUT [JOBS] [CASES] [VARIANTS "steps:qtol:power ..."]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
OUT=$1
JOBS=${2:-8}
CASES=${3:-"120"}
VARIANTS=${4:-"5:1e-4:1 10:1e-4:1 20:1e-4:1"}
mkdir -p "$OUT"
for r in $CASES; do for v in $VARIANTS; do echo "$r $v"; done; done | xargs -P "$JOBS" -L1 bash -c '
  r=$0; IFS=: read -r k q p <<< "$1"; name=t$((4*r))-$r-c$k-q$q-p$p
  [ -f "'$OUT'/$name/$name.quality.json" ] || bash "'$root'/usp-utils/install/container/run.sh" \
    python -I "'$here'/create_tropical_refined_grid.py" -r $r --start continuation --steps $k --qtol $q --power $p \
    --threads 1 -o "'$OUT'" --name $name > "'$OUT'/$name.out" 2>&1'
