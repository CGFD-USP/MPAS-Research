#!/usr/bin/env bash
# Sets up and runs one Jablonowski and Williamson baroclinic wave run (init
# case 2, or its steady state, init case 1) in <root>/<mesh>/<case>_L<levels>/:
# init/ (init_atmosphere on 1 rank, shared by the configurations) and
# <config>_np<ranks>/ (atmosphere_model). <mesh> is the regenerated mesh of
# $MPAS_GRIDS/<mesh> (prepare_ncar_mesh.sh), or <mesh>-ncar for the original
# NCAR grid (trsk only). Settings and configurations: common.sh.
# Output: 2D diagnostics every $JW_DIAG_INTERVAL (default 1 day), 3D history
# every $JW_HISTORY_INTERVAL (default the run duration: initial and final state).
# mpirun options: $MPAS_MPIRUN_OPTS, default one node through shared memory only
# (the TCP transport of the image fails above about 24 ranks) and no binding
# (nodes shared with other jobs).
# Each folder gets RUN_INFO, whose "rerun" line repeats the run by hand.
# Usage: bash run_jw.sh <root> <mesh>[-ncar] <wave|steady> <levels> <config> <ranks> <duration>
#   e.g. bash run_jw.sh $MPAS_DATA_ROOT/jw x1.40962 wave 60 consistent 48 15_00:00:00
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -eq 7 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
root=$1 mesh=$2 case=$3 levels=$4 config=$5 ranks=$6 duration=$7
base=${mesh%-ncar}
dx=$(jw_dx_km "$base")
dt=$(jw_dt "$base")
cfg=$(jw_config "$config")
read -r opfile weights coeffs ke vke <<< "$cfg"
case $case in
  wave) init_case=2 ;;
  steady) init_case=1 ;;
  *) echo "case is wave or steady, not $case" >&2; exit 1 ;;
esac
gdir=$MPAS_GRIDS/$base
if [ "$mesh" = "$base" ]; then
  grid=$gdir/$base.grid.regen.nc
  part=$gdir/$base.grid.regen.graph.info.part.$ranks
  [ -f "$part" ] || part=$gdir/$base.graph.info.part.$ranks
else
  [ "$opfile" = none ] || { echo "operator files belong to the regenerated mesh, not $mesh" >&2; exit 1; }
  grid=$gdir/$base.grid.nc
  part=$gdir/$base.graph.info.part.$ranks
fi
[ -f "$grid" ] || { echo "no $grid, run prepare_ncar_mesh.sh $base" >&2; exit 1; }
[ "$ranks" -eq 1 ] || [ -f "$part" ] || { echo "no partition for $ranks ranks, run prepare_ncar_mesh.sh $base $ranks" >&2; exit 1; }

cdir=$root/$mesh/${case}_L$levels
idir=$cdir/init
rdir=$cdir/${config}_np$ranks
[ ! -e "$rdir" ] || { echo "$rdir exists" >&2; exit 1; }
mpas_ok() { grep -q 'Finished running the' "$1" && ! grep -q 'CRITICAL ERROR' "$1"; }
# runs an MPAS executable on $1 ranks in the current folder, recorded in RUN_INFO
launch() {
  local cmd="bash $JW_RUN mpirun ${MPAS_MPIRUN_OPTS:---bind-to none --mca btl self,vader} -n $1 $2"
  echo "rerun      source $MPAS_ROOT/usp-utils/machines/env.sh && cd $PWD && MPAS_BIND=$MPAS_BIND $cmd > run.log 2>&1" >> RUN_INFO
  echo "host       $(hostname -s), start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> RUN_INFO
  local t0
  t0=$(date +%s)
  $cmd > run.log 2>&1 || true
  echo "wall       $(($(date +%s) - t0)) s" >> RUN_INFO
}

if [ ! -f "$idir/init.nc" ]; then
  [ ! -e "$idir" ] || { echo "$idir holds a failed init, remove it" >&2; exit 1; }
  mkdir -p "$idir"
  cd "$idir"
  ln -s "$grid" grid.nc
  cat > namelist.init_atmosphere << EOF
&nhyd_model
    config_init_case = $init_case
    config_start_time = '0000-01-01_00:00:00'
/
&dimensions
    config_nvertlevels = $levels
/
&decomposition
    config_block_decomp_file_prefix = 'graph.info.part.'
/
EOF
  cat > streams.init_atmosphere << 'EOF'
<streams>
<immutable_stream name="input" type="input" filename_template="grid.nc" input_interval="initial_only" />
<immutable_stream name="output" type="output" filename_template="init.nc" packages="initial_conds" output_interval="initial_only" />
<immutable_stream name="surface" type="output" filename_template="sfc_unused.nc" filename_interval="none" packages="sfc_update" output_interval="none" />
<immutable_stream name="lbc" type="output" filename_template="lbc_unused.nc" filename_interval="output_interval" packages="lbcs" output_interval="none" />
</streams>
EOF
  {
    echo "init       $mesh $case L$levels (config_init_case $init_case)"
    echo "grid       $grid"
    echo "build      $MPAS_BUILD"
    grep '^md5 .*init_atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | sed 's/^md5 */binary     /'
  } > RUN_INFO
  echo "init $mesh $case L$levels"
  launch 1 "$MPAS_BUILD/init_atmosphere_model"
  if mpas_ok log.init_atmosphere.0000.out && [ -f init.nc ]; then
    echo "status     ok" >> RUN_INFO
  else
    echo "status     failed" >> RUN_INFO
    echo "init failed, see $idir" >&2
    exit 1
  fi
fi

mkdir -p "$rdir"
cd "$rdir"
ln -s ../init/init.nc init.nc
[ "$opfile" = none ] || ln -s "$gdir/$opfile" custom_operators.nc
[ "$ranks" -eq 1 ] || ln -s "$part" "graph.info.part.$ranks"
cat > namelist.atmosphere << EOF
&nhyd_model
    config_dt = $dt
    config_start_time = '0000-01-01_00:00:00'
    config_run_duration = '$duration'
    config_split_dynamics_transport = false
    config_number_of_sub_steps = 6
    config_dynamics_split_steps = 1
    config_h_mom_eddy_visc2 = 0.0
    config_h_mom_eddy_visc4 = 0.0
    config_v_mom_eddy_visc2 = 0.0
    config_h_theta_eddy_visc2 = 0.0
    config_h_theta_eddy_visc4 = 0.0
    config_v_theta_eddy_visc2 = 0.0
    config_horiz_mixing = '2d_smagorinsky'
    config_len_disp = $(awk -v dx="$dx" 'BEGIN { print dx * 1000 }')
    config_u_vadv_order = 3
    config_w_vadv_order = 3
    config_theta_vadv_order = 3
    config_scalar_vadv_order = 3
    config_theta_adv_order = 3
    config_scalar_adv_order = 3
    config_scalar_advection = false
    config_positive_definite = false
    config_coef_3rd_order = 1.0
    config_monotonic = false
    config_smdiv = 0.1
    config_use_custom_weightsOnEdge = $weights
    config_use_custom_coeffs_reconstruct = $coeffs
    config_ke_use_reconstructed_vel = $ke
    config_ke_use_vertex_reconstructed_vel = $vke
/
&damping
    config_zd = 22000.0
    config_xnutr = 0.0
/
&limited_area
    config_apply_lbcs = false
/
&io
    config_pio_num_iotasks = 0
    config_pio_stride = 1
/
&decomposition
    config_block_decomp_file_prefix = 'graph.info.part.'
/
&restart
    config_do_restart = false
/
&printout
    config_print_global_minmax_vel = true
    config_print_global_minmax_sca = false
/
&physics
    config_sst_update = false
    config_sstdiurn_update = false
    config_deepsoiltemp_update = false
    config_bucket_update = 'none'
    config_physics_suite = 'none'
/
EOF
cat > streams.atmosphere << EOF
<streams>
<immutable_stream name="input" type="input" filename_template="init.nc" input_interval="initial_only" />
<immutable_stream name="restart" type="input;output" filename_template="restart.\$Y-\$M-\$D_\$h.\$m.\$s.nc" input_interval="initial_only" output_interval="none" />
<stream name="output" type="output" filename_template="history.\$Y-\$M-\$D_\$h.\$m.\$s.nc" output_interval="${JW_HISTORY_INTERVAL:-$duration}" >
    <file name="stream_list.atmosphere.output"/>
</stream>
<stream name="diagnostics" type="output" filename_template="diag.\$Y-\$M-\$D_\$h.\$m.\$s.nc" output_interval="${JW_DIAG_INTERVAL:-1_00:00:00}" >
    <file name="stream_list.atmosphere.diagnostics"/>
</stream>
<immutable_stream name="custom_operators" type="input" filename_template="custom_operators.nc" packages="custom_operators" input_interval="initial_only" />
</streams>
EOF
printf '%s\n' xtime w theta rho pressure uReconstructZonal uReconstructMeridional \
  > stream_list.atmosphere.output
printf '%s\n' xtime mslp vorticity_850hPa uzonal_850hPa umeridional_850hPa temperature_850hPa \
  height_500hPa uzonal_surface umeridional_surface > stream_list.atmosphere.diagnostics

{
  echo "run        $mesh $case L$levels $config, $ranks ranks, $duration, dt $dt s"
  echo "grid       $grid"
  echo "operators  $([ "$opfile" = none ] && echo none || echo "$gdir/$opfile")"
  echo "partition  $([ "$ranks" -eq 1 ] && echo none || echo "$part")"
  echo "build      $MPAS_BUILD"
  grep '^md5 .*atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | grep -v init_ | sed 's/^md5 */binary     /'
} > RUN_INFO
echo "run $mesh $case L$levels $config np$ranks"
launch "$ranks" "$MPAS_BUILD/atmosphere_model"
if mpas_ok log.atmosphere.0000.out; then
  echo "status     ok" >> RUN_INFO
else
  echo "status     failed" >> RUN_INFO
  echo "run failed, see $rdir" >&2
  exit 1
fi
