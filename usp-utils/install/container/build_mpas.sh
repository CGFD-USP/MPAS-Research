#!/usr/bin/env bash
# Builds init_atmosphere_model and atmosphere_model of an MPAS-Research commit in
# the MPAS image, from a clean copy of the commit (git archive), so uncommitted
# edits never enter a build. Writes $MPAS_BUILD_ROOT/<ref>_<commit>_<precision>/
# (default build root ~/mpas-builds) with the two executables, the default
# namelists and streams, the physics tables (physics/) and BUILD_INFO.
# <ref>: a branch (master, consistency-analysis, origin/<branch>) or a commit;
# a branch missing locally is taken from origin, as of the last git fetch.
# The atmosphere build downloads the WRF physics tables (MPAS-Data) with git.
# Parallel make: $MPAS_MAKE_JOBS (default 16).
# Usage: bash build_mpas.sh <ref> [single|double]   (default single, as MPAS)
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$here/../../.." && pwd)
ref=${1:?usage: bash build_mpas.sh <ref> [single|double]}
precision=${2:-single}
case $precision in
  single | double) ;;
  *) echo "precision is single or double, not $precision" >&2; exit 1 ;;
esac
commit=$(git -C "$repo" rev-parse --verify -q "$ref^{commit}" ||
  git -C "$repo" rev-parse --verify -q "origin/$ref^{commit}") ||
  { echo "unknown ref $ref (git fetch first?)" >&2; exit 1; }
short=$(git -C "$repo" rev-parse --short=8 "$commit")
root=${MPAS_BUILD_ROOT:-$HOME/mpas-builds}
name=$(printf '%s' "$ref" | tr '/' '-')_${short}_$precision
dest=$root/$name
[ ! -e "$dest" ] || { echo "$dest exists, remove it to rebuild" >&2; exit 1; }
sif=${MPAS_SIF:-$repo/.apptainer/mpas.sif}

work=$root/.$name.build
mkdir -p "$root"
rm -rf "$work"
mkdir "$work"
trap 'rm -rf "$work"' EXIT
git -C "$repo" archive "$commit" | tar -x -C "$work"

echo "building $ref ($short, $precision) in $work"
jobs=${MPAS_MAKE_JOBS:-16}
make_opts="gnu PRECISION=$precision AUTOCLEAN=true"
if ! MPAS_BIND="$root${MPAS_BIND:+:$MPAS_BIND}" MPAS_SIF=$sif bash "$here/run.sh" bash -c "
    cd '$work' && unset PIO NETCDF &&
    make -j$jobs $make_opts CORE=init_atmosphere &&
    make -j$jobs $make_opts CORE=atmosphere" > "$work/build.log" 2>&1; then
  cp "$work/build.log" "$root/$name.failed.log"
  echo "build failed, log in $root/$name.failed.log" >&2
  exit 1
fi

mkdir -p "$dest/physics"
cp "$work"/init_atmosphere_model "$work"/atmosphere_model "$dest/"
cp "$work"/default_inputs/* "$dest/"
find "$work/src/core_atmosphere/physics/physics_wrf/files" \
  "$work/src/core_atmosphere/physics/physics_noahmp/parameters" \
  -maxdepth 1 -type f \( -name '*.TBL' -o -name '*DATA*' -o -name 'COMPATIBILITY' \) \
  -exec cp {} "$dest/physics/" \;
cp "$work/build.log" "$dest/build.log"

versions=$(MPAS_SIF=$sif bash "$here/run.sh" bash -c '
  gfortran --version | head -1; mpif90 --showme:version; /opt/pnetcdf/bin/pnetcdf-config --version')
{
  echo "ref        $ref"
  echo "commit     $commit ($(git -C "$repo" log -1 --format='%ad %s' --date=short "$commit"))"
  echo "precision  $precision"
  echo "make       make $make_opts CORE=init_atmosphere, then CORE=atmosphere"
  echo "built      $(date -u +%Y-%m-%dT%H:%MZ) on $(hostname -s) by $USER"
  echo "image      $sif"
  echo "image md5  $(md5sum < "$sif" | cut -d' ' -f1)"
  printf '%s\n' "$versions" | sed 's/^/toolchain  /'
  (cd "$dest" && md5sum init_atmosphere_model atmosphere_model) | sed 's/^/md5        /'
  for p in "$repo"/external/*/; do
    [ -d "$p/.git" ] || continue
    dirty=$(git -C "$p" status --porcelain --untracked-files=no | grep -q . && echo " +uncommitted" || true)
    echo "julia      $(basename "$p") $(git -C "$p" rev-parse HEAD)$dirty"
  done
} > "$dest/BUILD_INFO"
echo "built $dest"
cat "$dest/BUILD_INFO"
