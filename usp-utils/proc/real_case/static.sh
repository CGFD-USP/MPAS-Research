#!/usr/bin/env bash
# Interpolates the static fields (terrain, land use, soil, albedo, gravity-wave-drag orography) to a mesh with
# init_atmosphere (init case 7, static stages only) on <ranks> ranks, into <dir>/static.nc. The namelist is the
# default of the build with the changed keys listed in RUN_INFO. A folder with a complete static.nc is left alone.
# Usage: bash static.sh <dir> <grid.nc> <graph.info> <ranks> <geog dir>
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
[ $# -eq 5 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
dir=$1 grid=$(readlink -f "$2") graph=$(readlink -f "$3") ranks=$4 geog=$(readlink -f "$5")
[ -d "$geog" ] || { echo "no geog folder $geog" >&2; exit 1; }
if [ -f "$dir/RUN_INFO" ] && grep -q '^status *ok' "$dir/RUN_INFO"; then
  echo "$dir is complete"
  exit 0
fi
mkdir -p "$(dirname "$dir")"
mkdir "$dir"
cd "$dir"
ln -s "$grid" grid.nc
rc_partition "$graph" "$ranks"
nl=namelist.init_atmosphere
cp "$MPAS_BUILD/$nl" $nl
rc_set $nl config_init_case 7
rc_set $nl config_geog_data_path "'$geog/'"
rc_set $nl config_static_interp true
rc_set $nl config_native_gwd_static true
rc_set $nl config_native_gwd_gsl_static false
rc_set $nl config_vertical_grid false
rc_set $nl config_met_interp false
rc_set $nl config_input_sst false
rc_set $nl config_block_decomp_file_prefix "'graph.info.part.'"
cat > streams.init_atmosphere << 'EOF'
<streams>
<immutable_stream name="input" type="input" filename_template="grid.nc" input_interval="initial_only" />
<immutable_stream name="output" type="output" filename_template="static.nc" packages="initial_conds" output_interval="initial_only" />
<immutable_stream name="ugwp_oro_data" type="output" filename_template="ugwp_oro_data.nc" packages="gwd_gsl_stage_out" output_interval="initial_only" />
<immutable_stream name="surface" type="output" filename_template="sfc_unused.nc" filename_interval="none" packages="sfc_update" output_interval="none" />
<immutable_stream name="lbc" type="output" filename_template="lbc_unused.nc" filename_interval="output_interval" packages="lbcs" output_interval="none" />
</streams>
EOF
{
  echo "static     $grid, $ranks ranks"
  echo "geog       $geog"
  echo "build      $MPAS_BUILD"
  grep '^md5 .*init_atmosphere_model$' "$MPAS_BUILD/BUILD_INFO" | sed 's/^md5 */binary     /'
  diff "$MPAS_BUILD/$nl" $nl | sed -n 's/^> */namelist   /p'
} > RUN_INFO
rc_launch "$ranks" "$MPAS_BUILD/init_atmosphere_model"
if rc_mpas_ok log.init_atmosphere.0000.out && [ -f static.nc ]; then
  echo "status     ok" >> RUN_INFO
else
  echo "status     failed" >> RUN_INFO
  echo "static failed, see $dir" >&2
  exit 1
fi
