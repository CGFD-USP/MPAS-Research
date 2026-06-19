# MPAS visualization

Lightweight tool for quick, generic visual inspection of MPAS NetCDF outputs
**on the native (Voronoi) grid** — no regridding required. Meant for fast
diagnostics; for publication-quality figures, adapt the code as needed.

`mpas_viz.py` is a **single framework that both plots and animates**: it draws a
still image when one time step is selected, or an animation when more than one
is. Plots and animations share the same options, so a useful flag works for both.

> `mpas_plot.py` and `mpas_animate.py` still exist as **thin backward-compatible
> shims** that forward to `mpas_viz.py` (old commands and `from mpas_plot import …`
> keep working). Prefer calling `mpas_viz.py` directly in new work.

## Environment

```bash
conda activate cgfd-usp-mpas
```

Relies on `xarray`, `numpy`, `matplotlib`, `cartopy` and `tqdm`. Animations need
FFmpeg for `.mp4` (`conda install -c conda-forge ffmpeg`) or use `.gif` (Pillow).

---

## The time model: one timeline

All input files are expanded into a single, ordered **timeline** of
`(file, time_index)` entries. This works whether time is spread across many
single-step files (`history.*.nc`) **or** held in one multi-step file
(`x1.*.sfc_update.nc`).

Inspect it:

```bash
python mpas_viz.py -f x1.10242.sfc_update.nc --list-times
```

Select a sub-range with `--tstart`/`--tend` (global indices, **inclusive**):

- **1** step selected → still image (`.png`, `.pdf`, …)
- **>1** steps selected → animation (`.mp4`, `.gif`)

Omit `--tstart/--tend` to take the whole timeline (so a multi-step file like
`sfc_update` animates by default).

**To get a still image from a file that holds many time steps, pick one step**
with `-t N` (or `--tstart N --tend N`), where `N` is an index from `--list-times`:

```bash
# A single map (step 0) from a multi-time file — not an animation
python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
    -g no -ml yes -t 0 -o sst.png
```

## Discover variables

Omit `-v/--var` to print a table of plottable variables (name, long name, units,
grid, extra dims) and exit:

```bash
python mpas_viz.py -f x1.10242.sfc_update.nc
```

## The grid file (`-gf`) vs the edge switch (`-g`)

Many MPAS files (`sfc_update`, `diag`, some `history`) **do not carry the mesh
connectivity** (`verticesOnCell`, `nEdgesOnCell`, `latitudeVertex`, …). Supply a
file that does — `*.grid.nc`, `*.static.nc` or `*.init.nc` — via **`-gf/--gridfile`**.
A `*.static.nc`/`*.init.nc` also carries `landmask`, needed by `--mask-land`.

⚠️ **`-g/--grid` is NOT the grid file** — it is only the yes/no switch for drawing
cell edges. Passing a file to `-g` is a common slip; the script detects it and
points you to `-gf`.

---

## Examples

```bash
# Still SST map, masking land (connectivity + landmask from static)
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

# Zoom to a region (South Atlantic / SE Brazil)
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
- `--cmap`: colormap (default `Spectral`)
- `--vmin, --vmax`: color-scale limits
- `--extend`: colorbar extend (`both`/`neither`/`min`/`max`)
- `-c, --clip`: clip extremes at mean ± 4σ (`yes`/`no`)

**Map**
- `-lat_min, -lat_max, -lon_min, -lon_max`: geographic zoom box
- `--no-coastlines`: hide coastlines

**Wind vectors**
- `-u, --u_wind` / `-v_wind, --v_wind`: wind components (optional overlay)
- `--stride`: plot every Nth vector (default 15)

**Animation**
- `--fps`: frames per second (default 5)
- `--dpi`: output resolution (default 150)
- `-j, --jobs`: parallel frame workers (default 1; `-1` = all CPUs)

---

## Legacy commands

The old two-script interface still works through the shims:

| Old | Now equivalent to |
|-----|-------------------|
| `mpas_plot.py -f file.nc -v sst -t 0 -o sst.png` | `mpas_viz.py … -t 0 …` (one step → still) |
| `mpas_animate.py -f "h.*.nc" -v p --tmin 0 --tmax 10 -o a.mp4` | `mpas_viz.py … --tstart 0 --tend 10 …` |

⚠️ **One behavior change:** `--tend` is **inclusive**, whereas the old
`--tmax` was an exclusive slice bound. Using the new `--tend N` therefore
includes one extra step compared to the old `--tmax N`. Out-of-range indices are
clamped, so `--tmax` values equal to the step count still select everything.

## Performance tips

- DPI: 80–100 for fast previews, 150 general use, 300+ for publication.
- `-g no` (no cell edges) is faster on high-resolution meshes.
- Larger `--stride` → fewer wind vectors → faster.
- `-j 4` (or `-j -1` for all CPUs): each worker renders complete frames into
  temporary PNGs that are then combined into the final animation.

## Troubleshooting

- Missing connectivity → supply `-gf` (a `*.static.nc`/`*.init.nc`/`*.grid.nc`).
- `--mask-land` does nothing → the file/grid lacks `landmask`; pass a
  `*.static.nc`/`*.init.nc` via `-gf`.
- FFmpeg missing → `conda install -c conda-forge ffmpeg`, or output `.gif`.
- Too slow → lower DPI, fewer frames, `-g no`, larger `--stride`, or `-j`.
- Variable not found → list with `mpas_viz.py -f file.nc` (no `-v`).

## Typical variables

- Surface: `surface_pressure`, `sst`, `rainnc`, `rainc`
- 3D: `theta`, `pressure`, `qv`, `uReconstructZonal`, `uReconstructMeridional`

## Authors

Originally adapted by Danilo Couto de Souza (2023), with edits by P. Peixoto,
F.A.V.B. Alves and G. Torres Mendonça. Unified `plot`+`animate` framework
(`mpas_viz.py`): Danilo Couto de Souza (2026).
