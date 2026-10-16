# Settings of the steady zonal flow benchmark (bash): source common.sh
# Builds on the baroclinic wave benchmark (../jw_baroclinic_wave/common.sh: machine
# profile, build, meshes, spacing and time step of a mesh, operator configurations)
# and runs through its run_jw.sh.
_zs_here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$_zs_here/../jw_baroclinic_wave/common.sh" || return 1
ZS_RUN_JW=$_zs_here/../jw_baroclinic_wave/run_jw.sh
unset _zs_here
ZS_INIT_CASE=11
ZS_ZTOP=30000.0
# 3D fields of the error check, written once a day
ZS_HISTORY_FIELDS="xtime u w theta rho pressure"
: "${ZS_HISTORY_INTERVAL:=1_00:00:00}"

# horizontal mixing of a variant: the JW settings (2d Smagorinsky) or none
zs_mixing() {
  case $1 in
    smag) echo 2d_smagorinsky ;;
    nodiss) echo 2d_fixed ;;
    *) echo "unknown mixing $1 (smag or nodiss)" >&2; return 1 ;;
  esac
}
