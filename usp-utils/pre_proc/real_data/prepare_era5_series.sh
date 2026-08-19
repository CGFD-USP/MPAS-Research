#!/usr/bin/env bash
#
# prepare_era5_series.sh — build a *series* of ERA5 WPS intermediates over a date
# window, for long downscaling runs (the LBC series of a month / year / years).
# Wraps prepare_era5.sh in a window loop. Designed for unattended runs:
#
#   - Resumable: skips every time whose ERA5:<date>_<hh> intermediate already
#     exists, so re-running only fetches what is missing.
#   - Fault-tolerant: a failed CDS request logs FAIL and the series continues;
#     re-run later to pick up the gaps.
#   - nohup-friendly: every line is timestamped; redirect to a log and detach.
#   - Optional parallelism (--jobs N). NOTE: the CDS queue throttles concurrent
#     requests per user, so keep N small (2-3); large N just queues or is rejected.
#
# Usage:
#   nohup ./prepare_era5_series.sh --start 2020-01-01 --end 2020-02-01 \
#         --area "10 -57 0 -30" --cadence 6 --jobs 2 > era5_2020.log 2>&1 &
#   tail -f era5_2020.log
#
#   --start YYYY-MM-DD   first day (series starts at START 00z)            [required]
#   --end   YYYY-MM-DD   last day to include, at 00z (set to the run stop) [required]
#   --area  "N W S E"    ERA5 download box (mesh + margin; W/E negative over Brazil)
#   --cadence H          LBC cadence in hours (default 6 -> 00/06/12/18)
#   --jobs N             concurrent downloads (default 1; keep <=3 for CDS)
#   --env ENV            conda env (default cgfd-usp-mpas)
#   --outbase DIR        base output dir (default <repo>/met_data/era5)
#
# Requires a CDS account + ~/.cdsapirc. SST is a single separate call
# (prepare_oisst.sh --start --end), not part of this series.

set -uo pipefail   # NOT -e: one failed CDS request must not abort the whole series
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

START="" END="" AREA="" CAD=6 JOBS=1 ENV="cgfd-usp-mpas" OUTBASE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --start)   START="$2"; shift 2 ;;
        --end)     END="$2"; shift 2 ;;
        --area)    AREA="$2"; shift 2 ;;
        --cadence) CAD="$2"; shift 2 ;;
        --jobs)    JOBS="$2"; shift 2 ;;
        --env)     ENV="$2"; shift 2 ;;
        --outbase) OUTBASE="$2"; shift 2 ;;
        -h|--help) sed -n '2,30p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$START" ] && [ -n "$END" ] || { echo "ERROR: --start and --end (YYYY-MM-DD) are required" >&2; exit 2; }

REPO_ROOT=$( cd "$SCRIPT_DIR/../../.." && pwd )
MET="${OUTBASE:-$REPO_ROOT/met_data/era5}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Download+convert one (date, hour), skipping if the intermediate already exists.
do_one() {
    local d="$1" hh="$2"
    local ymd="${d//-/}"
    local intf="$MET/${ymd}${hh}/ERA5:${d}_${hh}"
    if [ -s "$intf" ]; then
        echo "[$(ts)] SKIP $d ${hh}z (have ERA5:${d}_${hh})"
        return 0
    fi
    echo "[$(ts)] GET  $d ${hh}z"
    local args=(--date "$d" --time "$hh" --env "$ENV")
    [ -n "$AREA" ] && args+=(--area "$AREA")
    if "$SCRIPT_DIR/prepare_era5.sh" "${args[@]}"; then
        echo "[$(ts)] DONE $d ${hh}z"
    else
        echo "[$(ts)] FAIL $d ${hh}z (re-run to retry)"
        return 1
    fi
}
export -f do_one ts
export SCRIPT_DIR MET AREA ENV

# Build the task list: timestamps from START 00z to END 00z (inclusive), step CAD h.
# Parse as UTC (the '... UTC' suffix) and iterate by epoch seconds so the result is
# independent of the server's local timezone and of date(1)'s output locale.
start_ts=$( date -u -d "$START 00:00 UTC" +%s ) || { echo "ERROR: bad --start date" >&2; exit 2; }
end_ts=$(   date -u -d "$END 00:00 UTC"   +%s ) || { echo "ERROR: bad --end date" >&2; exit 2; }
[ "$start_ts" -le "$end_ts" ] || { echo "ERROR: --start is after --end" >&2; exit 2; }
step=$(( CAD * 3600 ))
tasks=()
t_ts="$start_ts"
while [ "$t_ts" -le "$end_ts" ]; do
    tasks+=("$( date -u -d "@$t_ts" +%Y-%m-%d ) $( date -u -d "@$t_ts" +%H )")
    t_ts=$(( t_ts + step ))
done

echo "[$(ts)] ERA5 series: ${#tasks[@]} times | ${START}..${END} | cadence ${CAD}h | jobs ${JOBS} | area '${AREA:-global}'"

if [ "$JOBS" -gt 1 ]; then
    printf '%s\n' "${tasks[@]}" | xargs -P "$JOBS" -n 2 bash -c 'do_one "$1" "$2"' _
else
    for task in "${tasks[@]}"; do do_one $task; done
fi

# Summary: how many intermediates are present now (resumability check).
have=0
for task in "${tasks[@]}"; do
    set -- $task; d="$1"; hh="$2"; ymd="${d//-/}"
    [ -s "$MET/${ymd}${hh}/ERA5:${d}_${hh}" ] && have=$((have + 1))
done
miss=$(( ${#tasks[@]} - have ))
echo "[$(ts)] summary: ${have}/${#tasks[@]} intermediates present, ${miss} missing"
[ "$miss" -gt 0 ] && echo "[$(ts)] re-run the same command to retry the ${miss} missing time(s)."
exit 0
