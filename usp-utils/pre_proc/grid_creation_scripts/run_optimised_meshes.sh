#!/usr/bin/env bash
# Optimised copies of the uniform and tropical meshes, made by JIGSAW itself with the CVT optimiser
# kernel (best of run_option_study.sh) at the optimisation tolerance of the raw mesh of each family
# (uniform 1e-6, tropical 1e-3). One JIGSAW thread per mesh, all meshes at once.
# Usage: bash run_optimised_meshes.sh   (from the MPAS-Research root, MPAS image through run.sh)
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
run() { bash "$root/usp-utils/install/container/run.sh" python -I "$here/create_tropical_refined_grid.py" \
  --threads 1 --jig optm_kern=cvt+dqdx "$@"; }
U=$root/meshes/uniform T=$root/meshes/tropical-ref
mkdir -p "$U/logs" "$T/logs"
for r in 480 240 120 60; do
  run -r $r --ratio 1 --qtol 1e-6 -o "$U" --name uniform-cvt-$r > "$U/logs/uniform-cvt-$r.out" 2>&1 &
done
for r in 120 60 30 15; do
  run -r $r --qtol 1e-3 -o "$T" --name tropical-$((4*r))-${r}km-opt > "$T/logs/opt-a-$r.out" 2>&1 &
done
for r in 120 60 30; do
  run -r $r --band-ref 120 --qtol 1e-3 -o "$T" --name tropical-fixcells-$((4*r))-${r}km-opt > "$T/logs/opt-b-$r.out" 2>&1 &
done
wait
