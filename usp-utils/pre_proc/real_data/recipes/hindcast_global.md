# Recipe — Hindcast, global mesh

**Goal:** prepare the input *data* to simulate a **past** period on a **global** mesh
(no lateral boundaries) — e.g. a global case study or a multi-month/year run. Scope here
is data preparation only.

| What | Source | When |
|------|--------|------|
| Atmosphere initial conditions | **ERA5** (1940→present) or **GFS analysis** (2015+) | once, at the run start |
| SST / sea-ice | **OISST observed** daily | at the update cadence over the run |

The past has observed data, so use a reanalysis (ERA5) for the atmosphere and the OISST
daily analysis for SST. (For a recent date, 2021-03-23+, GFS analysis works too.)

## 1. Atmosphere initial conditions
```sh
./prepare_era5.sh --date 2010-01-01 --time 00          # -> GFS:2010-01-01_00
#   recent date alternative:
# ./prepare_gfs.sh --date 2023-09-10 --cycle 00 --product atm
```

## 2. SST / sea-ice over the run (observed, daily)
```sh
./prepare_oisst.sh --start 2010-01-01 --end 2012-12-31   # one SST: per day
```
For a "typical" period rather than a specific year, use `--climatology` instead of the
observed range. `config_fg_interval` (case-8 namelist) sets how often MPAS reads SST.

## Hand-off to the model
- `GFS:` → `init_atmosphere` **case 7** (global `*.static.nc`) → `x1.*.init.nc`.
- `SST:` → `init_atmosphere` **case 8** → `x1.*.sfc_update.nc`; model `config_sst_update`
  + the `sfc_update` stream. See README *SST / sea-ice update*.
- **Verify the `init.nc`** (README *Verify the init.nc*) — this catches unit/interpolation
  problems (e.g. the ERA5 path is newer; confirm `theta`/`rho` are physical).

Global mesh ⇒ **no lateral boundary conditions**. Mesh and runs: separate tutorial.
