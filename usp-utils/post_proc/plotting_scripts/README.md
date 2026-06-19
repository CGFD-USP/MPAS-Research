# MPAS plotting scripts

Lightweight scripts for quick, generic visual inspection of MPAS NetCDF
outputs **on the native (Voronoi) grid** — no regridding required. They are
meant for fast diagnostics; for publication-quality figures, adapt them as
needed.

| Script | Purpose |
|--------|---------|
| `mpas_plot.py` | Plot a single scalar field (one time step / vertical level) on the native mesh. |
| `mpas_animate.py` | Animate a scalar field (and optionally wind vectors) over time, with parallel rendering. |

## Environment

Use the project conda environment (`usp-utils/setup_environment.sh`):

```bash
conda activate cgfd-usp-mpas
```

The scripts rely on `xarray`, `numpy`, `matplotlib`, `cartopy` and `tqdm`.
`mpas_animate.py` additionally needs FFmpeg for `.mp4` output (`conda install
-c conda-forge ffmpeg`); `.gif` output uses Pillow.

---

## `mpas_plot.py` — single-field maps

### Discover variables

If you do **not** pass `-v/--var`, the script prints a formatted table of the
plottable variables (name, long name, units, grid location, extra dims) and
exits, so you can pick one:

```bash
python mpas_plot.py -f x1.10242.sfc_update.nc
```

### Plot a variable

```bash
# Surface field, time step 0
python mpas_plot.py -f x1.10242.sfc_update.nc -v sst -t 0 -o sst.png \
    -gf x1.10242.grid.nc

# 3D field at vertical level 10
python mpas_plot.py -f history.2026-06-16_00.00.00.nc -v theta -l 10 -o theta.png

# Zoom to a region (South Atlantic / SE Brazil)
python mpas_plot.py -f x1.10242.sfc_update.nc -v sst -t 0 \
    -lat_min -40 -lat_max 0 -lon_min -70 -lon_max -20 -o sst_zoom.png \
    -gf x1.10242.grid.nc
```

### The grid file (`-gf`) vs the edge switch (`-g`)

Many MPAS files (e.g. `sfc_update`, `diag`, some `history` files) **do not
carry the mesh connectivity** (`verticesOnCell`, `nEdgesOnCell`,
`latitudeVertex`, ...). To plot them you must supply a file that does — a
`*.grid.nc`, `*.static.nc` or `*.init.nc` — through **`-gf/--gridfile`**:

```bash
-gf x1.10242.grid.nc
```

⚠️ **`-g/--grid` is NOT the grid file** — it is only the yes/no switch for
drawing cell edges. Passing a file path to `-g` is a common mistake; the
script now detects it and tells you to use `-gf` instead.

### Main options (`mpas_plot.py`)

- `-f, --infile`: Input MPAS file (`.nc`) — **required**
- `-v, --var`: Variable to plot (omit to list available variables)
- `-o, --outfile`: Output image file (omit to show interactively)
- `-l, --level`: Vertical level (for 3D fields)
- `-t, --time`: Time step index
- `-gf, --gridfile`: File providing mesh connectivity, if `infile` lacks it
- `-g, --grid`: Draw cell edges (`yes`/`no`)
- `-c, --clip`: Clip extremes at mean ± 4σ (`yes`/`no`)
- `-lat_min, -lat_max, -lon_min, -lon_max`: Geographic zoom box

---

## `mpas_animate.py` — time animations

### Usage examples

- Animate a surface field:
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure -o animation.mp4
  ```
- Animate a 3D field at a vertical level:
  ```bash
  python mpas_animate.py -f "history.*.nc" -v theta -l 10 -o temp_animation.mp4
  ```
- Animate with wind vectors:
  ```bash
  python mpas_animate.py -f "history.*.nc" -v theta -l 10 \
      -u uReconstructZonal -v_wind uReconstructMeridional -o wind_animation.mp4
  ```
- Limit time range:
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure --tmin 0 --tmax 10 -o animation.gif
  ```
- Zoom to a region:
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure \
      -lat_min -35 -lat_max 5 -lon_min -75 -lon_max -35 -o region_animation.mp4
  ```
- Parallel rendering (4 workers / all CPUs):
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure -j 4 -o animation.mp4
  python mpas_animate.py -f "history.*.nc" -v surface_pressure -j -1 -o animation.mp4
  ```
- Custom color scale (surface pressure in Pa):
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure \
      --vmin 90000 --vmax 103500 --cmap viridis -o animation.mp4
  ```
- **Sum variables** (total precipitation = convective + non-convective):
  ```bash
  python mpas_animate.py -f "history.*.nc" --sum-vars "rainc+rainnc" -o total_precip.mp4
  ```
- **Deaccumulate** (accumulated field → rate):
  ```bash
  python mpas_animate.py -f "history.*.nc" --sum-vars "rainc+rainnc" --deaccumulate -o precip_rate.mp4
  ```
- **Hide coastlines** (cleaner plots):
  ```bash
  python mpas_animate.py -f "history.*.nc" -v surface_pressure --no-coastlines -o clean_animation.mp4
  ```

### Main options (`mpas_animate.py`)

- `-f, --files`: Input file glob pattern
- `-v, --var`: Variable to animate
- `-l, --level`: Vertical level (for 3D fields)
- `-u, --u_wind` / `-v_wind, --v_wind`: Wind components (optional vectors)
- `-gf, --gridfile`: Additional grid file (mesh connectivity)
- `-o, --outfile`: Output filename (default: `mpas_animation.mp4`)
- `--cmap`: Colormap (default: `Spectral`)
- `--vmin, --vmax`: Colorbar limits
- `-c, --clip`: Clip extremes (`yes`/`no`)
- `-g, --grid`: Draw cell edges (`yes`/`no`)
- `-lat_min, -lat_max, -lon_min, -lon_max`: Geographic box
- `--tmin, --tmax`: Start/end frame indices
- `--fps`: Frames per second (default: 5)
- `--dpi`: Output resolution (default: 150)
- `--stride`: Vector stride (default: 15)
- `-j, --jobs`: Parallel workers (default: 1; `-1` for all CPUs)
- `--extend`: Colorbar extend: `both`/`neither`/`min`/`max` (default: both)
- `--sum-vars`: Sum two variables (e.g. `rainc+rainnc`)
- `--deaccumulate`: Compute temporal differences (first frame skipped)
- `--no-coastlines`: Hide coastlines

### Output formats

- `.mp4`: MP4 video (requires FFmpeg)
- `.gif`: Animated GIF (uses Pillow)
- Other Matplotlib-supported formats may work

### Advanced variable operations

**Variable summing** (`--sum-vars`) adds two fields before plotting — e.g.
total precipitation from convective + non-convective components, or any other
additive fields (fluxes, energy components).

**Deaccumulation** (`--deaccumulate`) computes differences between consecutive
time steps, turning accumulated fields into rates (precipitation rate,
instantaneous fluxes). The first frame is skipped (no previous step).

### Performance tips

- DPI: 80–100 for fast previews, 150 for general use, 300+ for publication.
- `-g no` (no cell edges) is faster on high-resolution meshes.
- Larger `--stride` → fewer vectors → faster.
- Parallel rendering: `-j 4` (~4× faster) or `-j -1` (all CPUs). Each worker
  renders complete frames independently into temporary PNGs that are then
  combined into the final animation.

### Troubleshooting

- FFmpeg missing → `conda install -c conda-forge ffmpeg`, or output `.gif`.
- Too slow → lower DPI, fewer frames, `-g no`, larger `--stride`, or `-j`.
- Variable not found → list variables with `mpas_plot.py -f file.nc` (no `-v`),
  or `ncdump -h file.nc | grep -A2 "variables:"`.

---

## Typical variables

- Surface: `surface_pressure`, `sst`, `rainnc`, `rainc`
- 3D: `theta`, `pressure`, `qv`, `uReconstructZonal`, `uReconstructMeridional`

## Customization

These scripts target quick, generic visualization. For advanced mapping,
projections, overlays or custom features, adapt the code as needed.

## Authors

`mpas_plot.py` — originally adapted by Danilo Couto de Souza (2023), with
later edits by P. Peixoto, F.A.V.B. Alves and G. Torres Mendonça.
`mpas_animate.py` — based on `mpas_plot.py`, by Danilo Couto de Souza (2025).
