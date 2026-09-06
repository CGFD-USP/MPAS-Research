# Grid creation scripts

Scripts to create meshes for MPAS-Atmosphere. They are thin command-line
front-ends; the actual mesh logic lives in the shared modules under
`usp-utils/libs/py/` (`jigsaw_util.py`, `regional_util.py`).

## Setup (read first)

These scripts run in the `cgfd-usp-mpas` conda env, which provides `jigsawpy`,
`mpas_tools` and the `jigsaw` binary. Two extra tools are used but are **not**
part of the base env and must be installed once (per machine): `create_region`
for regional meshes (see section 2) and `gpmetis` for partitioning (see
section 3).
Before running, activate the env and source the usp-utils environment so the
libraries are on `PYTHONPATH` and `MPAS_ROOT` is defined:

```bash
conda activate cgfd-usp-mpas
source usp-utils/setup_environment.sh
```

The `-p/--plot` option additionally uses `matplotlib` and `cartopy` (both in the
env) to draw coastlines and borders; if cartopy or its map data is unavailable
the plot falls back to a plain scatter.

Cell spacing is drawn on a fixed 12-step scale running **purple (finest) →
red → orange → yellow → green (coarsest)**, so the same colour means the same
spacing across every figure and two grids can be compared side by side. Values
coarser than the top of the scale keep the coarsest colour (the arrow on the
colourbar).

In buffer mode `-p` writes **two separate figures** rather than one two-panel
image — `<name>_resolution.png` (the map) and `<name>_resolution_profile.png`
(cell spacing vs signed distance to the region boundary, with the requested
profile overlaid and the relaxation zone highlighted). They answer different
questions and each needs the full width of a page. `--preview` splits the same
way. Without a buffer there is no profile, so only the map is written. If you
point `--plot-out` at a file, the profile lands beside it with `_profile`
appended to the name.

> **Note (changed):** the plots now report cell spacing as `sqrt(2A/√3)`, the
> spacing of a hexagon of area `A`, instead of `2·sqrt(A/π)`, the diameter of an
> equal-area disc. The old formula overstated the spacing by 5.0 %, so a
> nominally 5 km mesh plotted as 5.24 km. Plots made before and after this
> change differ by that 5 %; the new numbers are the correct ones.

## Where meshes are saved

**By default everything is written under `$MPAS_ROOT/grids/<output>/`**, where
`<output>` is the name you pass with `-o`. For example, `-o sudeste_30km`
produces `$MPAS_ROOT/grids/sudeste_30km/`. The directory is created
automatically. `MPAS_ROOT` is set by `setup_environment.sh`; if it is not set,
the scripts stop with a message.

---

## 1. Global meshes — `create_spherical_grid.py`

Creates a mesh that covers the whole planet. The grid type is chosen with `-g`:

| `-g`       | What it does                                              |
|------------|----------------------------------------------------------|
| `unif`     | Uniform-resolution global mesh                           |
| `icos`     | Icosahedral global mesh (`-l` = refinement level)        |
| `localref` | Global mesh **refined over a region** (still global)     |

### Options

| Flag | Default | Used by | Meaning |
|------|---------|---------|---------|
| `-g`, `--grid` | *(required)* | all | `unif`, `icos` or `localref` |
| `-r`, `--high` | `30` | `unif`, `localref` | High-resolution cell spacing, in km |
| `-l`, `--low` | `150` | `icos`, `localref` | `icos`: refinement **level** (1–15). `localref`: global (low-res) spacing in km |
| `-rad`, `--radius` | `50` | `localref` | Radius of the high-resolution area, in km |
| `-tr`, `--transitionradius` | `600` | `localref` | Steepness of the transition between high and low resolution: the slope is `100/tr` km per km, so the belt is `l × tr / 100` km wide, **not `tr`** |
| `-clat`, `--center_latitude` | `0` | `localref` | Latitude (deg) of the centre of refinement |
| `-clon`, `--center_longitude` | `0` | `localref` | Longitude (deg) of the centre of refinement |
| `-o`, `--output` | `grid` | all | Output basename (folder + files under `$MPAS_ROOT/grids/`) |
| `-p`, `--plot` | *(off)* | all | Flag (no value). If given, saves a quick-look PNG of the final mesh resolution to `<output>_resolution.png` (next to the grid). Uses cartopy for coastlines + country borders when available |
| `--plot-out` | *(grid dir)* | all | Custom path for the resolution plot — a file, or a directory in which `<output>_resolution.png` is written. Implies `--plot` |

### Examples (with plots for a quick lookup)

```bash
# Uniform global mesh at 120 km
python create_spherical_grid.py -g unif -r 120 -o global_120km -p

# Icosahedral global mesh, refinement level 7
python create_spherical_grid.py -g icos -l 7 -o icos_l7 -p

# Global mesh refined to 30 km within 500 km of a point, 150 km elsewhere
python create_spherical_grid.py -g localref -r 30 -l 150 \
       -clat -23 -clon -45 -rad 500 -tr 600 -o refined_global -p
```

Run `python create_spherical_grid.py -h` for the built-in help.

---

## 2. Regional (limited-area) meshes — `create_regional_grid.py`

Creates a **true regional mesh**: it builds a global locally-refined mesh and
then **cuts out** only your area of interest, with a boundary (relaxation) zone
for the lateral conditions. This is the standard MPAS-Atmosphere regional
workflow. It runs both steps in **one command**:

1. build a global mesh, fine over your region, coarse elsewhere
   (`jigsaw_util.build_global_mesh`);
2. cut your region out with the NCAR **MPAS-Limited-Area** tool
   (`regional_util.cut_regional_mesh` → `create_region`).

### Smart-transition default

Generating meshes is expensive, so by default the global background is **coarse
(200 km)**. The high-resolution flat zone is sized automatically to cover your
area of interest **plus the 7-cell relaxation belt** (`--buffer`, default
`10 × -r`). As a result:

- **every cell kept in the regional mesh — interior *and* relaxation zone — is
  at the target spacing** (`-r`);
- the coarser transition belt falls **outside** the cut and is **discarded**,
  minimising grid points that get generated but never used.

### Buffer / transition zone (optional)

A uniform regional mesh makes the lateral boundary jump straight from the
driving-data spacing (GFS 0.25° ≈ 25 km, ERA5 ≈ 31 km) to your regional spacing
in a single step. Pass **`--buffer-res`** to instead keep a buffer ring *inside*
the domain, over which the spacing coarsens smoothly from `-r` to the driving
resolution, so the LBC-driven flow can adjust gradually:

```
        area of interest        ramp            flat plateau
   |<--------- R_core --------->|<--- W --->|<------- P ------->|
   |            -r              | -r -> ro  |         ro        |  -> -l
                                            ^          ^mesh edge
                                            LBC zone starts (.pts)
                                            |<- 7 relaxation rings ->|
```

**Everything up to the mesh edge is in the final grid.** The points-file
boundary is the *inner* edge of the lateral-BC zone, not a discard line:
`create_region` grows its 7 relaxation rings **outward** from it, and those
cells are part of `<name>.grid.nc`. The only thing thrown away is what lies
beyond the mesh edge, which never appears in the regional plots at all.

MPAS-Limited-Area grows its **7 relaxation rings outward** from the boundary in
the `.pts` file, so the cut is placed a couple of cells *into* the plateau and
all seven rings land in the flat `ro` band. A locally uniform relaxation zone,
comparable to the driving data, is exactly what limited-area practice asks for.
Everything is sized for you; `--buffer-res` is the only flag you must give.

**Width and abruptness are one knob, seen two ways.** Walking outward one cell
advances the distance by `h` and grows `h` by `(g-1)·h`, so `g = 1 + dh/ds` and

```
W = C · (buffer_res − r) / (decay − 1)
```

where `decay` is the maximum size ratio between adjacent cells and `C` depends
on the ramp shape. Give `--buffer-width` **or** `--buffer-decay`; the other
follows. Mesh-quality guidance is `decay` ≈ 1.05–1.15 — and note that jigsaw is
called with **no gradient limiter**, so a ramp that is too sharp shows up
directly as poor cells with nothing to catch it.

| `--buffer-profile` | `C` | notes |
|---|---|---|
| `linear` | 1.0 | narrowest for a given decay, but the slope kinks at both joins |
| `smoothstep` | 1.5 | cheapest smooth option (C¹) |
| `cosine` | 1.5708 | C¹ |
| `smootherstep` | 1.875 | C² |
| `tanh` *(default)* | 2.3444 | mpas_tools-style; renormalised so it reaches both ends exactly |

Widths for `-r 5 --buffer-res 25` at `--buffer-decay 1.10`: linear 200 km,
smoothstep 300 km, cosine 314 km, smootherstep 375 km, tanh 469 km.

`--buffer-decay` sets the gradient of the **requested** profile. On the mesh
jigsaw actually returns, that gradient is compounded with the generator's own
cell-to-cell scatter, which is present in a uniform mesh too. Measured on the
5 km example:

| neighbour size ratio | max | p99.9 | p99 |
|---|---|---|---|
| uniform 5 km mesh (no buffer, control) | 1.193 | 1.132 | 1.064 |
| buffered mesh — uniform core | 1.163 | 1.145 | 1.079 |
| buffered mesh — ramp (`decay` 1.10) | 1.321 | 1.236 | 1.145 |
| buffered mesh — plateau | 1.167 | 1.151 | 1.109 |

The core and plateau match the control, and the ramp comes out at roughly
`decay × 1.19` — the requested gradient on top of the baseline scatter. So a
realised worst-case ratio below ~1.2 is not achievable at any `decay`; judge a
ramp by how far it sits **above the control**, not against 1.15 in absolute
terms.

**Tune it with `--preview` first.** It resolves the geometry, prints the table
below and saves the *analytic* cell-width map plus its radial profile — in a few
seconds, instead of the minutes a real 5 km mesh costs:

```bash
python create_regional_grid.py -r 5 -l 200 --shape circle \
       -clat -22.33 -clon -49.04 --region-radius 650 \
       --buffer-res 25 --buffer-decay 1.10 -o sp-state_05km_buf --preview
```

```
Buffer / transition zone
------------------------
  area of interest (R_core)             650.0 km
  buffer ramp width                     468.9 km  (5.0 -> 25.0 km, tanh)
  max cell-to-cell growth ratio         1.100    (~44.3 cells across the ramp)
  flat 25.0 km plateau                  300.0 km  (2 pre + 7 relaxation + 3 post cells)
  cut boundary (points file)           1168.9 km
  regional mesh outer edge             1343.9 km
  outer ramp to 200 km starts at       1418.9 km  (discarded by the cut)
```

Drop `--preview` to build it. The same table is written to
`<output>_domain.txt` next to the grid, because with a buffer
**`--region-radius` no longer describes the extent of the mesh** — only the
inner core is at the resolution you asked for.

The buffer follows the **actual region shape** for all four `--shape` values,
not just circles: the profile is a function of the signed distance to the region
boundary, and the cut boundary is a true constant-distance offset of it. A box
therefore gets a buffer of even width all the way round, including at its
corners, and concave polygons offset without self-intersecting. (Circles take an
exact analytic fast path.) One caveat: a region whose centre is more than
~8000 km from its own boundary is rejected, since the local-plane geometry no
longer holds.

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `-r`, `--high` | `30` | Target cell spacing **inside** the region, in km |
| `-l`, `--low` | `200` | Background (global) spacing, in km. Kept coarse on purpose since it is discarded by the cut |
| `--shape` | `circle` | Region shape: `circle`, `ellipse`, `box` or `polygon` (see below) |
| `-clat`, `--center_latitude` | — | Region centre latitude (deg) — **circle/ellipse** (or inside point for **polygon**) |
| `-clon`, `--center_longitude` | — | Region centre longitude (deg) — **circle/ellipse** (or inside point for **polygon**) |
| `--region-radius` | — | Radius of the area of interest, in km — **circle** |
| `--semi-major` | — | Ellipse semi-major axis, in km — **ellipse** |
| `--semi-minor` | — | Ellipse semi-minor axis, in km — **ellipse** |
| `--orientation` | `0` | Ellipse orientation, deg clockwise from north — **ellipse** |
| `--lat-min` / `--lat-max` | — | South / north edges (deg) — **box** |
| `--lon-min` / `--lon-max` | — | West / east edges (deg) — **box** |
| `--polygon-file` | — | Text file with `lat, lon` boundary points (one per line; `#` comments) — **polygon** |
| `--points-file` | — | Rebuild the region from an existing `<name>.pts` (see below). Replaces `--shape` and its coordinates |
| `--buffer` | `10 × -r` | Extra full-resolution margin (km) around the area of interest so the relaxation belt also stays at full resolution. With `--buffer-res` that job is done by the plateau instead, so it just widens the full-resolution core and defaults to `0` |
| `-tr`, `--transitionradius` | `600` | Steepness of the (discarded) outer ramp towards `-l`, as a reference length in km. The slope is `100/tr` km per km, so the belt is actually **`l × tr / 100` km wide, not `tr`** (1200 km at the defaults). Mainly affects generation cost |

#### Buffer / transition zone (see above)

| Flag | Default | Meaning |
|------|---------|---------|
| `--buffer-res` (`--outer-resolution`) | *(off)* | Cell spacing (km) at the **outer edge** of the regional domain — your lateral-BC resolution. **Enables the buffer.** Must be coarser than `-r` and finer than `-l` |
| `--buffer-width` | *derived* | Width (km) of the ramp. Mutually exclusive with `--buffer-decay` |
| `--buffer-decay` (`--buffer-growth`) | `1.10` | Max size ratio between adjacent cells in the ramp. Larger = more abrupt = narrower ring |
| `--buffer-profile` | `tanh` | `tanh`, `smoothstep`, `smootherstep`, `cosine` or `linear` |
| `--relax-pre-cells` | `2` | Plateau cells kept **inside** the cut boundary, absorbing the one-cell jitter of the region-marking walk |
| `--relax-post-cells` | `3` | Plateau cells kept beyond the 7th relaxation ring before the discarded outer ramp starts |
| `--preview` | *(off)* | Resolve the geometry, print the table, plot the **analytic** field, then exit without running jigsaw |
| `--hfun-dlat` | `-r/200` | Working-grid spacing (deg) for the resolution field. It only has to resolve the *transition*, not the cell size, so a coarser grid is usually fine and much cheaper. Advanced |
| `--hfun-float32` | *(off)* | Store the field in single precision: halves memory, smaller intermediate HFUN file. Advanced |
| `-o`, `--output` | `regional_grid` | Output basename (folder + files under `$MPAS_ROOT/grids/`) |
| `-p`, `--plot` | *(off)* | Flag (no value). If given, saves a quick-look PNG of the regional mesh resolution next to the grid, as `$MPAS_ROOT/grids/<output>/<output>_resolution.png`. Uses cartopy for coastlines + country **and state** borders when available |
| `--plot-out` | *(grid dir)* | Custom path for the resolution plot — a file, or a directory in which `<output>_resolution.png` is written. Implies `--plot` |

### Examples

```bash
# Circular region — 30 km over a ~1500 km circle around the SE Brazil coast
python create_regional_grid.py -r 30 -l 200 \
       --shape circle -clat -23 -clon -45 --region-radius 1500 \
       -o sudeste_30km -p

# Lat/lon box region — 25 km over the South Atlantic
python create_regional_grid.py -r 25 -l 200 \
       --shape box --lat-min -35 --lat-max -10 --lon-min -60 --lon-max -30 \
       -o south_atlantic_25km -p

# Ellipse — elongated domain (e.g. along a coast), tilted 30 deg from north
python create_regional_grid.py -r 30 -l 200 \
       --shape ellipse -clat -23 -clon -45 \
       --semi-major 1600 --semi-minor 800 --orientation 30 \
       -o coast_ellipse -p

# Custom polygon from a file (irregular domain)
python create_regional_grid.py -r 30 -l 200 \
       --shape polygon --polygon-file my_region.txt -o my_region -p
```

`my_region.txt` is just one `lat, lon` per line (in counter-clockwise order),
`#` for comments. A point inside is taken as the polygon centroid unless you
pass `-clat -clon`:

```
# my_region.txt
-18, -52
-18, -38
-30, -40
-30, -54
```

#### Reusing an existing region — `--points-file`

A `<name>.pts` already *is* the region geometry, so you can rebuild a domain at
a different resolution without retyping anything:

```bash
# same domain as grids/meqbr_05km, now with a 25 km buffer ring
python create_regional_grid.py --points-file $MPAS_ROOT/grids/meqbr_05km/meqbr_05km.pts \
       -r 5 -l 200 --buffer-res 25 --buffer-decay 1.10 -o meqbr_05km_buf -p
```

It handles all three types a points file can hold (`circle`, `ellipse`,
`custom`) and the geometry round-trips exactly. Two things to know:

- **A `.pts` stores only the geometry**, not the resolution. `-r`, `-l`, `-tr`
  and every `--buffer-*` flag still have to be given on the command line —
  which is the point: it is how you rebuild the *same domain* at a *new*
  resolution. Anything you pass explicitly (`-clat`, `--region-radius`, …)
  overrides the file.
- **Do not feed back a `.pts` that was written with a buffer.** In buffer mode
  the points file holds the *cut* boundary, already pushed outward past the
  ramp, so reusing it would grow the domain by that offset all over again. The
  script warns you when it spots the tell-tale `<name>_domain.txt` beside it;
  reuse the original area of interest instead.

#### Drawing the polygon interactively — `draw_region.py`

Instead of typing coordinates, you can **click them on a map**. `draw_region.py`
opens a cartopy map (coastlines, country and state borders) starting on the
**whole world**; zoom into your region — anywhere on Earth — and click the
vertices. It writes the polygon file for you:

```bash
python draw_region.py -o my_region.txt
# optional starting view: --lat-min --lat-max --lon-min --lon-max
```

Controls: **scroll wheel** zoom in/out · **toolbar** pan / zoom-rectangle ·
**left click** add vertex · **right click** undo · **c** clear · **enter**
save & quit · **esc** quit. Navigating with the wheel or toolbar does not drop
vertices. The saved file is ready for
`--shape polygon --polygon-file my_region.txt`.

> Needs an interactive display (a GUI window). On a headless server run it on
> your local machine or over SSH X forwarding (`ssh -X`).

Run `python create_regional_grid.py -h` for the built-in help.

### Outputs (under `$MPAS_ROOT/grids/<output>/`)

| File                  | What it is                                        |
|-----------------------|---------------------------------------------------|
| `<name>_global.nc`    | global pre-cut mesh (intermediate, can be deleted)|
| `<name>.pts`          | region specification ("points file")              |
| `<name>.grid.nc`      | **the regional mesh**                             |
| `<name>.graph.info`   | partition graph (for `gpmetis`)                   |
| `<name>_domain.txt`   | resolved geometry summary (buffer mode only)      |
| `<name>_resolution.png` | resolution map (`-p`)                           |
| `<name>_resolution_profile.png` | resolution profile (`-p`, buffer mode)  |
| `<name>_preview.png`  | analytic cell-width map (`--preview`)             |
| `<name>_preview_profile.png` | analytic profile (`--preview`)             |

### Dependency: MPAS-Limited-Area (one-time install)

The cut step needs the external `create_region` tool from NCAR. The upstream
repository (`MPAS-Dev/MPAS-Limited-Area`) ships **no `setup.py`/`pyproject.toml`**,
so a plain `pip install git+https://...` does **not** work.

**Recommended — run the bundled installer once** (it clones the tool, adds a
minimal local `setup.py` and installs it editable into the active env):

```bash
conda activate cgfd-usp-mpas
bash install_limited_area.sh            # optional: pass a custom install dir
```

This is a **one-time, per-machine** setup (not per run). Re-running it is safe
(it just updates and reinstalls). To remove the tool later:
`pip uninstall mpas-limited-area`.

<details>
<summary>Manual steps (what the installer does)</summary>

```bash
git clone https://github.com/MPAS-Dev/MPAS-Limited-Area.git
cd MPAS-Limited-Area
cat > setup.py <<'PY'
from setuptools import setup
setup(name="mpas-limited-area", version="0.0.0",
      packages=["limited_area"], scripts=["create_region"],
      install_requires=["numpy", "netCDF4"])
PY
pip install -e .
```
</details>

If `create_region` is missing, `create_regional_grid.py` stops with a message
pointing here.

---

## 3. Partitioning for parallel runs (`gpmetis`)

To run MPAS in parallel you must split the mesh into one block per MPI task.
That is done with **`gpmetis`** (from METIS), which reads the mesh's
`graph.info` and writes a `graph.info.part.<N>` file (`N` = number of MPI
tasks). Both grid scripts already produce the graph file:

- global meshes  → `$MPAS_ROOT/grids/<output>/<output>_graph.info`
- regional meshes → `$MPAS_ROOT/grids/<output>/<output>.graph.info`

Partition it, e.g. for 96 tasks (`<output>_graph.info` for global meshes,
`<output>.graph.info` for regional ones):

```bash
gpmetis $MPAS_ROOT/grids/<output>/<output>.graph.info 96
# -> creates <...>.graph.info.part.96
```

**Recommended (MPAS docs).** For production runs use the higher-quality
options recommended by MPAS:

```bash
gpmetis -minconn -contig -niter=200 \
        $MPAS_ROOT/grids/<output>/<output>.graph.info 96
```

- `-contig` — each partition is a single connected block (better halo
  exchange);
- `-minconn` — minimise how many neighbour partitions each block talks to
  (less MPI communication);
- `-niter=200` — more refinement iterations for a better-quality partition.

They are not required for MPAS to run (plain `gpmetis` works), but they
improve parallel performance and are worth it at scale.

### Install (one-time, per machine)

`gpmetis` ships with the conda-forge `metis` package:

```bash
conda install -n cgfd-usp-mpas -c conda-forge metis
```

(Removes with `conda remove -n cgfd-usp-mpas metis`.)

---

## Other files

- `create-voronoi-operator.jl`, `regenerate-mesh.jl` — Julia mesh helpers.
