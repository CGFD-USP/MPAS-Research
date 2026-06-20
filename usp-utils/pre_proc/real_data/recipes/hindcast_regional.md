# Recipe — Hindcast / downscaling, regional (limited-area) mesh

**Goal:** prepare the input *data* for a **downscaling / case study** on a **regional**
mesh over a **past** period (the most common scientific use). Like the global hindcast
but with **lateral boundary conditions (LBCs)** from ERA5 through the run. Scope here is
data preparation only.

| What | Source | When |
|------|--------|------|
| Atmosphere initial conditions | **ERA5** | once, at the run start |
| Lateral boundary data | **ERA5** at the LBC cadence | every `N` h across the run |
| SST / sea-ice | **OISST observed** daily | at the update cadence |

## 1. Atmosphere initial conditions
```sh
./prepare_era5.sh --date 2014-09-10 --time 00          # -> GFS:2014-09-10_00
```

## 2. Boundary data through the run (the LBC step consumes these)
One `GFS:` intermediate per boundary time = ERA5 at the LBC cadence (here 6-hourly):
```sh
for d in 2014-09-10 2014-09-11 2014-09-12; do
    for t in 00 06 12 18; do
        ./prepare_era5.sh --date $d --time $t          # GFS:<d>_<t>
    done
done
```
(Optionally pass `--area "N W S E"` to ERA5 to download only a box around the regional
domain and keep the files small.)

## 3. SST / sea-ice over the run (observed, daily)
```sh
./prepare_oisst.sh --start 2014-09-10 --end 2014-09-15
```

## Hand-off to the model
- Initial conditions: `GFS:<init>` → `init_atmosphere` **case 7** (regional `*.static.nc`).
- LBCs: the `GFS:` series at the boundary times → `init_atmosphere` **case 9** →
  `lbc.*.nc`; model `config_apply_lbcs=.true.` + the `lbc` stream.
- SST: `SST:` series → case 8 + `config_sst_update`.
- **Verify the `init.nc`** (README *Verify the init.nc*).

> **Out of scope here (separate tutorial / branch):** creating the limited-area mesh
> (`create_region` from MPAS-Limited-Area) and running `init_atmosphere` case 7/9 and the
> model. This directory only prepares the `GFS:`/`SST:` intermediates those steps read.
