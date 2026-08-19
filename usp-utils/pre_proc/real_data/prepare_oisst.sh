#!/usr/bin/env bash
#
# prepare_oisst.sh — one-shot OISST SST/sea-ice data for MPAS SST update files.
#
# Two modes:
#   (default)      observed daily OISST v2.1 (NCEI) over a date range  -> SST: files
#   --climatology  OISST daily climatology (LTM 1991-2020, via OPeNDAP) -> SST: files
#                  tagged with the target dates (for forecasts / typical-month runs,
#                  where there is no observed SST for the dates).
#
# Usage:
#   ./prepare_oisst.sh --start YYYY-MM-DD [--end YYYY-MM-DD] [--hour 00]
#                      [--climatology] [--outdir DIR] [--env ENV]
#
# OISST observed covers 1981-09-01 -> present. Runs the Python steps in the conda
# env with xarray + pywinter (default: cgfd-usp-mpas). See README "SST / sea-ice
# update" for the init_atmosphere config_init_case=8 run.

set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

START="" END="" HOUR="00" CLIM=0 OUTDIR="" ENV="cgfd-usp-mpas"
while [ $# -gt 0 ]; do
    case "$1" in
        --start)       START="$2"; shift 2 ;;
        --end)         END="$2"; shift 2 ;;
        --hour)        HOUR="$2"; shift 2 ;;
        --climatology) CLIM=1; shift ;;
        --outdir)      OUTDIR="$2"; shift 2 ;;
        --env)         ENV="$2"; shift 2 ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$START" ] || { echo "ERROR: --start YYYY-MM-DD is required" >&2; exit 2; }
END="${END:-$START}"

run() { conda run -n "$ENV" python "$SCRIPT_DIR/$@"; }

if [ "$CLIM" = "1" ]; then
    echo "[prepare_oisst] climatology (LTM 1991-2020) ${START}..${END}"
    CL_ARGS=(--start "$START" --end "$END" --hour "$HOUR")
    [ -n "$OUTDIR" ] && CL_ARGS+=(--outdir "$OUTDIR")
    run oisst_clim_to_intermediate.py "${CL_ARGS[@]}"
    echo "[prepare_oisst] done (climatology)."
else
    oisstdir="${OUTDIR:-$( cd "$SCRIPT_DIR/../../.." && pwd )/met_data/oisst}"
    echo "[prepare_oisst] download observed ${START}..${END}"
    run download_oisst.py --start "$START" --end "$END" --outdir "$oisstdir"
    echo "[prepare_oisst] convert -> WPS intermediate (SST:)"
    run oisst_to_intermediate.py --indir "$oisstdir" --start "$START" --end "$END" --hour "$HOUR"
    echo "[prepare_oisst] done. SST:* files in $oisstdir."
fi
echo "                Run init_atmosphere config_init_case=8 with"
echo "                config_sfc_prefix='SST' (see README 'SST / sea-ice update')."
