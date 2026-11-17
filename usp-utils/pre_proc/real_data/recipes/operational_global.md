# Recipe — Operational forecast, global mesh

**Goal:** prepare the input *data* for a real-time/near-real-time MPAS forecast on a
**global** mesh (no lateral boundaries). Scope here is data preparation only; the mesh,
the `init_atmosphere` runs and the model run are covered by the model tutorial.

| What | Source | When |
|------|--------|------|
| Atmosphere initial conditions | latest **GFS analysis** (`--fhour 0`) | once, at the forecast start |
| SST / sea-ice | GFS (init time) + GFS forecast or OISST climatology over the window | once, or per update step |

GFS is a forecast model: the analysis (`--fhour 0`) is the best estimate at the cycle
time; forecast hours (`--fhour > 0`) give the **future**. Use the latest available cycle.

## 1. Atmosphere + initial SST (one GFS download)
```sh
./prepare_gfs.sh --date 2026-06-16 --cycle 00 --product both
```
Produces `GFS:2026-06-16_00` (atmosphere) and `SST:2026-06-16_00` (SST/sea-ice) under
`met_data/gfs/2026061600/`.

## 2. SST over the forecast window (only if you update SST)
Short forecasts (≲1 week) usually keep SST **fixed** (`config_sst_update=.false.`) — then
step 1 is enough. To let SST evolve (the future has no observed SST), use either:
```sh
# GFS forecast SST from the same cycle (each fhour -> SST: tagged with its valid date)
for fh in 024 048 072 096 120; do
    ./prepare_gfs.sh --date 2026-06-16 --cycle 00 --product sst --fhour $fh
done
# or the OISST day-of-year climatology for the forecast dates
./prepare_oisst.sh --start 2026-06-17 --end 2026-06-21 --climatology
```

## Hand-off to the model
- `GFS:` → `init_atmosphere` **case 7** (with the global `*.static.nc`) → `x1.*.init.nc`.
- `SST:` → `init_atmosphere` **case 8** → `x1.*.sfc_update.nc`; model `config_sst_update`
  + the `sfc_update` stream. See the README section *SST / sea-ice update*.
- **Verify the `init.nc`** before running the model (README *Verify the init.nc*).

Global mesh ⇒ **no lateral boundary conditions**. Mesh creation and the
`init_atmosphere`/model runs are documented separately (other branch/tutorial).
