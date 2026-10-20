#!/usr/bin/env bash
# Sets up and runs one Jablonowski and Williamson baroclinic wave run (init
# case 2, or its steady state, init case 1) in <root>/<mesh>/<case>_L<levels>/:
# init/ (init_atmosphere on 1 rank, shared by the configurations) and
# <config>_np<ranks>/ (atmosphere_model). <mesh> is the regenerated mesh of
# $MPAS_GRIDS/<mesh> (prepare_ncar_mesh.sh), or <mesh>-ncar for the original
# NCAR grid (trsk only). Settings and configurations: common.sh.
# Output: 2D diagnostics every $JW_DIAG_INTERVAL (default 1 day), 3D history
# every $JW_HISTORY_INTERVAL (default the run duration: initial and final state).
# MPI launch: usp-utils/machines/mpirun.sh (one node, or the nodes of a PBS job).
# Segments: $JW_SEGMENT (D_hh:mm:ss, default the whole duration) splits the run
# into segments, each started from the restart file of the previous one (only
# the latest restart file is kept; the last segment writes none, unless
# $JW_KEEP_RESTART is set). A call runs the remaining segments, at most
# $JW_SEGMENTS_PER_CALL of them, so a long run can be a chain of shorter jobs;
# a call on a complete run does nothing, and a call after an interrupted
# segment repeats it.
# Each folder gets RUN_INFO, whose "rerun" lines repeat the run by hand.
# Flat surface: the cases wave-flat and steady-flat (init cases 18 and 17) use the JW fields over a
# flat surface (surface pressure p0 eta_s(lat)), not directly comparable with published JW results.
# Rebalanced wind: the cases wave-rebal and steady-rebal (init cases 21 and 20) are the JW cases with the
# initial wind balanced against the pressure gradient of the model. The cases wave-exactavg and steady-exactavg
# (init cases 24 and 23) add the exact edge average of the 2D wind and a 2D latitude grid refined to the mesh.
# Other test cases (e.g. ../zonal_steady): a <case> other than wave and steady
# takes its config_init_case from $JW_INIT_CASE, and $JW_INIT_EXTRA (namelist
# groups) is appended to namelist.init_atmosphere. $JW_DT (s) replaces the time
# step, $JW_HORIZ_MIXING the horizontal mixing (default 2d_smagorinsky),
# $JW_SMDIV the divergence damping (default 0.1), and $JW_HISTORY_FIELDS and
# $JW_DIAG_FIELDS the fields of the two output streams. $JW_NHYD_EXTRA (namelist
# lines) is appended to &nhyd_model, e.g. for options of the dynamics, and $JW_RUN_TAG (e.g. +ep) is
# added to the name of the run folder, so that runs of one configuration with different options
# share the initial state.
# Usage: bash run_jw.sh <root> <mesh>[-ncar] <wave|steady|wave-flat|steady-flat|wave-rebal|steady-rebal|wave-exactavg|steady-exactavg> <levels> <config> <ranks> <duration>
#   e.g. bash run_jw.sh $MPAS_DATA_ROOT/jw x1.40962 wave 60 consistent 48 15_00:00:00
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -eq 7 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
root=$1 mesh=$2 case=$3 levels=$4 config=$5 ranks=$6 duration=$7
base=${mesh%-ncar}
dx=$(jw_dx_km "$base")
dt=${JW_DT:-$(jw_dt "$base")}
cfg=$(jw_config "$config")
read -r opfile weights coeffs ke vke <<< "$cfg"
case $case in
  wave) init_case=2 ;;
  steady) init_case=1 ;;
  wave-flat) init_case=18 ;;
  steady-flat) init_case=17 ;;
  wave-rebal) init_case=21 ;;
  steady-rebal) init_case=20 ;;
  wave-exactavg) init_case=24 ;;
  steady-exactavg) init_case=23 ;;
  *)
    [ -n "${JW_INIT_CASE:-}" ] || { echo "case is wave or steady, or set JW_INIT_CASE for $case" >&2; exit 1; }
    init_case=$JW_INIT_CASE
    ;;
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
  # the regenerated mesh has the cells and neighbours of the NCAR grid
  [ -f "$part" ] || part=$gdir/$base.grid.regen.graph.info.part.$ranks
fi
[ -f "$grid" ] || { echo "no $grid, run prepare_ncar_mesh.sh $base" >&2; exit 1; }
[ "$ranks" -eq 1 ] || [ -f "$part" ] || { echo "no partition for $ranks ranks, run prepare_ncar_mesh.sh $base $ranks" >&2; exit 1; }

cdir=$root/$mesh/${case}_L$levels
idir=$cdir/init
rdir=$cdir/${config}${JW_RUN_TAG:-}_np$ranks
# duration in seconds of D_hh:mm:ss
seconds() {
  local d=0 t=$1 h m sec
  [[ $1 == *_* ]] && d=${1%%_*} t=${1#*_}
  IFS=: read -r h m sec <<< "$t"
  echo $((10#$d * 86400 + 10#$h * 3600 + 10#$m * 60 + 10#$sec))
}
# seconds from 0000-01-01_00:00:00 to a time of year 0000 (a leap year in MPAS's
# gregorian calendar), as written in restart_timestamp
stamp_seconds() {
  [[ $1 =~ ^0000-[0-9]{2}-[0-9]{2}_[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || { echo "unexpected time $1" >&2; return 1; }
  awk -F'[-_:]' '{
    split("31 29 31 30 31 30 31 31 30 31 30 31", days, " ")
    d = $3 - 1
    for (i = 1; i < $2; i++) d += days[i]
    print ((d * 24 + $4) * 60 + $5) * 60 + $6
  }' <<< "$1"
}
segment=${JW_SEGMENT:-$duration}
nseg=$(($(seconds "$duration") / $(seconds "$segment")))
[ $((nseg * $(seconds "$segment"))) -eq "$(seconds "$duration")" ] ||
  { echo "the duration $duration is not a multiple of the segment $segment" >&2; exit 1; }
if [ -f "$rdir/RUN_INFO" ]; then
  grep -q '^status *ok' "$rdir/RUN_INFO" && { echo "$rdir is complete"; exit 0; }
  grep -q '^status *failed' "$rdir/RUN_INFO" && { echo "$rdir failed, see its logs" >&2; exit 1; }
fi
mpas_ok() { grep -q 'Finished running the' "$1" && ! grep -q 'CRITICAL ERROR' "$1"; }
# runs an MPAS executable on $1 ranks in the current folder, recorded in RUN_INFO
# (after the command in $prelude, if any)
prelude=
launch() {
  local cmd="bash $MPAS_ROOT/usp-utils/machines/mpirun.sh $1 $2"
  echo "rerun      source $MPAS_ROOT/usp-utils/machines/env.sh && cd $PWD && ${prelude:+$prelude && }MPAS_BIND=$MPAS_BIND $cmd > run.log 2>&1" >> RUN_INFO
  echo "host       $(hostname -s), start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> RUN_INFO
  local t0
  t0=$(date +%s)
  $cmd > run.log 2>&1 || true
  echo "wall       $(($(date +%s) - t0)) s" >> RUN_INFO
}

# the first run of a case makes its initial state (mkdir is atomic), and runs
# started meanwhile wait for its status, at most $JW_INIT_WAIT seconds (default 3 h)
mkdir -p "$cdir"
if mkdir "$idir" 2> /dev/null; then
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
  [ -z "${JW_INIT_EXTRA:-}" ] || echo "$JW_INIT_EXTRA" >> namelist.init_atmosphere
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
else
  waited=0
  until grep -q '^status' "$idir/RUN_INFO" 2> /dev/null; do
    [ "$waited" -lt "${JW_INIT_WAIT:-10800}" ] || { echo "no initial state in $idir after $waited s" >&2; exit 1; }
    sleep 30
    waited=$((waited + 30))
  done
  grep -q '^status *ok' "$idir/RUN_INFO" || { echo "$idir holds a failed init, remove it" >&2; exit 1; }
fi

# namelist.atmosphere.<start|restart>: the first segment, and the next ones
nhyd_extra=${JW_NHYD_EXTRA:+$'\n'$JW_NHYD_EXTRA}
namelist() {
  cat << EOF
&nhyd_model
    config_dt = $dt
    config_start_time = '$2'
    config_run_duration = '$segment'
    config_split_dynamics_transport = false
    config_number_of_sub_steps = 6
    config_dynamics_split_steps = 1
    config_h_mom_eddy_visc2 = 0.0
    config_h_mom_eddy_visc4 = 0.0
    config_v_mom_eddy_visc2 = 0.0
    config_h_theta_eddy_visc2 = 0.0
    config_h_theta_eddy_visc4 = 0.0
    config_v_theta_eddy_visc2 = 0.0
    config_horiz_mixing = '${JW_HORIZ_MIXING:-2d_smagorinsky}'
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
    config_smdiv = ${JW_SMDIV:-0.1}
    config_use_custom_weightsOnEdge = $weights
    config_use_custom_coeffs_reconstruct = $coeffs
    config_ke_use_reconstructed_vel = $ke
    config_ke_use_vertex_reconstructed_vel = $vke$nhyd_extra
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
    config_do_restart = $1
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
}

t0=0000-01-01_00:00:00
if mkdir "$rdir" 2> /dev/null; then
  cd "$rdir"
  ln -s ../init/init.nc init.nc
  [ "$opfile" = none ] || ln -s "$gdir/$opfile" custom_operators.nc
  [ "$ranks" -eq 1 ] || ln -s "$part" "graph.info.part.$ranks"
  namelist false "$t0" > namelist.atmosphere.start
  namelist true file > namelist.atmosphere.restart
  # output times count from the start of the run, also in a restarted segment;
  # restart files every segment (streams.atmosphere.segments), none at the end
  # of the last segment (streams.atmosphere.last)
  streams() {
    cat << EOF
<streams>
<immutable_stream name="input" type="input" filename_template="init.nc" input_interval="initial_only" />
<immutable_stream name="restart" type="input;output" filename_template="restart.\$Y-\$M-\$D_\$h.\$m.\$s.nc" input_interval="initial_only" output_interval="$1" clobber_mode="replace_files" />
<stream name="output" type="output" filename_template="history.\$Y-\$M-\$D_\$h.\$m.\$s.nc" reference_time="$t0" output_interval="${JW_HISTORY_INTERVAL:-$duration}" clobber_mode="replace_files" >
    <file name="stream_list.atmosphere.output"/>
</stream>
<stream name="diagnostics" type="output" filename_template="diag.\$Y-\$M-\$D_\$h.\$m.\$s.nc" reference_time="$t0" output_interval="${JW_DIAG_INTERVAL:-1_00:00:00}" clobber_mode="replace_files" >
    <file name="stream_list.atmosphere.diagnostics"/>
</stream>
<immutable_stream name="custom_operators" type="input" filename_template="custom_operators.nc" packages="custom_operators" input_interval="initial_only" />
</streams>
EOF
  }
  if [ "$nseg" -eq 1 ]; then
    streams none > streams.atmosphere
  else
    streams "$segment" > streams.atmosphere.segments
    streams "$([ -n "${JW_KEEP_RESTART:-}" ] && echo "$segment" || echo none)" > streams.atmosphere.last
  fi
  printf '%s\n' ${JW_HISTORY_FIELDS:-xtime w theta rho pressure uReconstructZonal uReconstructMeridional} \
    > stream_list.atmosphere.output
  printf '%s\n' ${JW_DIAG_FIELDS:-xtime mslp vorticity_850hPa uzonal_850hPa umeridional_850hPa \
    temperature_850hPa height_500hPa uzonal_surface umeridional_surface} > stream_list.atmosphere.diagnostics
  {
    echo "run        $mesh $case L$levels $config, $ranks ranks, $duration, dt $dt s"
    echo "segments   $nseg of $segment"
    echo "grid       $grid"
    echo "operators  $([ "$opfile" = none ] && echo none || echo "$gdir/$opfile")"
    echo "partition  $([ "$ranks" -eq 1 ] && echo none || echo "$part")"
    echo "build      $MPAS_BUILD"
    grep '^md5 .*atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | grep -v init_ | sed 's/^md5 */binary     /'
  } > RUN_INFO
else
  cd "$rdir"
fi

# segments done: the time of the latest restart file, which MPAS records in
# restart_timestamp only once the file is complete
progress() {
  local t
  if [ "$nseg" -gt 1 ] && [ -f restart_timestamp ]; then
    t=$(stamp_seconds "$(tr -d ' ' < restart_timestamp)") || return 1
    echo $((t / $(seconds "$segment")))
  else
    echo 0
  fi
}
done_segments=$(progress)
calls=0
while [ "$done_segments" -lt "$nseg" ] && [ "$calls" -lt "${JW_SEGMENTS_PER_CALL:-$nseg}" ]; do
  k=$((done_segments + 1))
  if [ "$done_segments" -eq 0 ]; then
    prelude="cp namelist.atmosphere.start namelist.atmosphere"
  else
    [ -f restart_timestamp ] || { echo "no restart_timestamp in $rdir for segment $k" >&2; exit 1; }
    prelude="cp namelist.atmosphere.restart namelist.atmosphere"
  fi
  if [ "$nseg" -gt 1 ]; then
    prelude="$prelude && cp streams.atmosphere.$([ "$k" -lt "$nseg" ] && echo segments || echo last) streams.atmosphere"
  fi
  eval "$prelude"
  echo "run $mesh $case L$levels $config np$ranks, segment $k of $nseg"
  launch "$ranks" "$MPAS_BUILD/atmosphere_model"
  [ "$nseg" -eq 1 ] || cp log.atmosphere.0000.out "log.atmosphere.0000.seg$k.out"
  if ! mpas_ok log.atmosphere.0000.out; then
    echo "status     failed in segment $k of $nseg" >> RUN_INFO
    echo "run failed, see $rdir" >&2
    exit 1
  fi
  if [ "$k" -lt "$nseg" ]; then
    [ "$(progress)" -eq "$k" ] || { echo "restart_timestamp does not match segment $k in $rdir" >&2; exit 1; }
    latest="restart.$(tr -d ' ' < restart_timestamp | tr : .).nc"
    for f in restart.*.nc; do
      [ "$f" = "$latest" ] || rm -f "$f"
    done
  fi
  until=the\ end
  [ "$k" -eq "$nseg" ] || until=$(tr -d ' ' < restart_timestamp)
  echo "segment    $k of $nseg ok, until $until" >> RUN_INFO
  done_segments=$k
  calls=$((calls + 1))
done
if [ "$done_segments" -eq "$nseg" ]; then
  # a complete run keeps no restart file, unless $JW_KEEP_RESTART is set
  [ -n "${JW_KEEP_RESTART:-}" ] || rm -f restart.*.nc
  echo "status     ok" >> RUN_INFO
fi
