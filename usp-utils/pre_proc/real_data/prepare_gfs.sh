#!/usr/bin/env bash
#
# prepare_gfs.sh — one-shot GFS met data for MPAS real-data init:
# download (AWS S3 by default) + convert to WPS intermediate files.
#
# GFS feeds both products from a SINGLE download:
#   atm  -> GFS:YYYY-MM-DD_HH  (atmosphere, for init_atmosphere case 7)
#   sst  -> SST:YYYY-MM-DD_HH  (SST/sea-ice, for init_atmosphere case 8)
#
# Usage:
#   ./prepare_gfs.sh --date YYYY-MM-DD [--cycle 00] [--fhour 0] [--res 0p25]
#                    [--product atm|sst|both] [--source aws|nomads|rda]
#                    [--outdir DIR] [--env ENV]
#
# --fhour is the forecast lead time in hours (0 = analysis). Use forecast hours
# (e.g. 024 048 ...) of one cycle to get evolving SST over a forecast window;
# the SST: file is auto-tagged with the valid date (cycle + fhour).
#
# Source coverage (GFS 0.25 deg): aws = 2021-03-23+, rda = 2015-01-15+,
# nomads = last ~10 days. For older dates use ERA5 (prepare_era5.sh) for the
# atmosphere and OISST (prepare_oisst.sh) for SST.
#
# Runs the Python steps in the conda env that has cfgrib + pywinter
# (default: cgfd-usp-mpas). For atm it prints the config_nfglevels value to put
# in namelist.init_atmosphere.

set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

DATE="" CYCLE="00" FHOUR="0" RES="0p25" PRODUCT="atm" SOURCE="aws" OUTDIR="" ENV="cgfd-usp-mpas"
while [ $# -gt 0 ]; do
    case "$1" in
        --date)    DATE="$2"; shift 2 ;;
        --cycle)   CYCLE="$2"; shift 2 ;;
        --fhour)   FHOUR="$2"; shift 2 ;;
        --res)     RES="$2"; shift 2 ;;
        --product) PRODUCT="$2"; shift 2 ;;
        --source)  SOURCE="$2"; shift 2 ;;
        --outdir)  OUTDIR="$2"; shift 2 ;;
        --env)     ENV="$2"; shift 2 ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$DATE" ] || { echo "ERROR: --date YYYY-MM-DD is required" >&2; exit 2; }
fhh=$(printf 'f%03d' "$((10#$FHOUR))")   # base-10 so e.g. 024 is not read as octal
case "$PRODUCT" in atm|sst|both) ;; *) echo "ERROR: --product must be atm|sst|both" >&2; exit 2 ;; esac

run() { conda run -n "$ENV" python "$SCRIPT_DIR/$@"; }

echo "[prepare_gfs] download ($SOURCE) ${DATE} ${CYCLE}z ${fhh} ${RES} [product=$PRODUCT]"
DL_ARGS=(--date "$DATE" --cycle "$CYCLE" --fhour "$FHOUR" --res "$RES" --source "$SOURCE")
# A pure SST product needs only the small surface subset (skip the 3D atmosphere).
[ "$PRODUCT" = "sst" ] && DL_ARGS+=(--fields sst)
[ -n "$OUTDIR" ] && DL_ARGS+=(--outdir "$OUTDIR")
run download_gfs.py "${DL_ARGS[@]}"

# locate the freshly downloaded GRIB (name depends on source, fhour and product)
ymd=${DATE//-/}
griddir="${OUTDIR:-$( cd "$SCRIPT_DIR/../../.." && pwd )/met_data/gfs/${ymd}${CYCLE}}"
if [ "$SOURCE" = "rda" ]; then
    grib="$griddir/gfs.0p25.${ymd}${CYCLE}.${fhh}.grib2"
else
    grib="$griddir/gfs.t${CYCLE}z.pgrb2.${RES}.${fhh}"
    [ "$PRODUCT" = "sst" ] && grib="${grib}.sst"   # download_gfs.py --fields sst suffix
fi
[ -f "$grib" ] || { echo "ERROR: downloaded GRIB not found: $grib" >&2; exit 1; }

if [ "$PRODUCT" = "atm" ] || [ "$PRODUCT" = "both" ]; then
    echo "[prepare_gfs] convert -> atmosphere intermediate (GFS:)"
    run gfs_to_intermediate.py --grib "$grib"
fi
if [ "$PRODUCT" = "sst" ] || [ "$PRODUCT" = "both" ]; then
    echo "[prepare_gfs] convert -> SST/sea-ice intermediate (SST:)"
    run gfs_sst_to_intermediate.py --grib "$grib"
fi

echo "[prepare_gfs] done."
[ "$PRODUCT" != "sst" ] && echo "  atm: set config_met_prefix='GFS' + the printed config_nfglevels; link GFS:* + *.static.nc in the run dir."
[ "$PRODUCT" != "atm" ] && echo "  sst: use config_init_case=8 with config_sfc_prefix='SST' (see README 'SST / sea-ice update')."
exit 0
