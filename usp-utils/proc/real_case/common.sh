# Settings of the real-data runs (bash): source common.sh
# Loads the machine profile of usp-utils/machines and needs
#   MPAS_BUILD  a build of usp-utils/install/container/build_mpas.sh (required)
_rc_here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$_rc_here/../../machines/env.sh" || return 1
. "$_rc_here/../schemes.sh"
unset _rc_here
[ -n "${MPAS_BUILD:-}" ] && [ -f "$MPAS_BUILD/BUILD_INFO" ] ||
  { echo "set MPAS_BUILD to a build of build_mpas.sh (a folder with BUILD_INFO)" >&2; return 1; }
# apptainer binds the home already
case $MPAS_BUILD in
  "$HOME"/*) ;;
  *) MPAS_BIND=$MPAS_BUILD${MPAS_BIND:+:$MPAS_BIND} ;;
esac
export MPAS_BUILD MPAS_BIND

# true when the MPAS log of $1 ended without a critical error
rc_mpas_ok() { grep -q 'Finished running the' "$1" && ! grep -q 'CRITICAL ERROR' "$1"; }

# runs an MPAS executable on $1 ranks in the current folder, recorded in RUN_INFO
rc_launch() {
  local cmd="bash $MPAS_ROOT/usp-utils/machines/mpirun.sh $1 $2" t0
  echo "rerun      source $MPAS_ROOT/usp-utils/machines/env.sh && cd $PWD && MPAS_BIND=$MPAS_BIND $cmd > run.log 2>&1" >> RUN_INFO
  echo "host       $(hostname -s), start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> RUN_INFO
  t0=$(date +%s)
  $cmd > run.log 2>&1 || true
  echo "wall       $(($(date +%s) - t0)) s" >> RUN_INFO
}

# links the METIS partition for $2 ranks of the graph file $1 as graph.info.part.<ranks>
rc_partition() {
  [ "$2" -eq 1 ] && return 0
  [ -f "$1.part.$2" ] || { echo "no partition $1.part.$2" >&2; return 1; }
  ln -sf "$1.part.$2" "graph.info.part.$2"
}

# sets "key = value" in the namelist file $1, failing when the key is not there
rc_set() {
  grep -q "^ *$2 *=" "$1" || { echo "no $2 in $1" >&2; return 1; }
  sed -i "s|^\( *\)$2 *=.*|\1$2 = $3|" "$1"
}
# adds "key = value" to the group $2 of the namelist file $1
rc_add() {
  grep -q "^&$2\$" "$1" || { echo "no group $2 in $1" >&2; return 1; }
  ! grep -q "^ *$3 *=" "$1" || { echo "$3 is already in $1" >&2; return 1; }
  sed -i "/^&$2\$/a\\    $3 = $4" "$1"
}
