#!/usr/bin/env bash
# Makes the real-data initial state of one start time with init_atmosphere (init case 7, vertical grid and
# interpolation of the first-guess fields) on <ranks> ranks, from the static file of the mesh and a WPS
# intermediate file <prefix>:YYYY-MM-DD_HH, into <dir>/init.nc. The namelist is the default of the build (55 levels,
# top 30 km) with the changed keys listed in RUN_INFO. A folder with a complete init.nc is left alone.
# Usage: bash init.sh <dir> <static.nc> <graph.info> <ranks> <intermediate file> <nfglevels>
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -eq 6 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
dir=$1 static=$(readlink -f "$2") graph=$(readlink -f "$3") ranks=$4 met=$(readlink -f "$5") nfg=$6
name=$(basename "$met")
[[ $name =~ ^([A-Za-z0-9]+):([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2})$ ]] ||
  { echo "$met is not an intermediate file <prefix>:YYYY-MM-DD_HH" >&2; exit 1; }
prefix=${BASH_REMATCH[1]}
start=${BASH_REMATCH[2]}:00:00
if [ -f "$dir/RUN_INFO" ] && grep -q '^status *ok' "$dir/RUN_INFO"; then
  echo "$dir is complete"
  exit 0
fi
mkdir -p "$(dirname "$dir")"
mkdir "$dir"
cd "$dir"
ln -s "$static" static.nc
ln -s "$met" "$name"
rc_partition "$graph" "$ranks"
nl=namelist.init_atmosphere
cp "$MPAS_BUILD/$nl" $nl
rc_set $nl config_init_case 7
rc_set $nl config_start_time "'$start'"
rc_set $nl config_stop_time "'$start'"
rc_set $nl config_nfglevels "$nfg"
rc_set $nl config_met_prefix "'$prefix'"
rc_set $nl config_static_interp false
rc_set $nl config_native_gwd_static false
rc_set $nl config_native_gwd_gsl_static false
rc_set $nl config_vertical_grid true
rc_set $nl config_met_interp true
rc_set $nl config_input_sst false
rc_set $nl config_block_decomp_file_prefix "'graph.info.part.'"
cat > streams.init_atmosphere << 'EOF'
<streams>
<immutable_stream name="input" type="input" filename_template="static.nc" input_interval="initial_only" />
<immutable_stream name="output" type="output" filename_template="init.nc" packages="initial_conds" output_interval="initial_only" />
<immutable_stream name="ugwp_oro_data" type="output" filename_template="ugwp_oro_data.nc" packages="gwd_gsl_stage_out" output_interval="initial_only" />
<immutable_stream name="surface" type="output" filename_template="sfc_unused.nc" filename_interval="none" packages="sfc_update" output_interval="none" />
<immutable_stream name="lbc" type="output" filename_template="lbc_unused.nc" filename_interval="output_interval" packages="lbcs" output_interval="none" />
</streams>
EOF
{
  echo "init       $start from $met, $ranks ranks"
  echo "static     $static"
  echo "build      $MPAS_BUILD"
  grep '^md5 .*init_atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | sed 's/^md5 */binary     /'
  diff "$MPAS_BUILD/$nl" $nl | sed -n 's/^> */namelist   /p'
} > RUN_INFO
rc_launch "$ranks" "$MPAS_BUILD/init_atmosphere_model"
if rc_mpas_ok log.init_atmosphere.0000.out && [ -f init.nc ]; then
  echo "status     ok" >> RUN_INFO
else
  echo "status     failed" >> RUN_INFO
  echo "init failed, see $dir" >&2
  exit 1
fi
