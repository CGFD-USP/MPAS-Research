# Settings of the baroclinic wave benchmark (bash): source common.sh
# Loads the machine profile of usp-utils/machines and needs
#   MPAS_BUILD  a build of usp-utils/install/container/build_mpas.sh (required)
#   MPAS_GRIDS  meshes of prepare_ncar_mesh.sh (default $MPAS_DATA_ROOT/mpas_grids)
_jw_here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$_jw_here/../../machines/env.sh" || return 1
. "$_jw_here/../schemes.sh"
unset _jw_here
[ -n "${MPAS_BUILD:-}" ] && [ -f "$MPAS_BUILD/BUILD_INFO" ] ||
  { echo "set MPAS_BUILD to a build of build_mpas.sh (a folder with BUILD_INFO)" >&2; return 1; }
: "${MPAS_GRIDS:=$MPAS_DATA_ROOT/mpas_grids}"
JW_RUN=$MPAS_ROOT/usp-utils/install/container/run.sh
JW_PREPARE=$MPAS_ROOT/usp-utils/pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh
# apptainer binds the home already
case $MPAS_BUILD in
  "$HOME"/*) ;;
  *) MPAS_BIND=$MPAS_BUILD${MPAS_BIND:+:$MPAS_BIND} ;;
esac
export MPAS_BUILD MPAS_GRIDS MPAS_BIND

# nominal cell spacing (km) of an NCAR mesh x1.<nCells>, as in NCAR's mesh names:
# nCells = 10 n^2 + 2, and 480 km for x1.2562 (n = 16). $JW_DX_KM sets it for any other mesh.
jw_dx_km() {
  [ -z "${JW_DX_KM:-}" ] || { echo "$JW_DX_KM"; return; }
  [[ $1 =~ ^x1\.([0-9]+)$ ]] || { echo "$1 is not an NCAR mesh x1.<nCells>" >&2; return 1; }
  awk -v n="${BASH_REMATCH[1]}" 'BEGIN { printf "%.6g\n", 480 * sqrt(2560 / (n - 2)) }'
}

# time step (s): 450 s at 120 km as in the NCAR test case, proportional to the spacing
jw_dt() {
  local dx
  dx=$(jw_dx_km "$1") || return 1
  awk -v dx="$dx" 'BEGIN { print 450 * dx / 120 }'
}

JW_CONFIGS="trsk consistent consistent-vke lsq2 lsq2-vke trsk-newke-consistent trsk-newke-lsq2"
