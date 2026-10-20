#!/usr/bin/env bash
# Prepares an NCAR quasi-uniform mesh x1.<nCells> for MPAS runs with custom
# operators, in $MPAS_GRIDS/<mesh>/ (default $MPAS_DATA_ROOT/mpas_grids): the
# NCAR grid with its partitions, the regenerated mesh (regenerate-mesh.jl, same
# cell and vertex order), the operator files operators-consistent.nc (Perot) and
# operators-lsq2.nc (LSq2), both with the Peixoto tangential weights
# (create-voronoi-operator.jl), METIS partitions of the regenerated mesh for the
# given rank counts, and PROVENANCE. Steps already done are skipped. Runs the
# tools in the MPAS image, on any machine with a profile in usp-utils/machines.
# LSQ2_PROJECT (a Julia project folder) makes operators-lsq2.nc with the
# VoronoiOperators of that project instead of the shared environment.
# Usage: bash prepare_ncar_mesh.sh <mesh> [ranks ...]   e.g. x1.40962 48
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/../../machines/env.sh"
: "${MPAS_GRIDS:=$MPAS_DATA_ROOT/mpas_grids}"
mesh=${1:?usage: bash prepare_ncar_mesh.sh <mesh> [ranks ...]}
shift
[[ $mesh =~ ^x1\.[0-9]+$ ]] || { echo "$mesh is not an NCAR quasi-uniform mesh x1.<nCells>" >&2; exit 1; }
url=https://www2.mmm.ucar.edu/projects/mpas/atmosphere_meshes/$mesh.tar.gz
run=$MPAS_ROOT/usp-utils/install/container/run.sh
sif=${MPAS_SIF:-$MPAS_ROOT/.apptainer/mpas.sif}
jl() { bash "$run" julia --project="${JL_PROJECT:-@cgfd-usp-mpas}" --threads=auto "$@"; }

dir=$MPAS_GRIDS/$mesh
mkdir -p "$dir"
cd "$dir"
if [ ! -f "$mesh.grid.nc" ]; then
  echo "downloading $mesh"
  curl -fsSL -o "$mesh.tar.gz" "$url"
  md5sum "$mesh.tar.gz" > "$mesh.tar.gz.md5"
  tar -xzf "$mesh.tar.gz"
  rm "$mesh.tar.gz"
fi

# outputs go through .work/ so that an interrupted step leaves nothing behind
regen=$mesh.grid.regen
made=()
rm -rf .work
mkdir .work
if [ ! -f "$regen.nc" ]; then
  echo "regenerating $mesh"
  jl "$here/regenerate-mesh.jl" "$mesh.grid.nc" ".work/$regen.nc"
  mv ".work/$regen.graph.info" ".work/$regen.nc" .
  made+=("regenerate-mesh.jl $mesh.grid.nc $regen.nc")
fi
ops() {
  [ -f "$1" ] && return
  echo "writing $1"
  jl "$here/create-voronoi-operator.jl" "$regen.nc" "${@:2}" ".work/$1"
  mv ".work/$1" .
  made+=("create-voronoi-operator.jl $regen.nc ${*:2} $1")
}
ops operators-consistent.nc -t Peixoto -c Perot -v Perot
JL_PROJECT=${LSQ2_PROJECT:-} ops operators-lsq2.nc -t Peixoto -c LSq2 -v LSq2
rmdir .work

for p in "$@"; do
  [ "$p" -gt 1 ] && [ ! -f "$regen.graph.info.part.$p" ] || continue
  if bash "$run" sh -c 'command -v gpmetis' > /dev/null; then
    bash "$run" gpmetis -minconn -contig -niter=200 "$regen.graph.info" "$p" > /dev/null
    made+=("gpmetis -minconn -contig -niter=200 $regen.graph.info $p")
  elif [ -f "$mesh.graph.info.part.$p" ]; then
    echo "no gpmetis in the image, $p ranks use $mesh.graph.info.part.$p (same cell order)"
  else
    echo "no gpmetis in the image and no NCAR partition for $p ranks" >&2
    exit 1
  fi
done

# neighbour sets of each cell, independent of the order and padding of a graph file
neighbours() {
  awk '{
    n = split($0, a)
    for (i = 2; i <= n; i++) {
      v = a[i] + 0
      for (j = i - 1; j > 0 && a[j] + 0 > v; j--) a[j + 1] = a[j]
      a[j + 1] = v
    }
    s = ""
    for (i = 1; i <= n; i++) s = s " " a[i] + 0
    print s
  }' "$1"
}
if [ ${#made[@]} -gt 0 ]; then
  first=$([ -f PROVENANCE ] || echo yes)
  {
    echo "== $(date -u +%Y-%m-%dT%H:%MZ) on $(hostname -s) by $USER"
    if [ -n "$first" ]; then
      echo "source     $url"
      echo "tarball    $(cut -d' ' -f1 "$mesh.tar.gz.md5") (md5)"
    fi
    printf 'made       %s\n' "${made[@]}"
    echo "image      $sif ($(stat -c '%s bytes, %y' "$sif"))"
    if [ -n "${LSQ2_PROJECT:-}" ]; then
      vo=$(sed -n '/^\[\[deps.VoronoiOperators\]\]/,/^$/s/^path = "\(.*\)"/\1/p' "$LSQ2_PROJECT/Manifest.toml")
      echo "julia      operators-lsq2.nc: VoronoiOperators.jl $(git -C "$vo" rev-parse HEAD) of $LSQ2_PROJECT"
    fi
    for p in "$MPAS_ROOT"/external/*/; do
      [ -d "$p/.git" ] || continue
      dirty=$(git -C "$p" status --porcelain --untracked-files=no | grep -q . && echo " +uncommitted" || true)
      echo "julia      $(basename "$p") $(git -C "$p" rev-parse HEAD)$dirty"
    done
    if cmp -s <(neighbours "$mesh.graph.info") <(neighbours "$regen.graph.info"); then
      echo "graph      $regen.graph.info has the cell neighbours of $mesh.graph.info"
    else
      echo "graph      $regen.graph.info differs from $mesh.graph.info"
    fi
    md5sum "$regen.nc" operators-*.nc | sed 's/^/md5        /'
  } >> PROVENANCE
fi
echo "mesh ready in $dir"
