# Consistent operators for MPAS-A: using this branch

This branch is MPAS-A 8.4.2 with the consistent operators of Alves and Peixoto, implemented in Fortran. The new options need
no operator files. This note builds the model, lists the options and the paper's schemes, and runs the idealized tests, the
meshes and the real cases with the scripts of `usp-utils/`. Every command runs from the root of the repository.

## Build

The model and the tools run in an apptainer image, on any machine with apptainer (nemesis and kami are profiles in
`usp-utils/machines/`, [`machines/README.md`](../machines/README.md) explains how to add another).

```bash
source usp-utils/machines/env.sh                       # machine profile, MPAS_BUILD_ROOT (default ~/mpas-builds)
bash usp-utils/machines/setup.sh                       # once: data root and the image (about 10 min)
bash usp-utils/install/container/build_mpas.sh feature/consistent-operators double   # init_atmosphere and atmosphere
export MPAS_BUILD=$MPAS_BUILD_ROOT/feature-consistent-operators_<commit>_double      # the folder it printed
```

The build is made from a clean copy of the commit and records the commit and checksums in `BUILD_INFO`. Details:
[`install/container/README.md`](../install/container/README.md).

## Namelist options

All options are in `&nhyd_model` of `namelist.atmosphere` (the init option in that of `namelist.init_atmosphere`), and their
defaults keep the operators of MPAS-A 8.4.2. Two corrections of MPAS-A are always on: the `zz` factor of the horizontal
pressure gradient in the acoustic steps, lost in MPAS-A 5.1, and the Smagorinsky deformation coefficients of each edge on
meshes not ordered as NCAR's (bitwise unchanged on NCAR meshes).

| option | default | meaning |
|---|---|---|
| `config_tangential_reconstruction` | `'trsk'` | tangential wind of an edge in the Coriolis term and in the diagnosed `v`: from `weightsOnEdge` (`'trsk'`), or as the mean of the Perot velocities of its two cells along the edge, with the weight of the edge itself (`'perot'`) |
| `config_ke_reconstruction` | `'trsk'` | kinetic energy at cells and vertices from the squares of the edge winds (`'trsk'`), or from the wind vector reconstructed with the Perot weights (`'perot'`) or a second-order least-squares fit (`'lsq2'`). With `'perot'` and `'lsq2'` the same reconstruction gives the cell wind `uReconstruct*` |
| `config_cell_wind_reconstruction` | `'ke'` | cell wind `uReconstruct*` of the physics and the output: from the reconstruction of `config_ke_reconstruction` (`'ke'`, the radial basis functions of MPAS with `'trsk'`), or from the Perot weights (`'perot'`) or the least-squares fit (`'lsq2'`). A value other than `'ke'` needs `config_ke_reconstruction = 'trsk'` or the same value, so with `'trsk'` it changes only the cell wind |
| `config_ke_cell_weight` | `0.625` | weight of the cell estimate in the blend with the vertex estimates, which get one minus this weight |
| `config_edge_midpoint_flux` | `.false.` | fluxes of mass, `theta_m` and `w` in the large-step divergences, and the mass flux of the scalar transport, at the midpoint of the Voronoi edge instead of the edge point |
| `config_point_wind` (init) | `.false.` | normal wind of the idealized init cases 1 to 3, 11 and 17 to 25 as the point value at `xEdge` instead of the dual-edge mean |

The model log lists the reconstructions in use, for example `Tangential velocity from the Perot velocities of the cells`.
The reconstructions need a spherical mesh.

## The schemes of the paper

A scheme is named by its choice for the tangential wind T, the kinetic energy KE and the edge fluxes F (Table 2 of the paper).

| scheme | `tangential` | `ke` | `edge_midpoint_flux` | harness name |
|---|---|---|---|---|
| MPAS | `'trsk'` | `'trsk'` | false | `trsk` |
| T(MPAS)-KE(Cons) | `'trsk'` | `'perot'` | false | `trsk-newke-consistent` |
| T(MPAS)-KE(LSq2) | `'trsk'` | `'lsq2'` | false | `trsk-newke-lsq2` |
| T(Cons)-KE(Cons) | `'perot'` | `'perot'` | false | `consistent-vke` |
| T(Cons)-KE(LSq2) | `'perot'` | `'lsq2'` | false | `lsq2-vke` |
| T(Cons)-KE(Cons)-F(Cons) | `'perot'` | `'perot'` | true | `consistent-vke+em` |
| T(Cons)-KE(LSq2)-F(Cons) | `'perot'` | `'lsq2'` | true | `lsq2-vke+em` |

The paper's idealized tests also set `config_point_wind = .true.`. The
harness maps a name to its options in one place, [`proc/schemes.sh`](../proc/schemes.sh). Names without `-vke` or `-newke`
(`consistent`, `lsq2`) use the cell kinetic energy alone, `config_ke_cell_weight = 1.0`. The control `trsk-cellvel` is MPAS
with the Perot cell wind, `config_cell_wind_reconstruction = 'perot'`, which isolates the effect of the cell wind on the
physics in the real cases.

## Idealized tests

The scripts of [`proc/`](../proc/README.md) set up one run per call in its own folder (namelists, streams, logs and `RUN_INFO`),
make the initial state once per case, and are restartable. The mesh is a regenerated NCAR mesh `x1.<nCells>` (next section).

```bash
bash usp-utils/pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh x1.2562 4    # mesh and a 4-rank partition
export JW_INIT_NHYD_EXTRA="    config_point_wind = true"                      # point-valued initial wind
export JW_NHYD_EXTRA="    config_smdiv = 0.1"                                    # other options of &nhyd_model
J=usp-utils/proc/jw_baroclinic_wave/run_jw.sh
bash $J $MPAS_DATA_ROOT/jw x1.2562 steady-exactavg 30 consistent-vke 4 9_00:00:00   # JW steady state, 30 levels, 4 ranks
bash $J $MPAS_DATA_ROOT/jw x1.2562 wave-exactavg 30 consistent-vke+em 4 9_00:00:00  # JW baroclinic wave with F(Cons)
bash usp-utils/proc/zonal_steady/run_zonal.sh $MPAS_DATA_ROOT/zonal x1.2562 30 trsk 4 10_00:00:00   # solid-body case 11
```

The arguments are the output root, the mesh, the case, the number of levels, the scheme (harness name, optionally with `+em`),
the ranks and the duration. The cases `steady-exactavg` and `wave-exactavg` (init cases 23 and 24) are the ones of the paper.
The time step is proportional to the mesh spacing, 450 s at 120 km. `JW_HISTORY_INTERVAL`, `JW_HISTORY_FIELDS`, `JW_SEGMENT`
and the other variables are in the headers of `run_jw.sh` and `run_zonal.sh`. A cluster job runs the same command through
`bash usp-utils/machines/submit.sh <cores> <log> <command>`. The summary of finished runs:

```bash
bash usp-utils/install/container/run.sh python3 usp-utils/proc/jw_baroclinic_wave/check_runs.py $MPAS_DATA_ROOT/jw
```

`smoke.sh` in each benchmark folder runs a minute-long check of all configurations on x1.2562.

## Meshes

Quasi-uniform meshes. `prepare_ncar_mesh.sh <mesh> [ranks ...]` downloads the NCAR mesh, regenerates it with
`regenerate-mesh.jl` (geometry and TRSK weights recomputed from the generators, with the vertex ordering of the MPAS
specification) and writes the METIS partitions, into `$MPAS_GRIDS/<mesh>` (default `$MPAS_DATA_ROOT/mpas_grids`). Every
scheme, MPAS included, should run on the regenerated mesh. The Julia tools compile on first use, which takes a few minutes.

Any other grid file, for example a refined mesh, goes through `prepare_mesh.sh <name> <grid.nc> [ranks ...]`.

Tropical refinement. The 15 km mesh is the NCAR variable-resolution mesh `x4.1572866` (NCAR's MPAS-Atmosphere meshes page),
run as it is after `prepare_mesh.sh b-60-15 <x4.1572866.grid.nc> <ranks>`. Its three coarsenings (fine spacings 30, 60 and
120 km) keep every other generator of the finer mesh and re-optimize it with JIGSAW:

```bash
G=usp-utils/pre_proc/grid_creation_scripts
bash $G/run_coarsen_meshes.sh <out> <x4.1572866.grid.nc> 15      # <out>/chain-120-30, chain-240-60, chain-480-120 (the other meshes of the same script are direct coarsenings)
bash $G/prepare_mesh.sh b-480-120 <out>/chain-480-120/chain-480-120.nc 16
```

`create_tropical_refined_grid.py` makes a tropically refined mesh of any fine spacing directly (`--help`),
`create_spherical_grid.py` a quasi-uniform or locally refined one, `rotate_mesh.py` moves the refinement centre of a
spherical mesh, and `check_mesh_quality.py` prints the quality metrics. They run in the image through
`bash usp-utils/install/container/run.sh python3 <script>`.

## Real cases

The workflow is one script per step in [`proc/real_case/`](../proc/real_case): static fields of the mesh, the initial
state of a start time, and the forecast. The inputs come from the scripts of [`pre_proc/`](../pre_proc/real_data/README.md).

```bash
U=usp-utils; RUN="bash $U/install/container/run.sh"
bash $U/pre_proc/static_fields/download_static_data.sh --mesh none --geog mpas      # met_data/WPS_GEOG
$RUN python3 $U/pre_proc/real_data/download_gfs.py --date 2023-07-10 --cycle 00     # met_data/gfs/2023071000
$RUN python3 $U/pre_proc/real_data/gfs_to_intermediate.py --grib met_data/gfs/2023071000/gfs.t00z.pgrb2.0p25.f000
# mesh: the regenerated grid and partition of prepare_mesh.sh, here <g>.grid.regen.nc and <g>.grid.regen.graph.info
R=proc/real_case; D=$MPAS_DATA_ROOT/real
bash $U/$R/static.sh $D/static <g>.grid.regen.nc <g>.grid.regen.graph.info 36 met_data/WPS_GEOG
bash $U/$R/init.sh $D/init $D/static/static.nc <g>.grid.regen.graph.info 36 met_data/gfs/2023071000/GFS:2023-07-10_00 34
bash $U/$R/run.sh $D/run/consistent-vke+em $D/init/init.nc <g>.grid.regen.graph.info 36 consistent-vke+em \
  2023-07-10_00:00:00 5_00:00:00 120 25000
```

`gfs_to_intermediate.py` prints the number of first-guess levels (`config_nfglevels`, the last argument of `init.sh`) and
sets the GFS snow depth over water to zero, where the intermediate file would otherwise reach coastal land cells. Partitions
for the rank count come from `prepare_mesh.sh <name> <grid> 36`. `run.sh` takes the physics suite and the output
settings of the build's default namelist, with the changes listed in `RUN_INFO` (variables `RC_*` in its header). The time
step is about five times the finest spacing in kilometres (120 s at 25 km) and `config_len_disp` is that spacing in metres.
The scheme names are those of the table above, so the same name selects the same options in the idealized and the real
runs. The same folder rules apply: a finished run is left alone, a failed one is removed by hand.
