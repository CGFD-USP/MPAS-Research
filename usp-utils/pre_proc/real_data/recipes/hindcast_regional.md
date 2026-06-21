# Recipe — Hindcast / downscaling, regional (limited-area) mesh

**Goal:** prepare the input *data* for a **downscaling / case study** on a **regional**
(limited-area) mesh over a **past** period (the most common scientific use). Like the
global hindcast but with **lateral boundary conditions (LBCs)** from ERA5 through the
run. Scope here is data preparation only.

| What | Source | When |
|------|--------|------|
| Atmosphere initial conditions | **ERA5** | once, at the run start |
| Lateral boundary data | **ERA5** at the LBC cadence | every `N` h across the run |
| SST / sea-ice | **OISST observed** daily | at the update cadence |

## The `--area` download box

`--area "N W S E"` restricts the **ERA5 download**, not the simulated region — the
region is the regional mesh (`create_region`, out of scope here). It keeps a long LBC
series small. Size it to the **regional mesh extent (including its relaxation zone)
plus a few degrees of margin** on every side; a box that does not cover the mesh makes
`init_atmosphere` extrapolate or fail at the boundary.

- Order **N W S E**, degrees. Latitude −90..90 (N > S); longitude −180..180 (W/E
  negative over Brazil).
- Brazilian equatorial margin (~5°N–5°S, 52°W–34°W) with buffer: `--area "12 -60 -12 -28"`.
- Global mesh: omit `--area` (download global).

## The run window (month, year, or multiple years)

The same block drives any span — set `START`/`END` and the loops fill it. A single
month, a single year, or several years are just different endpoints:

| Span | `START` | `END` |
|------|---------|-------|
| One month | `2014-09-01` | `2014-09-30` |
| One year | `2014-01-01` | `2014-12-31` |
| Multiple years | `2014-01-01` | `2016-12-31` |

ERA5 is taken 6-hourly (the usual LBC cadence). Downloads skip files already present,
so the loops are resumable and the init time overlapping the first LBC time is free.

```sh
# --- Window: edit these three lines ------------------------------------------
START=2014-09-01                                      # run start (init at START 00z)
END=2014-09-30                                         # last day of the run
AREA="12 -60 -12 -28"                                 # N W S E, mesh + margin

STOP=$(date -u -d "$END +1 day" +%Y-%m-%d)            # day after END (closing LBC)
```

### 1. Atmosphere initial conditions (run start)
```sh
./prepare_era5.sh --date "$START" --time 00 --area "$AREA"     # -> ERA5:<START>_00
```

### 2. Lateral boundary data, 6-hourly across the window
One `ERA5:` intermediate per boundary time (00/06/12/18 every day), plus the **closing
boundary** at `STOP` 00z that the run's stop time needs:
```sh
d="$START"
while [ "$d" != "$STOP" ]; do
    for t in 00 06 12 18; do
        ./prepare_era5.sh --date "$d" --time "$t" --area "$AREA"
    done
    d=$(date -u -d "$d +1 day" +%Y-%m-%d)
done
./prepare_era5.sh --date "$STOP" --time 00 --area "$AREA"      # closing boundary
```
Each day at 6-hourly is 4 boundary times (a small pl+sl GRIB each over the box), so a
30-day month is `30×4 + 1 = 121` and a year is `365×4 + 1`. A finer cadence
(3-hourly/hourly) raises boundary fidelity at more cost and storage; it must match
`config_fg_interval` in the case-9 step (21600 s for 6 h).

### 3. SST / sea-ice over the run (observed, daily)
```sh
./prepare_oisst.sh --start "$START" --end "$END"
```

For long windows, keep CDS requests **serial** (the queue throttles parallel jobs) and
budget disk space — a regional box is small per file, but years × 6-hourly accumulates.
The skip-existing behavior makes the whole window resumable. Download the geog/static
bundle once (see `../../static_fields/`) and reuse it across all years.

## Hand-off to the model
- Initial conditions: `ERA5:<START>_00` → `init_atmosphere` **case 7** (regional `*.static.nc`).
- LBCs: the `ERA5:` series at the boundary times → `init_atmosphere` **case 9** →
  `lbc.*.nc`; model `config_apply_lbcs=.true.` + the `lbc` stream
  (`config_fg_interval` = LBC cadence in seconds).
- SST: `SST:` series → case 8 + `config_sst_update` (see the README *SST / sea-ice
  update files*).
- **Verify the `init.nc`** (README *Verify the init.nc*) — the ERA5 path is not yet
  validated end-to-end here, so this check matters.

> **Out of scope here (separate tutorial / branch):** creating the limited-area mesh
> (`create_region` from MPAS-Limited-Area) and running `init_atmosphere` case 7/9 and the
> model. This directory only prepares the `ERA5:`/`SST:` intermediates those steps read.
