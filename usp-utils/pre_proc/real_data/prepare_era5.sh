#!/usr/bin/env bash
#
# prepare_era5.sh — one-shot ERA5 atmospheric data for MPAS real-data init:
# download pressure- and single-level GRIB (cdsapi) + convert to the WPS
# intermediate file (GFS:YYYY-MM-DD_HH) that init_atmosphere reads.
#
# Use for the scientific/downscaling pipeline (ERA5 atmosphere; pair with OISST
# for SST via prepare_oisst.sh). ERA5 covers 1940 -> present.
#
# Usage:
#   ./prepare_era5.sh --date YYYY-MM-DD [--time 00] [--area "N W S E"]
#                     [--outdir DIR] [--env ENV]
#
# Requires a CDS account + ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api).
# Runs the Python steps in the conda env with cdsapi + cfgrib + pywinter
# (default: cgfd-usp-mpas). Prints config_nfglevels for namelist.init_atmosphere.

set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

DATE="" TIME="00" AREA="" OUTDIR="" ENV="cgfd-usp-mpas"
while [ $# -gt 0 ]; do
    case "$1" in
        --date)   DATE="$2"; shift 2 ;;
        --time)   TIME="$2"; shift 2 ;;
        --area)   AREA="$2"; shift 2 ;;
        --outdir) OUTDIR="$2"; shift 2 ;;
        --env)    ENV="$2"; shift 2 ;;
        -h|--help) sed -n '2,16p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$DATE" ] || { echo "ERROR: --date YYYY-MM-DD is required" >&2; exit 2; }

run() { conda run -n "$ENV" python "$SCRIPT_DIR/$@"; }

echo "[prepare_era5] download ${DATE} ${TIME}z"
DL_ARGS=(--date "$DATE" --time "$TIME")
[ -n "$OUTDIR" ] && DL_ARGS+=(--outdir "$OUTDIR")
[ -n "$AREA" ] && DL_ARGS+=(--area $AREA)   # 4 tokens: N W S E
run download_era5.py "${DL_ARGS[@]}"

# locate the freshly downloaded GRIB files
ymd=${DATE//-/}; hh=$(printf '%02d' "${TIME#0}")
era5dir="${OUTDIR:-$( cd "$SCRIPT_DIR/../../.." && pwd )/met_data/era5/${ymd}${hh}}"
pl="$era5dir/era5_pl_${ymd}${hh}.grib"
sl="$era5dir/era5_sl_${ymd}${hh}.grib"
[ -f "$pl" ] && [ -f "$sl" ] || { echo "ERROR: ERA5 GRIB not found in $era5dir" >&2; exit 1; }

echo "[prepare_era5] convert -> WPS intermediate (GFS:)"
run era5_to_intermediate.py --pl "$pl" --sl "$sl"

echo "[prepare_era5] done. Set config_met_prefix='GFS' and the printed"
echo "               config_nfglevels in namelist.init_atmosphere; link the"
echo "               GFS:* intermediate (and the *.static.nc) into the run dir."
