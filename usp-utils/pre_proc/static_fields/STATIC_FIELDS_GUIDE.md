# Downloading meshes & terrain data for `init_atmosphere` static fields

This guide covers the inputs and steps for the **static-field generation** stage
of MPAS pre-processing — `init_atmosphere` with `config_init_case = 7`. That
stage interpolates geographical/terrain data (topography, land use, soil,
greenness, albedo, ...) onto an MPAS mesh, producing a *static* file that later
real-data initialization and model runs build on.

```
   global mesh  (grid.nc + graph.info)            ┐
                                                   ├─► init_atmosphere (case 7) ─► static file (e.g. x1.40962.init.nc)
   MPAS geog static dataset (config_geog_data_path)┘
```

## Prerequisites

- `init_atmosphere_model` compiled — see
  [`../../install/README.md`](../../install/README.md).
- The build environment sourced (so the MPICH `mpirun` is on `PATH`), e.g.:
  `source ../../install/mpas_build_env.local.sh`. This path is just an
  example — source whatever per-user build-env copy you created from the
  `mpas_build_env.sh` template (you may have renamed or relocated it).

---

## Step 1 — Download the mesh and the MPAS geog data

Use the helper (downloads, integrity-checks, **extracts into `WPS_GEOG/`**, and
records `SHA256SUMS`):

```sh
./download_static_data.sh --mesh x1.40962 --geog mpas
```

- `--mesh NAME` — the global mesh (default `x1.40962`, ≈120 km). Nominal
  resolutions of the quasi-uniform meshes (cell count → spacing):
  `x1.2562`≈480 km, `x1.10242`≈240 km, `x1.40962`≈120 km, `x1.163842`≈60 km,
  `x1.655362`≈30 km, `x1.2621442`≈15 km. The full list (incl.
  variable-resolution meshes) is on the
  [MPAS mesh page](https://mpas-dev.github.io/atmosphere/atmosphere_meshes.html).
  The tarball contains `NAME.grid.nc`, `NAME.graph.info`, and pre-made
  `NAME.graph.info.part.N` partitions (N = 2,4,6,8,...,128).
- `--geog mpas` (default) — the **MPAS-curated** static bundle
  ([`mpas_static.tar.bz2`](https://www2.mmm.ucar.edu/projects/mpas/site/downloads/static.html),
  ~2.2 GB). **This bundle is complete for the standard real-data config**
  (GMTED2010 topo + MODIS 30s land use + STATSGO soil + Noah-MP): it contains
  every subdirectory `mpas_init_atm_static.F` reads for that config, including
  `topo_gmted2010_30s`, `modis_landuse_20class_30s`, `soiltype_top_30s`, and
  `soilgrids/{soilcomp,texture_layer1-4}`. The WRF `geog_high_res_mandatory`
  bundle **lacks** `modis_landuse_20class_30s` and `soilgrids`, which is why
  `mpas` is the default. Alternatives: `--geog high` (~2.6 GB, incomplete for
  MPAS), `--geog low` (~150 MB), `--geog none` (skip).

The mesh lands in `<dest>/grids/`; the geog tarball is cached in
`<dest>/met_data/` and **extracted into `<dest>/met_data/WPS_GEOG/`** (override
the base with `--dest DIR`). Point `config_geog_data_path` at that
`met_data/WPS_GEOG/` directory.

> **Extraction pitfall (the usual cause of failures).** The bundle carries a
> single leading directory (`mpas_static/`). The helper strips it so datasets
> land directly under `WPS_GEOG/<dataset>/`. If you extract the tarball by hand
> *without* stripping it (`tar xjf mpas_static.tar.bz2 -C WPS_GEOG/`), you get
> `WPS_GEOG/mpas_static/<dataset>/` and `init_atmosphere` fails with
> `ERROR: Could not find an 'index' file in geotile directory ...`. Extract with
> `--strip-components=1` (the helper does this for you):
> ```sh
> tar xjf met_data/mpas_static.tar.bz2 --strip-components=1 -C WPS_GEOG/
> ```

### Optional add-ons (only for non-default configs)

The same MPAS downloads page offers add-ons that extract into the *same*
`WPS_GEOG/`. Fetch them with `--optional` (comma list, or `all`):

| `--optional` | File(s) | Needed when |
|---|---|---|
| `ugwp` | `topo_ugwp.tar.gz` + `ugwp_limb_tau.nc` | UGWP/GSL gravity-wave drag (`config_native_gwd_gsl_static = true` / UGWP suite) |
| `15s`  | `modis_landuse_20class_15s.tar.bz2` | 15-arc-second (higher-res) land use |
| `bnu`  | `bnu_soiltype_top.tar.bz2` | BNU soil category (`config_soilcat_data = 'BNU'`) |

```sh
./download_static_data.sh --mesh none --geog none --optional ugwp   # just the UGWP add-on
```

> `ugwp_limb_tau.nc` is **not** a geog dataset — it is a model **run-dir** input
> (the `ugwp_ngw` stream). The helper downloads it into `met_data/`; copy it into
> the `atmosphere_model` run directory if you enable the UGWP suite.

**Download just one component** by setting the other to `none`:

```sh
./download_static_data.sh --mesh x1.10242 --geog none   # only a new mesh
./download_static_data.sh --mesh none --geog mpas        # only the geog data
```

> **Provenance.** The script writes `SHA256SUMS` next to the downloads. The geog
> bundle is large — download it once per machine and share it across projects
> rather than re-downloading.

---

## Step 2 — Mesh partitioning (only if needed)

`init_atmosphere` (and the model) decompose the mesh across MPI tasks using a
`graph.info.part.N` file, where `N` is the number of tasks. The NCAR tarball
already ships the common counts (2–128), selected via the namelist prefix:

```
config_block_decomp_file_prefix = 'x1.40962.graph.info.part.'
```

If you need a task count that is **not** provided, generate it with `gpmetis`
(from METIS) in the `grids/` directory:

```sh
gpmetis x1.40962.graph.info 20      # -> x1.40962.graph.info.part.20
```

Running static generation on a single task needs no partition file at all.

---

## Step 3 — Configure `namelist.init_atmosphere` and streams

Create a run directory (links the executable + copies default namelists/streams):

```sh
"$MPAS_ROOT/testing_and_setup/atmosphere/setup_run_dir.py" "$MPAS_ROOT/runs/static_x1.40962"
cd "$MPAS_ROOT/runs/static_x1.40962"
ln -s "$MPAS_ROOT/grids/x1.40962.grid.nc" .
ln -s "$MPAS_ROOT/grids/x1.40962.graph.info.part."* .
```

Key `namelist.init_atmosphere` options for the static case:

```
&nhyd_model
    config_init_case = 7                 ! static-field generation
/
&data_sources
    config_geog_data_path = '/path/to/WPS_GEOG/'   ! from Step 1, trailing '/'
    config_landuse_data   = 'MODIFIED_IGBP_MODIS_NOAH'
    config_soilcat_data   = 'STATSGO'
    config_topo_data      = 'GMTED2010'
/
&preproc_stages
    config_static_interp         = true
    config_native_gwd_static     = true   ! conventional GWDO (computed from GMTED2010)
    config_native_gwd_gsl_static = false  ! UGWP/GSL drag — needs --optional ugwp; see note
/
&decomposition
    config_block_decomp_file_prefix = 'x1.40962.graph.info.part.'
/
```

> **Noah-MP soil composition is ON by default (hidden option).**
> `config_noahmp_static` has `default_value="true"` but `in_defaults="false"` in
> the Registry, so it is **not written** into the generated namelist yet is
> active. It makes the static stage interpolate `soilgrids/soilcomp` and
> `soilgrids/texture_layer1-4` — hence `soilgrids/` **must** be present under
> `WPS_GEOG/`. The `mpas` bundle provides it; the WRF `high` bundle does not. If
> you deliberately do not want these fields, set `config_noahmp_static = false`
> explicitly.

> **UGWP/GSL gravity-wave-drag static (optional).** Setting
> `config_native_gwd_gsl_static = true` makes init_atmosphere also build the GSL
> orographic-drag fields (`oro_data_ss`/`oro_data_ls`), which need the
> `topo_ugwp_*` raw-topography datasets. Those are **MPAS-specific** and ship as
> the **optional** `topo_ugwp.tar.gz` on the downloads page — fetch them with
> `./download_static_data.sh --optional ugwp` (and copy `ugwp_limb_tau.nc` into
> the model run dir). If a `topo_ugwp_*` tile is missing you get non-fatal
> `ERROR: Error reading topography tile ...` and the run still finishes, but the
> fields are empty. For standard runs keep this **false** (the conventional GWDO
> above is sufficient).

In `streams.init_atmosphere`, the `input` stream reads `x1.40962.grid.nc` and
the `output` stream writes the static file (default `x1.40962.init.nc`; you may
rename the template to `x1.40962.static.nc` to make its role explicit).

---

## Step 4 — Run

```sh
# single task (fine for static generation on moderate meshes):
./init_atmosphere_model

# or multiple tasks (needs a matching graph.info.part.N from Step 2):
mpirun -np 4 ./init_atmosphere_model
```

Check `log.init_atmosphere.0000.out` for `Finished running the init_atmosphere
core`. The output static file appears in the run directory.

---

## Output and next steps

The static file (e.g. `x1.40962.init.nc`) carries the mesh **plus** the
interpolated terrain/land-surface fields. It is the input for the next
pre-processing stage — real-data initialization (a different `config_init_case`
using meteorological data in `met_data/`) — which produces the actual initial
conditions for `atmosphere_model`. Those stages are covered separately.

---

## Troubleshooting

- **`ERROR: Could not find an 'index' file in geotile directory .../<dataset>/`**
  — the dataset directory is missing or nested one level too deep. Almost always
  the bundle was extracted **without** stripping its `mpas_static/` top
  directory (see the extraction pitfall in Step 1), so the data sits in
  `WPS_GEOG/mpas_static/<dataset>/`. Re-extract with `--strip-components=1`
  (or just rerun `download_static_data.sh`). If it specifically names
  `soilgrids/soilcomp/`, your geog set lacks `soilgrids` — use `--geog mpas`,
  not the WRF `high`/`low` bundles.
- **`init_atmosphere` can't find the geog data** — `config_geog_data_path` must
  point to the extracted `WPS_GEOG/` directory and end with a trailing `/`.
- **Decomposition / partition error** — the `graph.info.part.N` file for your
  task count is missing; download a mesh that includes it, run on 1 task, or
  build it with `gpmetis` (Step 2).
- **`config_topo_data`/`config_landuse_data`/`config_soilcat_data` mismatch** —
  those names must match subdirectories present under `WPS_GEOG/`; the `mpas`
  bundle provides GMTED2010 topo, `MODIFIED_IGBP_MODIS_NOAH` land use, and
  `STATSGO` soil.
