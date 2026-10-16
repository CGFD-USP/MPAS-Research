#!/usr/bin/env bash
# Sets up and runs one steady zonal flow run (init case 11, an isothermal
# solid-body zonal flow) through ../jw_baroclinic_wave/run_jw.sh, in
# <root>/<mesh>/<case>_L<levels>/<config>_np<ranks>/ (initial state in init/).
# The case folder is zonal, plus -nodiss without explicit horizontal mixing,
# -nosmdiv without the divergence damping of the acoustic steps, and -dt<f> for a time step f times the one of the mesh (common.sh of the JW
# benchmark), or -step<s> for a time step of s seconds. Output: u, w, theta, rho and pressure once a day
# ($ZS_HISTORY_INTERVAL), no 2D diagnostics. $JW_SEGMENT and the other variables
# of run_jw.sh apply.
# Usage: bash run_zonal.sh <root> <mesh>[-ncar] <levels> <config> <ranks> <duration> [nodiss] [nosmdiv] [dt=<f> | step=<s>]
#   e.g. bash run_zonal.sh $MPAS_DATA_ROOT/zonal x1.40962 30 trsk 32 10_00:00:00 nodiss
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -ge 6 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
root=$1 mesh=$2 levels=$3 config=$4 ranks=$5 duration=$6
shift 6
mixing=smag smdiv=0.1 factor=1 step= case=zonal
for v in "$@"; do
  case $v in
    nodiss) mixing=nodiss case=$case-nodiss ;;
    nosmdiv) smdiv=0.0 case=$case-nosmdiv ;;
    dt=*) factor=${v#dt=} case=$case-dt$factor ;;
    step=*) step=${v#step=} case=$case-step$step ;;
    *) echo "unknown variant $v (nodiss, nosmdiv, dt=<f> or step=<s>)" >&2; exit 1 ;;
  esac
done
dt=${step:-$(awk -v dt="$(jw_dt "${mesh%-ncar}")" -v f="$factor" 'BEGIN { print dt * f }')}
JW_INIT_CASE=$ZS_INIT_CASE
JW_INIT_EXTRA=$(printf '&vertical_grid\n    config_ztop = %s\n/' "$ZS_ZTOP")
JW_DT=$dt
JW_HORIZ_MIXING=$(zs_mixing $mixing)
JW_SMDIV=$smdiv
JW_HISTORY_FIELDS=$ZS_HISTORY_FIELDS
JW_HISTORY_INTERVAL=$ZS_HISTORY_INTERVAL
JW_DIAG_INTERVAL=none
export JW_INIT_CASE JW_INIT_EXTRA JW_DT JW_HORIZ_MIXING JW_SMDIV JW_HISTORY_FIELDS JW_HISTORY_INTERVAL JW_DIAG_INTERVAL
exec bash "$ZS_RUN_JW" "$root" "$mesh" "$case" "$levels" "$config" "$ranks" "$duration"
