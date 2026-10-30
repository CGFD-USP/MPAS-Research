#!/usr/bin/env bash
# Runs one real-data forecast with atmosphere_model on <ranks> ranks in <dir>. The namelist is the default of the
# build (physics suite mesoscale_reference) with the time step, the start, the duration, config_len_disp and the
# options of the configuration (common.sh), all listed in RUN_INFO. Output, in single precision:
# 2D diagnostics every $RC_DIAG_INTERVAL (default 6 h, fields $RC_DIAG_FIELDS), MSLP every hour, and the 3D history
# every $RC_HISTORY_INTERVAL (default none; fields $RC_HISTORY_FIELDS, default the build's list; precision $RC_HISTORY_PRECISION,
# default single). $RC_PHYSICS_SUITE replaces the physics suite (e.g. none for dynamics-only tests).
# A complete run is left alone, a failed one must be removed by hand.
# Usage: bash run.sh <dir> <init.nc> <graph.info> <ranks> <config> <operators.nc|none> <start> <duration> <dt> <len_disp>
#   e.g. bash run.sh runs/c1/... init.nc mesh.graph.info 48 consistent-vke+em operators.nc 2023-07-10_00:00:00 5_00:00:00 120 25000
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -eq 10 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
dir=$1 init=$(readlink -f "$2") graph=$(readlink -f "$3") ranks=$4 config=$5 ops=$6 start=$7 duration=$8 dt=$9 len=${10}
read -r useops weights coeffs ke vke em <<< "$(rc_config "$config")"
[ "$useops" = no ] || { [ -f "$ops" ] && ops=$(readlink -f "$ops"); } || { echo "no operator file $ops" >&2; exit 1; }
[[ $start =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || { echo "start is YYYY-MM-DD_hh:mm:ss" >&2; exit 1; }
fields=${RC_DIAG_FIELDS:-xtime initial_time mslp
  height_250hPa height_500hPa height_700hPa height_850hPa temperature_250hPa temperature_500hPa temperature_700hPa
  temperature_850hPa uzonal_250hPa uzonal_500hPa uzonal_700hPa uzonal_850hPa umeridional_250hPa umeridional_500hPa
  umeridional_700hPa umeridional_850hPa relhum_500hPa relhum_700hPa relhum_850hPa w_250hPa w_500hPa w_850hPa
  vorticity_250hPa vorticity_500hPa vorticity_850hPa rainc rainnc precipw u10 v10 t2m q2 olrtoa}
for f in $fields; do
  grep -qx "$f" "$MPAS_BUILD/stream_list.atmosphere.diagnostics" || { echo "$f is not a diagnostic of this build" >&2; exit 1; }
done
if [ -f "$dir/RUN_INFO" ]; then
  grep -q '^status *ok' "$dir/RUN_INFO" && { echo "$dir is complete"; exit 0; }
  echo "$dir holds an earlier run, remove it to run again" >&2
  exit 1
fi
mkdir -p "$(dirname "$dir")"
mkdir "$dir"
cd "$dir"
ln -s "$init" init.nc
[ "$useops" = no ] || ln -s "$ops" custom_operators.nc
rc_partition "$graph" "$ranks"
ln -s "$MPAS_BUILD"/physics/* .
nl=namelist.atmosphere
cp "$MPAS_BUILD/$nl" $nl
rc_set $nl config_dt "$dt"
rc_set $nl config_start_time "'$start'"
rc_set $nl config_run_duration "'$duration'"
rc_add $nl nhyd_model config_len_disp "$len"
rc_set $nl config_use_custom_weightsOnEdge "$weights"
rc_set $nl config_use_custom_coeffs_reconstruct "$coeffs"
rc_set $nl config_ke_use_reconstructed_vel "$ke"
rc_set $nl config_ke_use_vertex_reconstructed_vel "$vke"
rc_set $nl config_edge_midpoint_flux "$em"
rc_set $nl config_block_decomp_file_prefix "'graph.info.part.'"
rc_set $nl config_do_restart false
[ -z "${RC_PHYSICS_SUITE:-}" ] || rc_set $nl config_physics_suite "'$RC_PHYSICS_SUITE'"
cp "$MPAS_BUILD"/stream_list.atmosphere.{output,surface,diag_ugwp} .
[ -z "${RC_HISTORY_FIELDS:-}" ] || printf '%s\n' $RC_HISTORY_FIELDS > stream_list.atmosphere.output
printf '%s\n' $fields > stream_list.atmosphere.diagnostics
cat > streams.atmosphere << EOF
<streams>
<immutable_stream name="input" type="input" filename_template="init.nc" input_interval="initial_only" />
<immutable_stream name="restart" type="input;output" filename_template="restart.\$Y-\$M-\$D_\$h.\$m.\$s.nc"
                  input_interval="initial_only" output_interval="${RC_RESTART_INTERVAL:-none}" />
<stream name="output" type="output" filename_template="history.\$Y-\$M-\$D_\$h.\$m.\$s.nc" precision="${RC_HISTORY_PRECISION:-single}"
        output_interval="${RC_HISTORY_INTERVAL:-none}" >
    <file name="stream_list.atmosphere.output"/>
</stream>
<stream name="diagnostics" type="output" filename_template="diag.\$Y-\$M-\$D_\$h.\$m.\$s.nc" precision="single"
        output_interval="${RC_DIAG_INTERVAL:-6:00:00}" >
    <file name="stream_list.atmosphere.diagnostics"/>
</stream>
<stream name="diag_hourly" type="output" filename_template="mslp.\$Y-\$M-\$D_\$h.\$m.\$s.nc" precision="single"
        filename_interval="none" output_interval="1:00:00" >
    <var name="xtime"/>
    <var name="mslp"/>
</stream>
<stream name="surface" type="input" filename_template="sfc_update.nc" filename_interval="none" input_interval="none" >
    <file name="stream_list.atmosphere.surface"/>
</stream>
<immutable_stream name="iau" type="input" filename_template="AmB.\$Y-\$M-\$D_\$h.\$m.\$s.nc" filename_interval="none"
                  packages="iau" input_interval="initial_only" />
<immutable_stream name="lbc_in" type="input" filename_template="lbc.\$Y-\$M-\$D_\$h.\$m.\$s.nc" filename_interval="input_interval"
                  packages="limited_area" input_interval="3:00:00" />
<immutable_stream name="ugwp_oro_data_in" type="input" filename_template="ugwp_oro_data.nc" packages="ugwp_orog_stream"
                  input_interval="initial_only" />
<immutable_stream name="ugwp_ngw_in" type="input" filename_template="ugwp_limb_tau.nc" packages="ugwp_ngw_stream"
                  input_interval="initial_only" />
<immutable_stream name="da_state" type="input;output" filename_template="mpasout.\$Y-\$M-\$D_\$h.\$m.\$s.nc" packages="jedi_da"
                  input_interval="initial_only" output_interval="0_06:00:00" />
<stream name="diag_ugwp" type="output" filename_template="diag_ugwp.\$Y-\$M-\$D_\$h.\$m.\$s.nc" packages="ugwp_diags_stream"
        output_interval="6:00:00" >
    <file name="stream_list.atmosphere.diag_ugwp"/>
</stream>
<immutable_stream name="custom_operators" type="input" filename_template="custom_operators.nc" packages="custom_operators"
                  input_interval="initial_only" />
</streams>
EOF
for s in $(grep -o 'name="[a-z_]*"' "$MPAS_BUILD/streams.atmosphere" | sort -u); do
  grep -q "stream $s" streams.atmosphere || { echo "stream $s of the default is missing" >&2; exit 1; }
done
{
  echo "run        $config from $start for $duration, dt $dt s, len_disp $len m, $ranks ranks"
  echo "init       $init"
  echo "operators  $([ "$useops" = no ] && echo none || echo "$ops")"
  echo "partition  $([ "$ranks" -eq 1 ] && echo none || echo "$graph.part.$ranks")"
  echo "build      $MPAS_BUILD"
  grep '^md5 .*atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | grep -v init_ | sed 's/^md5 */binary     /'
  diff "$MPAS_BUILD/$nl" $nl | sed -n 's/^> */namelist   /p'
} > RUN_INFO
rc_launch "$ranks" "$MPAS_BUILD/atmosphere_model"
if rc_mpas_ok log.atmosphere.0000.out; then
  echo "status     ok" >> RUN_INFO
else
  echo "status     failed" >> RUN_INFO
  echo "run failed, see $dir" >&2
  exit 1
fi
