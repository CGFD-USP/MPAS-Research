# Data-preparation recipes (by use case)

Each recipe lists exactly which data to download and convert (with the scripts in the
parent directory) for one kind of MPAS run. They cover **data preparation only** — the
mesh, the `init_atmosphere` runs (cases 7/8/9) and the model run are covered by the
model tutorial (separate branch/directory).

Pick by **what you simulate** (future vs past) and **mesh type** (global vs regional):

| | Global mesh (no LBCs) | Regional mesh (needs LBCs) |
|---|---|---|
| **Operational forecast** (future) | [operational_global.md](operational_global.md) | [operational_regional.md](operational_regional.md) |
| **Hindcast** (past) | [hindcast_global.md](hindcast_global.md) | [hindcast_regional.md](hindcast_regional.md) |

Quick guide to the choices:
- **Future (operational):** atmosphere from **GFS analysis**; future SST from **GFS
  forecast** hours or **OISST climatology** (the future has no observed SST).
- **Past (hindcast):** atmosphere from **ERA5** (or recent GFS analysis); SST from
  **OISST observed** daily.
- **Regional** additionally needs **lateral boundary** data at a regular cadence
  (GFS forecast hours, or ERA5 at e.g. 6-hourly), which the LBC step (`init_atmosphere`
  case 9) consumes.

See the parent [README](../README.md) for the source/coverage tables, per-script options,
the *SST / sea-ice update* mechanics, and the *Verify the init.nc* check.
