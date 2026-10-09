# Recipe — Operational forecast, regional (limited-area) mesh

**Goal:** prepare the input *data* for an operational MPAS forecast on a **regional**
(limited-area) mesh. A regional run needs, in addition to the global case, **lateral
boundary conditions (LBCs)** through the forecast — and those come from GFS **forecast**
hours of the cycle. Scope here is data preparation only.

| What | Source | When |
|------|--------|------|
| Atmosphere initial conditions | **GFS analysis** (`--fhour 0`) | once, at the start |
| Lateral boundary data | **GFS forecasts** of the same cycle, at the LBC cadence | every `N` h across the forecast |
| SST / sea-ice | GFS or OISST climatology | once, or per update step |

## 1. Atmosphere initial conditions
```sh
./prepare_gfs.sh --date 2026-06-16 --cycle 00 --product atm      # GFS:2026-06-16_00
```

## 2. Boundary data through the forecast (the LBC step consumes these)
One `GFS:` intermediate per boundary-update time = forecast hours of the cycle at the LBC
cadence (here every 6 h out to 120 h):
```sh
for fh in 006 012 018 024 030 036 042 048 ... 120; do
    ./prepare_gfs.sh --date 2026-06-16 --cycle 00 --product atm --fhour $fh
done   # each writes GFS:<valid date_hour> (cycle + fhour)
```

## 3. SST / sea-ice
As in the global recipe (fixed at init, or GFS-forecast / OISST-climatology over the
window): see [operational_global.md](operational_global.md) step 2.

## Hand-off to the model
- Initial conditions: `GFS:<init>` → `init_atmosphere` **case 7** (regional `*.static.nc`).
- LBCs: the `GFS:` series at the boundary times → `init_atmosphere` **case 9** →
  `lbc.*.nc`; model `config_apply_lbcs=.true.` + the `lbc` stream.
- SST: as in the global recipe (case 8 + `config_sst_update`).
- **Verify the `init.nc`** (README *Verify the init.nc*).

> **Out of scope here (separate tutorial / branch):** creating the limited-area mesh
> (`create_region` from MPAS-Limited-Area) and running `init_atmosphere` case 7/9 and the
> model. This directory only prepares the `GFS:`/`SST:` intermediates those steps read.
