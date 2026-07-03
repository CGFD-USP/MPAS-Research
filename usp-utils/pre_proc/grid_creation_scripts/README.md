# Grid creation scripts

Scripts to create meshes for MPAS-Atmosphere. They are thin command-line
front-ends; the actual mesh logic lives in the shared modules under
`usp-utils/libs/py/` (`jigsaw_util.py`, `regional_util.py`).

## Setup (read first)

These scripts run in the `cgfd-usp-mpas` conda env (it provides `jigsawpy`,
`mpas_tools`, the `jigsaw` binary, `create_region` for regional meshes, and
`gpmetis` for partitioning — see section 3).
Before running, activate it and source the usp-utils environment so the
libraries are on `PYTHONPATH` and `MPAS_ROOT` is defined:

```bash
conda activate cgfd-usp-mpas
source usp-utils/setup_environment.sh
```

The `-p/--plot` option additionally uses `matplotlib` and `cartopy` (both in the
env) to draw coastlines and borders; if cartopy or its map data is unavailable
the plot falls back to a plain scatter.

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
| `-tr`, `--transitionradius` | `600` | `localref` | Width of the transition zone between high and low resolution, in km |
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
| `--buffer` | `10 × -r` | Extra high-res margin (km) around the area of interest so the relaxation belt also stays at full resolution |
| `-tr`, `--transitionradius` | `600` | Transition-zone width (km). Lies outside the region and is discarded, so it mainly affects generation cost |
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

#### Drawing the polygon interactively — `draw_region.py`

Instead of typing coordinates, you can **click them on a map**. `draw_region.py`
opens a cartopy map (coastlines, country and state borders); left-click to add
vertices, and it writes the polygon file for you:

```bash
python draw_region.py -o my_region.txt
# optional starting view: --lat-min --lat-max --lon-min --lon-max
```

Controls: **left click** add vertex · **right click** undo · **c** clear ·
**enter** save & quit · **esc** quit. The saved file is ready for
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
