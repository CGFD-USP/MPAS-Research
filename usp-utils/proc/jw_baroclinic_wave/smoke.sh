#!/usr/bin/env bash
# Smoke test of the baroclinic wave benchmark on the 480 km mesh, 1 day per run
# with output every 6 h: every configuration on 4 ranks, consistent-vke also on
# 1 rank, trsk on the NCAR grid, and the steady state and 60 levels for trsk and
# consistent-vke. Prepares the mesh when needed and ends with check_runs.py's
# summary.txt in <root>. About 1 min on 4 cores.
# Usage: bash smoke.sh [root]   (default $MPAS_DATA_ROOT/mpas_benchmarks/jw_smoke_<UTC date and time>)
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
root=${1:-$MPAS_DATA_ROOT/mpas_benchmarks/jw_smoke_$(date -u +%Y%m%dT%H%M)}
[ ! -e "$root" ] || { echo "$root exists" >&2; exit 1; }
mesh=x1.2562 ranks=4 duration=1_00:00:00
export JW_HISTORY_INTERVAL=6:00:00 JW_DIAG_INTERVAL=6:00:00

bash "$JW_PREPARE" $mesh $ranks
mkdir -p "$root"
cp "$MPAS_BUILD/BUILD_INFO" "$root/"
sif=${MPAS_SIF:-$MPAS_ROOT/.apptainer/mpas.sif}
echo "image      $sif $(md5sum < "$sif" | cut -d' ' -f1)" > "$root/IMAGE"
run() { bash "$here/run_jw.sh" "$root" "$@" || echo "$*" >> "$root/failed"; }
for c in $JW_CONFIGS; do
  run $mesh wave 26 "$c" $ranks $duration
done
run $mesh wave 26 consistent-vke 1 $duration
run $mesh-ncar wave 26 trsk $ranks $duration
for c in trsk consistent-vke; do
  run $mesh steady 26 $c $ranks $duration
  run $mesh wave 60 $c $ranks $duration
done
bash "$JW_RUN" python3 "$here/check_runs.py" "$root" | tee "$root/summary.txt"
[ ! -f "$root/failed" ] || { echo "failed runs:"; cat "$root/failed"; exit 1; } >&2
