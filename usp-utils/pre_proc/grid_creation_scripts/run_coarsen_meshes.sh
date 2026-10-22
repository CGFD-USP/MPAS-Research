#!/usr/bin/env bash
# Tropical meshes made by decimating a finer mesh (create_tropical_refined_grid.py --start coarsen). The chain coarsens
# SRC to 2x, 4x and 8x larger spacing, each level from the optimised previous one, and the jumps coarsen SRC directly
# by 4x and 8x. Meshes go to $OUT/<chain|jump>-<coarse>-<fine>/.
# Usage (on the host, MPAS image through run.sh, MPAS_BIND set to the folder of OUT):
#   bash run_coarsen_meshes.sh OUT SRC FINE_KM [QTOL] [DIRECTION "x y z"]
# SRC is the grid file of the fine mesh of FINE_KM, e.g. NCAR x4.1572866 with 15.
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
OUT=$1; SRC=$2; FINE=$3; Q=${4:-1e-3}; DIR=${5:-"1 0 0"}
mkdir -p "$OUT"
make() {   # name fine_km source levels
  [ -f "$OUT/$1/$1.quality.json" ] || bash "$root/usp-utils/install/container/run.sh" python -I "$here/create_tropical_refined_grid.py" \
    -r $2 --start coarsen --source "$3" --levels $4 --qtol $Q --direction $DIR --threads 1 -o "$OUT" --name $1 > "$OUT/$1.out" 2>&1
}
chain() {
  prev=$SRC; f=$FINE
  for i in 1 2 3; do
    f=$((f*2)); name=chain-$((4*f))-$f; make $name $f $prev 1; prev=$OUT/$name/$name.nc
  done
}
chain &
for i in 2 3; do f=$((FINE*2**i)); make jump-$((4*f))-$f $f $SRC $i & done
wait
