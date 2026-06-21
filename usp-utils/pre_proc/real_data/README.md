# `real_data/` — GFS / ERA5 → WPS intermediate met files for MPAS

Scripts to fetch meteorological data and turn it into the **WPS intermediate-format**
file (`GFS:` or `ERA5:` `YYYY-MM-DD_HH`) that `init_atmosphere` reads to build the
real-data `init.nc`. MPAS has no built-in ungrib, so this is done in Python with
**pywinter** — no need to build WPS/ungrib.

```
download_gfs.py   →  GFS GRIB2    →  gfs_to_intermediate.py   →  GFS:YYYY-MM-DD_HH
download_era5.py  →  ERA5 GRIB    →  era5_to_intermediate.py  →  ERA5:YYYY-MM-DD_HH
```

Each source writes its own prefix — GFS → `GFS:`, ERA5 → `ERA5:` — which is the
`config_met_prefix` you set in `namelist.init_atmosphere`. The field names and the
rest of the setup are identical either way; only the prefix differs.
This directory only produces that **met intermediate file** — running
`init_atmosphere` with it (namelist, streams, linking `*.static.nc`, etc.) is covered
by the model usage tutorial, not repeated here. Run these after the static fields
are ready (see `../static_fields/`).

## Which source? (data availability)

Two products feed init_atmosphere: the **atmosphere** (3D state → `GFS:`/`ERA5:`
intermediate, init case 7) and the **SST/sea-ice** lower boundary (→ `SST:`
intermediate, init case 8,
see "SST / sea-ice update").

**Atmosphere:**

| Source | Coverage | Resolution | Notes |
|---|---|---|---|
| GFS `--source aws` (default) | **2021-03-23 → present** | 0.25° | S3 byte-range subset, no rate limit |
| GFS `--source nomads` | **last ~10 days** | 0.25/0.5/1° | grib_filter; can hit `Over Rate Limit` |
| GFS `--source rda` | **2015-01-15 → present** | 0.25° | NCAR RDA ds084.1, full files; may need a free RDA account |
| ERA5 (`download_era5.py`) | **1940 → present** | 0.25° | Copernicus CDS; needs a CDS account |

**SST / sea-ice:**

| Source | Coverage | Notes |
|---|---|---|
| GFS (`gfs_sst_to_intermediate.py`, or `--fields sst`) | same as GFS above | from the GFS GRIB; analysis **or** forecast |
| OISST observed (`download_oisst.py`) | **1981-09-01 → present** | NOAA OI SST v2.1 daily 0.25° (NCEI) |
| OISST climatology (`oisst_clim_to_intermediate.py`) | **any date** (LTM 1991-2020) | day-of-year climatology via OPeNDAP; for forecasts / typical-month runs |

### GFS is a *forecast* model — analysis vs forecast
GFS runs four times a day, at **00, 06, 12 and 18 UTC**. Each of those runs is a
**cycle**: `--cycle 00` selects the 00 UTC run of `--date`. Within a cycle, `--fhour`
is the **forecast hour** (lead time, in hours after the cycle time).

A cycle produces an **analysis** at forecast hour 0 (`--fhour 0`, the default) and
**forecasts** at later hours (`--fhour 3, 6, … up to 384`, i.e. 16 days). So:
- **Analysis** (`--fhour 0`) = best estimate of the atmosphere *at the cycle time*. Use it
  for the initial conditions. Only exists for the past (and the current cycle).
- **Forecast** (`--fhour > 0`) = a prediction for times *after* the cycle, i.e. it can give
  data for the **future** (times that have not happened yet) — that is what makes an
  operational MPAS forecast possible.

By contrast **ERA5 (reanalysis) and OISST observed only exist for the past.** For the
future (or any date with no observed SST) use the **OISST climatology**.

There is **no GFS 0.25° before 2015-01-15** — for anything older, use ERA5 (atmosphere)
and OISST (SST). `download_gfs.py` fails fast with the exact limit for out-of-range dates.

## Scripts

| Script | What it does |
|--------|--------------|
| `download_gfs.py` | Downloads the GFS fields/levels MPAS needs, with a `*.provenance.json`. Sources `aws` / `nomads` / `rda` (see table above). `--fields sst` for a small surface-only (SST update) download. |
| `gfs_to_intermediate.py` | Converts one GFS GRIB2 file to a WPS intermediate file via pywinter. Flips latitude to S→N, writes pressure in **Pa**, prints the level count for `config_nfglevels`. |
| `download_era5.py` | Downloads ERA5 pressure- and single-level GRIB via the CDS API (cdsapi), with provenance. For dates GFS can't reach. |
| `era5_to_intermediate.py` | ERA5 counterpart of the GFS converter (same intermediate field names; handles geopotential→height and snow units). |
| `download_oisst.py` | Downloads NOAA OISST v2.1 daily 0.25° SST/sea-ice NetCDF (NCEI) over a date range. For SST update files (scientific pipeline). |
| `oisst_to_intermediate.py` | Converts OISST daily files to `SST:` intermediate files (SST→K, SEAICE, LANDSEA) — one per day. |
| `oisst_clim_to_intermediate.py` | Builds `SST:` files from the OISST daily **climatology** (LTM 1991-2020, via OPeNDAP) for target dates with no observed SST (forecasts / typical-month runs). |
| `gfs_sst_to_intermediate.py` | Extracts SST/SEAICE/LANDSEA from a GFS GRIB into an `SST:` intermediate file (operational SST update). |

One-shot wrappers (download + convert in one call, inside the conda env):

| Wrapper | Covers |
|---------|--------|
| `prepare_gfs.sh` | GFS atmosphere and/or SST — `--product atm` (default), `sst`, or `both` (one download, both products). |
| `prepare_era5.sh` | ERA5 atmosphere (download pl+sl → `ERA5:` intermediate). |
| `prepare_oisst.sh` | OISST SST over a date range — observed (default) or `--climatology` (→ daily `SST:` intermediates). |

## Dependencies

The `cgfd-usp-mpas` conda env: `cfgrib` + `eccodes` (conda-forge) and `pywinter`
(pip); plus `cdsapi` (pip) for the ERA5 path. Run with
`conda run -n cgfd-usp-mpas python <script>.py ...`, or use the `prepare_*.sh` wrappers.
ERA5 also needs a CDS account and `~/.cdsapirc`
(https://cds.climate.copernicus.eu/how-to-api); RDA may need a free account at
https://rda.ucar.edu (set `RDA_API_TOKEN`). Never hard-code credentials.

## Recipes (by use case)

Step-by-step data-prep recipes live in [`recipes/`](recipes/). Pick by **what you
simulate** (future vs past) and **mesh type** (global vs regional — regional needs
lateral boundary data):

| | Global mesh | Regional mesh (LBCs) |
|---|---|---|
| **Operational forecast** (future) | [operational_global](recipes/operational_global.md) | [operational_regional](recipes/operational_regional.md) |
| **Hindcast / case study** (past) | [hindcast_global](recipes/hindcast_global.md) | [hindcast_regional](recipes/hindcast_regional.md) |

In one line each:
- **Operational** → atmosphere from GFS **analysis**; future SST from GFS **forecast**
  hours or OISST **climatology** (the future has no observed SST).
- **Hindcast** → atmosphere from **ERA5** (or recent GFS analysis); SST from **OISST
  observed** daily.
- **Regional** adds lateral-boundary data at a cadence (GFS forecast hours, or ERA5 6-hourly).

Minimal examples:
```sh
./prepare_gfs.sh   --date 2026-06-16 --cycle 00 --product both   # operational, global
./prepare_era5.sh  --date 2014-09-10 --time 00                   # hindcast atmosphere
./prepare_oisst.sh --start 2014-09-10 --end 2014-09-15           # hindcast SST (daily)
```

> **SST for an N-day forecast:** `--product both` gives SST only at the *initial* time.
> Short forecasts usually hold SST fixed (`config_sst_update=.false.`). To evolve it,
> loop GFS forecast hours (`--product sst --fhour 024 048 …`, each tagged with its valid
> date) or use the OISST climatology — see [operational_global](recipes/operational_global.md).

Calling the Python scripts directly (instead of the wrappers) lets you inspect each stage;
every `download_*.py` prints the exact next command. Output goes under `<repo>/met_data/`
(`gfs/`, `era5/`, `oisst/`, `oisst_clim/`) by default; `--outdir` changes it.

Key options:
- `download_gfs.py`: `--date YYYY-MM-DD`, `--cycle {00,06,12,18}` (UTC run hour),
  `--fhour` (forecast lead time in hours; 0 = analysis), `--res {0p25,0p50,1p00}`,
  `--source {aws,nomads,rda}`,
  `--fields {full,sst}` (`sst` = small surface-only download for SST update files),
  `--outdir`.
- `download_era5.py`: `--date YYYY-MM-DD`, `--time HH`, `--area N W S E` (default
  global), `--outdir`. **`--area` subsets only the *download*, not the simulated
  region** (that is the mesh): use it for a regional run to keep a long LBC series
  small, sized as the regional mesh extent **+ a margin** (order `N W S E`, degrees,
  lon −180..180; W/E negative over Brazil). For a global mesh, omit it. See
  [hindcast_regional](recipes/hindcast_regional.md) for a worked example (single
  month to multiple years).
- `download_oisst.py` / `oisst_to_intermediate.py`: `--start`/`--end` date range,
  `--hour HH`, `--outdir`.
- `oisst_clim_to_intermediate.py` (climatology): `--start`/`--end` target dates,
  `--hour HH`, `--outdir` (no download — reads the LTM over OPeNDAP).
- converters: `--outdir`, `--prefix` (default `GFS` for the GFS converter, `ERA5`
  for the ERA5 converter, `SST` for SST); GFS uses `--grib`, ERA5 uses `--pl`/`--sl`.

The converter sets the date tag from the data's valid time, so the date part of the
output name (`<prefix>:YYYY-MM-DD_HH`) is what `config_start_time` must match.

## Verify the init.nc (recommended after every run)

A clean `init_atmosphere` run does **not** guarantee a usable initial state — it can
finish with "0 errors" and still write a physically broken `init.nc` (e.g. from a
units/interpolation problem upstream), which then blows up the model (`w → NaN`) on
the first step. After building the `init.nc`, sanity-check the **prognostic** state:

```python
import numpy as np, xarray as xr
ds = xr.open_dataset("x1.10242.init.nc")
Rd, cp = 287.0, 1004.5; cv = cp - Rd; gamma = cp/cv; p0 = 1e5
th, rho = ds["theta"].values[0,:,0], ds["rho"].values[0,:,0]   # surface level
print("theta surf:", th.min(), th.max())   # expect ~270–320 K  (NOT ~1100)
print("rho   surf:", rho.min(), rho.max())  # expect ~1.0–1.3    (NOT ~0.01)
p = p0*(Rd*rho*th/p0)**gamma / 100.0        # EOS pressure from prognostic state
print("EOS(prognostic) hPa:", p.mean())     # expect ~950–1010 hPa (NOT ~10)
```
`rho_base`/`theta_base` and `surface_pressure` can look fine even when the
prognostic `theta`/`rho` are broken, so check `theta`/`rho` specifically.

## Field mapping (GRIB → WPS intermediate)

Both converters emit the same intermediate field names (WPS GFS Vtable):

| Field | Intermediate | Kind | GFS source | ERA5 source |
|-------|--------------|------|------------|-------------|
| geopotential height | `GHT`     | 3D / pressure | HGT       | z / g0 |
| temperature         | `TT`      | 3D / pressure | TMP       | t |
| wind u / v          | `UU`/`VV` | 3D / pressure | UGRD/VGRD | u / v |
| relative humidity   | `RH`      | 3D / pressure | RH        | r |
| mean sea level pres.| `PMSL`    | 2D            | PRMSL     | msl |
| surface pressure    | `PSFC`    | 2D            | PRES sfc  | sp |
| terrain height      | `SOILHGT` | 2D            | HGT sfc   | z(sfc) / g0 |
| skin temperature    | `SKINTEMP`| 2D            | TMP sfc   | skt |
| land-sea mask       | `LANDSEA` | 2D            | LAND      | lsm |
| sea-ice fraction    | `SEAICE`  | 2D            | ICEC      | ci (a.k.a. siconc) |
| snow water equiv.   | `SNOW`    | 2D            | WEASD     | sd × 1000 |
| soil temperature    | `ST<tag>` | 2D (4 layers) | TSOIL     | stl1–4 |
| soil moisture       | `SM<tag>` | 2D (4 layers) | SOILW     | swvl1–4 |

Soil layer tags are the source's actual layer depths (GFS: `000010/010040/040100/
100200`; ERA5: `000007/007028/028100/100289`, cm). All fields share the global
regular lat/lon grid; pywinter takes the geometry once (`Geo0`).

## SST / sea-ice update files

For runs longer than a day or two you usually want the lower boundary (SST and
sea ice) to evolve in time instead of staying fixed at the initial value. MPAS
supports this with a **surface update file** (`x1.<mesh>.sfc_update.nc`), built
independently of the atmospheric initial conditions. Two sources here:

- **Operational** (GFS atmosphere): `gfs_sst_to_intermediate.py` — reuses the GFS
  GRIB you already downloaded (SST = surface skin temperature, SEAICE = ICEC,
  LANDSEA = LAND).
- **Scientific / downscaling** (ERA5 atmosphere): `download_oisst.py` +
  `oisst_to_intermediate.py` — NOAA OISST v2.1 daily 0.25° (an independent,
  reference daily SST that matches the 0.25° atmosphere resolution).

The whole flow has three steps:

**1. Build `SST:YYYY-MM-DD_HH` intermediate files** (fields `SST`, `SEAICE`,
`LANDSEA`), one per update time:
```sh
# operational (GFS), SST only — lightweight: downloads just the surface
# SST/sea-ice/land fields (~1 MB, not the full GFS), then converts:
./prepare_gfs.sh --date 2026-06-11 --product sst
#   by hand:
python download_gfs.py --date 2026-06-11 --fields sst        # -> *.f000.sst (~1 MB)
python gfs_sst_to_intermediate.py --grib <the .f000.sst file>
# (if you already downloaded the full GFS for the atmosphere, just convert it:
#  python gfs_sst_to_intermediate.py --grib <the .f000 file>)

# scientific (OISST): daily files over the run period
./prepare_oisst.sh --start 2014-09-01 --end 2014-09-30
#   by hand:
python download_oisst.py --start 2014-09-01 --end 2014-09-30
python oisst_to_intermediate.py --indir <repo>/met_data/oisst --start 2014-09-01 --end 2014-09-30
```
> `download_gfs.py --fields sst` writes a distinct `*.f000.sst` file (only TMP/ICEC/
> LAND at the surface), so it never collides with a full atmosphere download in the
> same directory. `--product both` downloads the full GFS once and makes both
> `GFS:` and `SST:`.

**2. Run `init_atmosphere` in case 8** to interpolate them onto the mesh and write
`x1.<mesh>.sfc_update.nc`. Key `namelist.init_atmosphere` settings (static fields
already done; reuse the same mesh `*.static.nc`):
```
&nhyd_model       config_init_case = 8
                  config_start_time = 'YYYY-MM-DD_HH:00:00'
                  config_stop_time  = 'YYYY-MM-DD_HH:00:00'   ! end of the run
&dimensions       config_nsoillevels = 4
&data_sources     config_sfc_prefix = 'SST'
                  config_fg_interval = 86400                  ! update cadence (s); 86400 = daily
&preproc_stages   config_static_interp = .false.
                  config_vertical_grid = .false.
                  config_met_interp    = .false.
                  config_input_sst     = .true.               ! REQUIRED for case 8
                  config_frac_seaice   = .true.
```
The `surface` output stream writes `x1.<mesh>.sfc_update.nc` at `output_interval`
equal to the cadence; its input stream reads the `*.static.nc`.

**3. Enable the update in the model run** (`namelist.atmosphere`):
```
&physics          config_sst_update = .true.
```
and add an input stream in `streams.atmosphere` reading the update file at the same
cadence:
```xml
<stream name="surface" type="input" filename_template="x1.<mesh>.sfc_update.nc"
        input_interval="86400" >
    <var name="sst"/>
    <var name="xice"/>
</stream>
```

> Notes. `SST` is written in **Kelvin** (OISST is degC → +273.15; GFS skin temp is
> already K). `LANDSEA` is 1 = land / 0 = water; SST over land is a filler and is
> masked out via `LANDSEA`. OISST starts 1981-09-01; very recent days come as
> `_preliminary` files (handled automatically). OISST 0.25° matches the GFS/ERA5
> atmosphere resolution — finer GHRSST products (e.g. MUR 0.01°) are overkill for a
> 120–240 km mesh.

## Known issues / gotchas

- **GFS availability — you can't go arbitrarily far back.** GFS 0.25° only exists
  from **2015-01-15**. `--source aws` covers 2021-03-23+ (when the bucket adopted the
  `gfs.*/atmos/` layout), `--source rda` covers 2015-01-15+ (NCAR RDA ds084.1, full
  files), `--source nomads` only the last ~10 days. `download_gfs.py` checks the date
  against the chosen source and **errors early stating the limit** — a rejected old
  date is expected, not a bug. For pre-2015 use ERA5.
- **ERA5 path is newer and not yet validated end-to-end here.** `download_era5.py`
  and `era5_to_intermediate.py` mirror the validated GFS path, but the ERA5 branch
  hasn't been run through `init_atmosphere` + model in this repo yet. Always run the
  *Verify the init.nc* check. Watch for: geopotential is converted to height (÷ g0),
  snow depth (m w.e.) to kg m⁻² (× 1000), and pressure written in Pa.
- **Credentials.** ERA5 needs `~/.cdsapirc` (CDS account); RDA may need a free account
  and `RDA_API_TOKEN`. If RDA returns a login/HTML page instead of GRIB, the script
  says so — set the token.
- **NOMADS rate limit.** `--source nomads` can return `Over Rate Limit` (temporary IP
  block). Prefer `--source aws`; if hit, wait ~1 h.
- **Pressure units must be Pa.** The WPS intermediate format (and pywinter's `V3dp`)
  expect pressure in **Pa**. Levels arrive from cfgrib as `isobaricInhPa` (hPa), so the
  converters multiply by 100. In hPa, every 3D level would be 100× too low:
  `init_atmosphere` still runs, but `init.nc` gets `theta`/`rho` ~100×/~4× off and the
  model goes `w → NaN`; `surface_pressure` still looks fine (it comes from PSFC/PMSL,
  already in Pa), which makes it sneaky — hence the *Verify the init.nc* check.
- **`config_ztop` vs level coverage.** `config_nfglevels` must equal the value the
  converter prints (isobaric levels + 1). The downloaders ship levels up to 1 hPa
  (~48 km), so `config_ztop=30000` (30 km) works. A dataset that stops lower combined
  with a higher top triggers
  `extrap_type == 2 not implemented for target_z >= zf(1,nz)` — lower `config_ztop`.
