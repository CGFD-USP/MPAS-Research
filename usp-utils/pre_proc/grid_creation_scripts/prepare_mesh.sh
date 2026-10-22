#!/usr/bin/env bash
# Prepares any MPAS grid file for runs with custom operators, in $MPAS_GRIDS/<name>/ (default
# $MPAS_DATA_ROOT/mpas_grids): the regenerated mesh <name>.grid.regen.nc (regenerate-mesh.jl), the operator
# file operators-consistent.nc (Peixoto tangential weights, Perot) and METIS partitions of the regenerated
# mesh for the given rank counts, as prepare_ncar_mesh.sh does for the NCAR meshes. Steps already done are skipped.
# Usage: bash prepare_mesh.sh <name> <grid.nc> [ranks ...]   e.g. bash prepare_mesh.sh b-240-60 chain-240-60.nc 32
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/../../machines/env.sh"
: "${MPAS_GRIDS:=$MPAS_DATA_ROOT/mpas_grids}"
name=${1:?usage: bash prepare_mesh.sh <name> <grid.nc> [ranks ...]}
src=$(readlink -f "${2:?usage: bash prepare_mesh.sh <name> <grid.nc> [ranks ...]}")
shift 2
run=$MPAS_ROOT/usp-utils/install/container/run.sh
jl() { bash "$run" julia --project="${JL_PROJECT:-@cgfd-usp-mpas}" --threads=auto "$@"; }

dir=$MPAS_GRIDS/$name
mkdir -p "$dir"
cd "$dir"
regen=$name.grid.regen
made=()
rm -rf .work
mkdir .work
if [ ! -f "$regen.nc" ]; then
  echo "regenerating $name"
  jl "$here/regenerate-mesh.jl" "$src" ".work/$regen.nc"
  mv ".work/$regen.graph.info" ".work/$regen.nc" .
  made+=("regenerate-mesh.jl $src $regen.nc")
fi
if [ ! -f operators-consistent.nc ]; then
  echo "writing operators-consistent.nc"
  jl "$here/create-voronoi-operator.jl" "$regen.nc" -t Peixoto -c Perot -v Perot .work/operators-consistent.nc
  mv .work/operators-consistent.nc .
  made+=("create-voronoi-operator.jl $regen.nc -t Peixoto -c Perot -v Perot operators-consistent.nc")
fi
rmdir .work
for p in "$@"; do
  [ "$p" -gt 1 ] && [ ! -f "$regen.graph.info.part.$p" ] || continue
  bash "$run" gpmetis -minconn -contig -niter=200 "$regen.graph.info" "$p" > /dev/null
  made+=("gpmetis -minconn -contig -niter=200 $regen.graph.info $p")
done
if [ ${#made[@]} -gt 0 ]; then
  {
    echo "== $(date -u +%Y-%m-%dT%H:%MZ) on $(hostname -s) by $USER"
    printf 'made       %s\n' "${made[@]}"
    for p in "$MPAS_ROOT"/external/*/; do
      [ -d "$p/.git" ] || continue
      echo "julia      $(basename "$p") $(git -C "$p" rev-parse HEAD)"
    done
    md5sum "$regen.nc" operators-consistent.nc | sed 's/^/md5        /'
  } >> PROVENANCE
fi
echo "mesh ready in $dir"
