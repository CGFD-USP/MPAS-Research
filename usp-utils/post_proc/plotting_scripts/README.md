# MPAS visualization & validation

Lightweight tools for quick visual inspection of MPAS NetCDF outputs **on the
native (Voronoi) grid** — no regridding required. Meant for fast diagnostics and
for **validating a run as you build it up** (grid → static → initial conditions →
surface forcing → model output). For publication-quality figures, adapt the code.

Two complementary tools:

| Tool | View | Use it for |
|------|------|-----------|
| [`mpas_viz.py`](#reference--mpas_vizpy-map-view--animation) | **map** (top-down) | fields on the mesh; still images **and** animations |
| [`mpas_cross_section.py`](#reference--mpas_cross_sectionpy-vertical-cross-sections) | **cross-section** (side) | vertical levels, terrain and 3D fields along a transect |

> `mpas_plot.py` and `mpas_animate.py` still exist as **thin backward-compatible
> shims** that forward to `mpas_viz.py`. Prefer `mpas_viz.py` in new work.

## Environment

```bash
conda activate cgfd-usp-mpas
```

Relies on `xarray`, `numpy`, `matplotlib`, `cartopy` and `tqdm`. **Animations to
`.mp4` need FFmpeg** — `conda install -c conda-forge ffmpeg` (or `pip install
imageio-ffmpeg`) — otherwise both `mpas_viz.py` and `mpas_cross_section.py` exit
with a clear error naming the missing dependency. No FFmpeg? Output `.gif`
instead (needs only Pillow, already in the env).

---

# Validation walkthrough

A copy-paste guide to sanity-check each stage of a simulation. **Fill in the
variables once**, then paste each step as you reach it. Every step says *what*
you are checking and *what a healthy result looks like*.

## 0. Set up your shell variables

```bash
# --- edit these ---
export RUN=/path/to/your/run       # directory holding the run's .nc files
export MESH=your_mesh_name         # mesh basename (the <MESH> in <MESH>.grid.nc)

# Zoom box (-lat/-lon). Use it for a limited-area run, OR to focus on a region of
# a global / variable-resolution mesh. For a full global view, set BOUNDS="".
export LATMIN=-8;  export LATMAX=7
export LONMIN=-55; export LONMAX=-32
export BOUNDS="-lat_min $LATMIN -lat_max $LATMAX -lon_min $LONMIN -lon_max $LONMAX"

# Where to slice vertical cross-sections (a latitude and a longitude in-domain)
export TLAT=-1
export TLON=-45
```

> On fine meshes each map is one fill per cell and can take a while. Keep
> `-g no` (no cell edges), use the `$BOUNDS` zoom, and lower `--dpi` for previews.

> Instead of `$BOUNDS`, `mpas_viz.py` also accepts **`--auto-extent`**, which
> frames the map to the mesh footprint (or a masked field's valid region)
> automatically — handy for regional meshes. `mpas_cross_section.py` always
> auto-frames its locator inset.

## 1. Horizontal grid — location, shape, resolution

*After creating the mesh.* Confirms the grid sits where you expect and that the
refinement is where you want it (for regional meshes, that the patch is in the
right place and shape).

```bash
# Cell resolution (km) on the native grid
python mpas_viz.py -f $RUN/$MESH.grid.nc -v resolution -g no $BOUNDS \
    -o $RUN/check_01_resolution.png
```

**Look for:** the mesh outline in the right region; resolution values matching the
intended coarse/fine areas. On coarse meshes add `-g yes` to see individual cells.

## 2. Terrain — after static-field processing

*After `init_atmosphere` static processing.* Confirms topography was interpolated
onto the mesh sensibly (coastlines, mountains in the right places).

```bash
python mpas_viz.py -f $RUN/$MESH.static.nc -v ter -g no $BOUNDS \
    -o $RUN/check_02_terrain.png
```

**Look for:** terrain following real orography; no NaN holes or obvious seams.

## 3. Vertical grid + initial conditions

*After `init_atmosphere` generates `*.init.nc`.* Confirms the vertical coordinate
and the initial state.

```bash
# 3a. Vertical LEVEL STRUCTURE + terrain along a transect (side view)
python mpas_cross_section.py -f $RUN/$MESH.init.nc --levels-only \
    --lat $TLAT --zmax 6000 -o $RUN/check_03a_levels.png

# 3b. Initial potential temperature cross-section
python mpas_cross_section.py -f $RUN/$MESH.init.nc -v theta \
    --lat $TLAT --zmax 15000 -o $RUN/check_03b_theta_init.png

# 3c. An initial field on the map (surface_pressure; also try relhum, skintemp/sst if present)
python mpas_viz.py -f $RUN/$MESH.init.nc -v surface_pressure -g no $BOUNDS \
    -o $RUN/check_03c_sfcpres_init.png
```

**Look for:** (3a) levels hugging the terrain near the surface and flattening
aloft, no crossing interfaces; (3b) θ increasing monotonically with height;
(3c) a physically plausible field. Run `mpas_cross_section.py -f $RUN/$MESH.init.nc`
(no `-v`) to list all colorable 3D variables.

## 4. Surface forcing — SST / sea ice

*If your run reads a surface-update file.* Confirms the SST (and sea-ice)
sequence looks right over the ocean.

```bash
# Inspect the surface-update timeline
python mpas_viz.py -f $RUN/$MESH.sfc_update.nc --list-times

# SST at the first step, land masked (connectivity + landmask from static)
python mpas_viz.py -f $RUN/$MESH.sfc_update.nc -v sst -gf $RUN/$MESH.static.nc \
    -g no -ml yes -t 0 $BOUNDS -o $RUN/check_04_sst.png
```

**Look for:** realistic SST gradients over the ocean; land correctly blanked with
`-ml yes`.

## 5. Model output — maps, animations, cross-sections

*While/after the model runs.* Validate the evolving fields.

```bash
# 5a. Inspect the output timeline (diag or history)
python mpas_viz.py -f "$RUN/diag.*.nc" --list-times

# 5b. Discover output variables (point at any single output file)
python mpas_viz.py -f "$RUN/diag.<TIMESTAMP>.nc"

# 5c. Animate MSLP over the whole run (parallel, no edges)
python mpas_viz.py -f "$RUN/diag.*.nc" -v mslp -gf $RUN/$MESH.static.nc \
    -g no -j -1 --fps 8 $BOUNDS -o $RUN/mslp_anim.mp4

# 5d. Snapshot cross-section: theta + transect-relative wind from a history file
python mpas_cross_section.py -f $RUN/history.<TIMESTAMP>.nc -gf $RUN/$MESH.init.nc \
    -v theta --lat $TLAT -u uReconstructZonal -v_wind uReconstructMeridional -w w \
    --zmax 12000 -o $RUN/xsec_theta_wind.png

# 5e. Animate a cross-section across the run (several steps -> .mp4/.gif)
python mpas_cross_section.py -f "$RUN/history.*.nc" -gf $RUN/$MESH.init.nc \
    -v theta --lat $TLAT --zmax 15000 --fps 8 -o $RUN/xsec_theta.mp4
```

**Look for:** systems tracking and evolving as expected; winds and vertical motion
consistent with the temperature/pressure structure. Both `mpas_viz.py` and
`mpas_cross_section.py` animate when several time steps are selected — test a short
range first (`--tstart 0 --tend 4`) before rendering the whole run.

> **Always quote glob patterns** (`"$RUN/diag.*.nc"`) so the *script* expands
> them, not the shell.

---

# Reference — `mpas_viz.py` (map view & animation)

`mpas_viz.py` draws a **still image** when one time step is selected, or an
**animation** when more than one is. Both modes share the same options.

## The time model: one timeline

All input files are expanded into a single, ordered **timeline** of
`(file, time_index)` entries — whether time is spread across many single-step
files (`history.*.nc`) **or** held in one multi-step file (`x1.*.sfc_update.nc`).

```bash
python mpas_viz.py -f x1.10242.sfc_update.nc --list-times
```

Select a sub-range with `--tstart`/`--tend` (global indices, **inclusive**):

- **1** step selected → still image (`.png`, `.pdf`, …)
- **>1** steps selected → animation (`.mp4`, `.gif`)

Omit `--tstart/--tend` to take the whole timeline. **For a single map from a
multi-step file**, pick one step with `-t N` (index from `--list-times`):

```bash
python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
    -g no -ml yes -t 0 -o sst.png
```

## Discover variables

Omit `-v/--var` to print a table of plottable variables and exit:

```bash
python mpas_viz.py -f x1.10242.sfc_update.nc
```

## The grid file (`-gf`) vs the edge switch (`-g`)

Many MPAS files (`sfc_update`, `diag`, some `history`) **do not carry the mesh
connectivity** (`verticesOnCell`, `nEdgesOnCell`, …). Supply a file that does —
`*.grid.nc`, `*.static.nc` or `*.init.nc` — via **`-gf/--gridfile`**. A
`*.static.nc`/`*.init.nc` also carries `landmask`, needed by `--mask-land`.

⚠️ **`-g/--grid` is NOT the grid file** — it is only the yes/no switch for drawing
cell edges. Passing a file to `-g` is a common slip; the script detects it and
points you to `-gf`.

## Examples

```bash
# Still SST map, masking land
python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
    -g no -ml yes -o sst.png

# Animate SST across all 6 steps of a single multi-time file
python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
    -g no -ml yes --tstart 0 --tend 5 -o sst.gif

# Animate surface pressure across many history files, in parallel
python mpas_viz.py -f "history.*.nc" -v surface_pressure -j 4 -o mslp.mp4

# 3D field at a vertical level
python mpas_viz.py -f "history.*.nc" -v theta -l 10 -o theta.mp4

# Wind vectors over a field
python mpas_viz.py -f "history.*.nc" -v theta -l 10 \
    -u uReconstructZonal -v_wind uReconstructMeridional -o wind.mp4

# Zoom to a region
python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
    -lat_min -40 -lat_max 0 -lon_min -70 -lon_max -20 -o sst_zoom.png

# Custom color scale + colormap
python mpas_viz.py -f "history.*.nc" -v surface_pressure \
    --vmin 90000 --vmax 103500 --cmap viridis -o mslp.mp4

# Total precipitation (sum) and precip rate (sum + deaccumulate)
python mpas_viz.py -f "history.*.nc" --sum-vars "rainc+rainnc" -o total_precip.mp4
python mpas_viz.py -f "history.*.nc" --sum-vars "rainc+rainnc" --deaccumulate -o precip_rate.mp4
```

## Options

**Input / output**
- `-f, --infile` / `--files`: MPAS file or glob pattern — **required**
- `-o, --outfile`: image (1 step) or video (many); omit to show a still interactively
- `-v, --var`: variable to plot (omit to list variables)

**Variable operations**
- `--sum-vars`: sum two variables, e.g. `rainc+rainnc`
- `--deaccumulate`: plot differences between consecutive steps (accumulated → rate)
- `-l, --level`: vertical level (3D fields)

**Time**
- `--tstart, --tend`: timeline range, inclusive (aliases: `--tmin`, `--tmax`)
- `-t, --time`: single timeline index (one still image)
- `--list-times`: print the timeline and exit

**Mesh / mask**
- `-gf, --gridfile`: file providing mesh connectivity (and `landmask`)
- `-g, --grid`: draw cell edges (`yes`/`no`)
- `-ml, --mask-land`: hide land cells (`yes`/`no`; ocean-only fields like `sst`)

**Color**
- `--cmap`: colormap (default `Spectral_r` — red = higher values)
- `--vmin, --vmax`: color-scale limits
- `--extend`: colorbar extend (`both`/`neither`/`min`/`max`)
- `-c, --clip`: clip extremes at mean ± 4σ (`yes`/`no`)

**Map**
- `-lat_min, -lat_max, -lon_min, -lon_max`: geographic zoom box
- `--auto-extent`: auto-frame the map to the mesh footprint (or the non-NaN
  region of the field) instead of global — a hands-off `$BOUNDS` for regional
  meshes and masked fields (`sst`); explicit `-lat_min/...` still take priority
- `--no-coastlines`: hide coastlines

**Wind vectors**
- `-u, --u_wind` / `-v_wind, --v_wind`: wind components (optional overlay)
- `--stride`: plot every Nth vector (default 15)

**Animation**
- `--fps`: frames per second (default 5)
- `--dpi`: output resolution (default 150)
- `-j, --jobs`: parallel frame workers (default 1; `-1` = all CPUs)

## Legacy commands

The old two-script interface still works through the shims:

| Old | Now equivalent to |
|-----|-------------------|
| `mpas_plot.py -f file.nc -v sst -t 0 -o sst.png` | `mpas_viz.py … -t 0 …` (one step → still) |
| `mpas_animate.py -f "h.*.nc" -v p --tmin 0 --tmax 10 -o a.mp4` | `mpas_viz.py … --tstart 0 --tend 10 …` |

⚠️ **One behavior change:** `--tend` is **inclusive**, whereas the old `--tmax`
was an exclusive slice bound. Out-of-range indices are clamped.

## Performance & troubleshooting

- DPI: 80–100 for fast previews, 150 general use, 300+ for publication.
- `-g no` (no cell edges) is faster on high-resolution meshes; `-j 4`/`-j -1`
  renders animation frames in parallel.
- Missing connectivity → supply `-gf` (`*.static.nc`/`*.init.nc`/`*.grid.nc`).
- `--mask-land` does nothing → the file/grid lacks `landmask`; pass a static/init via `-gf`.
- FFmpeg missing → `conda install -c conda-forge ffmpeg`, or output `.gif`.
- Variable not found → list with `mpas_viz.py -f file.nc` (no `-v`).

Typical variables — surface: `surface_pressure`, `sst`, `mslp`, `rainnc`, `rainc`;
3D: `theta`, `pressure`, `qv`, `uReconstructZonal`, `uReconstructMeridional`.

---

# Reference — `mpas_cross_section.py` (vertical cross-sections)

A **side view**: sample the model cells nearest to a transect line and draw them
against the native vertical coordinate (`zgrid` interfaces, metres MSL), with the
terrain (`ter`) filled underneath. Like `mpas_viz.py`, it draws a **still image**
for one time step and an **animation** when several are selected. Two modes:

- **`--levels-only`** — show the vertical **level structure** (`zgrid` interfaces)
  plus terrain along the transect, *without any field* (to "see the levels").
- **`-v <field>`** — **color a 3D field** (`theta`, `qv`, `rho`, …) along the
  transect, height on the vertical axis, terrain filled at the bottom.

The vertical grid `zgrid` is produced by `init_atmosphere` and lives **only in
`*.init.nc`** (a `*.static.nc` has `ter` but not `zgrid`). Pass the init file with
**`-gf`** when the plotted file itself lacks `zgrid`/`ter` (e.g. `history` files).

A small **cartopy locator inset** (top-left) shows where the transect sits, as a
red line on a coastline map. Its extent is set automatically from the mesh
footprint, so a regional mesh is framed without any manual bounds; disable it
with `--no-inset`.

## Defining the transect (pick exactly one)

- `--start "lat,lon" --end "lat,lon"` — two end points
- `--lat <value>` — constant-latitude line (spans the mesh's longitude range)
- `--lon <value>` — constant-longitude line (spans the mesh's latitude range)

Cells are nearest-neighbour sampled along `--npoints` points (default 500);
consecutive duplicates are collapsed and columns are placed at their accumulated
great-circle distance. Sample points **outside** a regional mesh are detected (via
the mesh resolution) and skipped, so an off-domain transect is not silently
snapped onto boundary cells.

The transect geometry is fixed in time, so it is resolved once and only the
field/wind are re-read per frame — inspect the timeline with `--list-times` and
sub-select with `--tstart/--tend` (inclusive), exactly as in `mpas_viz.py`.

## Examples

Replace `<MESH>` with your mesh basename; quote glob patterns.

```bash
# List the colorable 3D (nVertLevels) variables
python mpas_cross_section.py -f <MESH>.init.nc -gf <MESH>.init.nc

# See the vertical levels + terrain along a 2-point transect
python mpas_cross_section.py -f <MESH>.init.nc -gf <MESH>.init.nc \
    --levels-only --start "-5,-52" --end "4,-36" -o levels.png

# Color potential temperature along a constant-latitude transect, capped at 15 km
python mpas_cross_section.py -f <MESH>.init.nc -gf <MESH>.init.nc \
    -v theta --lat 0 --zmax 15000 -o theta_xsec.png

# Water vapor along a constant-longitude transect, vertical axis as level index
python mpas_cross_section.py -f <MESH>.init.nc -gf <MESH>.init.nc \
    -v qv --lon -45 --by-index -o qv_xsec.png

# Wind decomposed relative to the transect (needs cell-centered reconstructed
# winds — from diag/history — and optionally w)
python mpas_cross_section.py -f history.nc -gf <MESH>.init.nc -v theta \
    --lat -1 -u uReconstructZonal -v_wind uReconstructMeridional -w w \
    --zmax 12000 -o theta_wind.png

# Animate the transect across many output files (several steps -> .mp4/.gif)
python mpas_cross_section.py -f "history.*.nc" -gf <MESH>.init.nc \
    -v theta --lat -1 --zmax 15000 --fps 8 -o theta_xsec.mp4
```

## Wind decomposed relative to the transect

Passing `-u`/`-v_wind` (cell-centered zonal/meridional wind) overlays the wind
**decomposed relative to the transect orientation**, following standard
meteorological practice:

- **In-plane arrows** — the (along-transect, vertical) circulation. The
  along-transect component points towards the right (transect end); adding `-w`
  tilts the arrows with vertical motion. Because `w` (≈cm/s) is tiny next to the
  horizontal wind and the axes are km × m, `w` is multiplied by `--w-exag`
  (default 100) so the tilt is visible — **the tilt is qualitative**.
- **Normal-component symbols** — the flow across the section: a **filled dot in a
  circle (⊙)** for wind coming **towards the viewer** (out of the page) and a
  **cross (⊗)** for wind going **away** (into the page); symbol size ∝ magnitude.
  For a W→E transect this means a **north** wind reads as ⊙ and a **south** wind
  as ⊗ (the normal direction is recomputed for any transect orientation).

The reconstructed cell-centered winds (`uReconstructZonal`/`uReconstructMeridional`)
and `w` come from `diag`/`history` output — the `*.init.nc` does not carry them
(it has edge-normal `u` and `w` only). Use `--wind-stride`/`--wind-lstride` to
thin the symbols on fine meshes.

## Options

Color options (`--cmap` default `Spectral_r`, `--vmin/--vmax/-c/--extend`) and
`-t/--time` behave as in `mpas_viz.py`.

**Transect / vertical axis**
- `--start` / `--end` / `--lat` / `--lon`: transect definition (pick one mode)
- `--npoints`: samples along the line (default 500; raise for fine meshes)
- `--levels-only`: draw `zgrid` interfaces + terrain, no field (time-independent)
- `--by-index`: vertical axis as level index instead of height (m)
- `--zmax`: cap the vertical axis at this height (m); the color scale then uses
  only the visible part so upper-level values don't wash out the plot
- `--no-inset`: do not draw the cartopy location mini-map (auto-framed to the mesh)

**Time / animation**
- `--list-times`: print the timeline and exit
- `--tstart, --tend`: timeline range, inclusive (aliases: `--tmin`, `--tmax`);
  one step → still image, several → animation
- `-t, --time`: single timeline index (shortcut for one still)
- `--fps`: animation frames per second (default 5)

**Wind overlay** (decomposed relative to the transect)
- `-u, --u_wind` / `-v_wind, --v_wind`: cell-centered zonal / meridional wind — enables the overlay
- `-w, --w_wind`: vertical velocity (e.g. `w`); tilts the in-plane arrows
- `--w-exag`: vertical exaggeration applied to `w` for the arrow tilt (default 100)
- `--wind-stride` / `--wind-lstride`: draw a symbol every Nth column / level

> When `--zmax` caps the view, prefer it over `-c/--clip` for fields that grow
> strongly with height (e.g. `theta`): the scale is taken from what's shown.

---

## Authors

Originally adapted by Danilo Couto de Souza (2023), with edits by P. Peixoto,
F.A.V.B. Alves and G. Torres Mendonça. Unified `plot`+`animate` framework
(`mpas_viz.py`) and the vertical cross-section tool (`mpas_cross_section.py`):
Danilo Couto de Souza (2026).
