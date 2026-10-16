#!/usr/bin/env bash
# Smoke test of the steady zonal flow benchmark on the 480 km mesh, 1 day per run
# with output every 6 h, on 4 ranks: trsk with 30 levels (also without mixing,
# with half the time step and with 15 levels), trsk on the NCAR grid and
# consistent-vke. Prepares the mesh when needed and ends with check_zonal.py's
# summary.txt in <root>. About 1 min on 4 cores.
# Usage: bash smoke.sh [root]   (default $MPAS_DATA_ROOT/mpas_benchmarks/zonal_smoke_<UTC date and time>)
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/common.sh"
root=${1:-$MPAS_DATA_ROOT/mpas_benchmarks/zonal_smoke_$(date -u +%Y%m%dT%H%M)}
[ ! -e "$root" ] || { echo "$root exists" >&2; exit 1; }
mesh=x1.2562 ranks=4 duration=1_00:00:00
export ZS_HISTORY_INTERVAL=6:00:00

bash "$JW_PREPARE" $mesh $ranks
mkdir -p "$root"
cp "$MPAS_BUILD/BUILD_INFO" "$root/"
run() { bash "$here/run_zonal.sh" "$root" "$@" || echo "$*" >> "$root/failed"; }
run $mesh 30 trsk $ranks $duration
run $mesh 30 trsk $ranks $duration nodiss
run $mesh 30 trsk $ranks $duration dt=0.5
run $mesh 15 trsk $ranks $duration
run $mesh-ncar 30 trsk $ranks $duration
run $mesh 30 consistent-vke $ranks $duration
bash "$JW_RUN" python3 "$here/check_zonal.py" "$root" | tee "$root/summary.txt"
[ ! -f "$root/failed" ] || { echo "failed runs:"; cat "$root/failed"; exit 1; } >&2
