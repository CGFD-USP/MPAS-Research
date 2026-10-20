# Baroclinic wave benchmark

Jablonowski and Williamson (2006) baroclinic wave of MPAS-Atmosphere (`config_init_case = 2`, a
zonal wind perturbation in the Northern Hemisphere) and its steady state without perturbation
(`config_init_case = 1`), on the NCAR quasi-uniform meshes, for the configurations of the custom
horizontal operators. The model is dry and has no physics, and the namelist follows the NCAR test
case (`jw_baroclinic_wave` of the MPAS test cases, v7.0), with the time step and the Smagorinsky
length proportional to the cell spacing.

| file | does |
|---|---|
| `common.sh` | settings: build, meshes, spacing and time step of a mesh, configurations with their operator file and options |
| `run_jw.sh <root> <mesh>[-ncar] <wave\|steady\|wave-flat\|steady-flat\|wave-rebal\|steady-rebal\|wave-exactavg\|steady-exactavg> <levels> <config> <ranks> <duration>` | makes the initial state once per mesh, case and level count (`init/`), then sets up and runs one configuration (`<config>_np<ranks>/`) |
| `check_runs.py <root>` | status, cost, whether the operator file was read, final ranges, and differences of cell fields between runs (each configuration against `trsk`, 1 rank against more ranks, the NCAR grid against the regenerated one, the steady state against its initial state) |
| `smoke.sh [root]` | smoke test on the 480 km mesh, 1 day per run, about 1 min on 4 cores |

The meshes and operator files come from
[`../../pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh`](../../pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh).

## Use

```bash
source usp-utils/machines/env.sh
export MPAS_BUILD=~/mpas-builds/master_61c72867_double   # a build of build_mpas.sh
bash usp-utils/proc/jw_baroclinic_wave/smoke.sh          # $MPAS_DATA_ROOT/mpas_benchmarks/jw_smoke_<time>
bash usp-utils/pre_proc/grid_creation_scripts/prepare_ncar_mesh.sh x1.40962 48
bash usp-utils/proc/jw_baroclinic_wave/run_jw.sh $MPAS_DATA_ROOT/jw x1.40962 wave 60 consistent 48 15_00:00:00
bash usp-utils/install/container/run.sh python3 usp-utils/proc/jw_baroclinic_wave/check_runs.py $MPAS_DATA_ROOT/jw
```

On a cluster, the same commands go through `usp-utils/machines/submit.sh <cores> <log> ...`.
Runs of one case may start together (in separate jobs): the first makes the initial state, and the
others wait for it (at most `JW_INIT_WAIT` seconds, 3 h by default).

Long runs go in segments: with `JW_SEGMENT=<D_hh:mm:ss>` (a divisor of the duration) a run writes a
restart file at the end of each segment and starts the next segment from it, keeping only the
latest restart file (about 84 GB at 15 km with 60 levels); the last segment writes none
(`streams.atmosphere.segments` and `streams.atmosphere.last`), unless `JW_KEEP_RESTART` is set. A call of `run_jw.sh` runs the remaining
segments, at most `JW_SEGMENTS_PER_CALL`, so a chain of identical jobs, each shorter than a day,
makes one long run. The progress is the time of the latest restart file (`restart_timestamp`, which
MPAS writes once the file is complete), so a call after an interrupted segment, such as a job
requeued after a node failure, repeats that segment. A call on a complete run does nothing, and a
call on a failed run stops. Segmented and interrupted runs give the same bits as one continuous run.

Other test cases run through `run_jw.sh` with environment variables for the init case, the time
step, the horizontal mixing, the divergence damping and the output fields (its header), as
[`../zonal_steady`](../zonal_steady) does. Unset, they keep the settings above.

Flat surface (opt-in): the cases `steady-flat` and `wave-flat` (`config_init_case = 17` and `18`, and 19 for the
normal-mode perturbation) use the JW fields over a flat surface at z = 0, with the surface pressure
p0 eta_s(lat) at which the JW geopotential vanishes, instead of the JW terrain. The existing cases
`steady` and `wave` are unchanged. The flat-surface results are not directly comparable with published JW
and HIWPP numbers, since the base state, the surface pressure and the reference solution differ.

Rebalanced wind (opt-in): the cases `steady-rebal` and `wave-rebal` (`config_init_case = 20` and `21`, and 22 for the
normal-mode perturbation) keep the JW terrain and surface pressure, and balance the initial wind against the
pressure gradient that the model evaluates (along-level gradient over `zz` plus the `zxu` term with the hydrostatic
`dp'/dz`), instead of the conservative form of the earlier releases. The existing cases `steady` and `wave` are unchanged.
The cases `steady-exactavg` and `wave-exactavg` (`config_init_case = 23` and `24`, and 25 for the normal-mode perturbation)
are the rebalanced ones with the exact mean of the piecewise-linear 2D wind over the latitudes of the dual edge (the
rebalanced cases weight the first partial interval wrongly, an error of the edge wind that grows as 1/dx down to the
spacing of the 2D grid) and with the 2D latitude grid refined to the mesh (at most 1/8 of the shortest cell distance).

The MPI launch is `usp-utils/machines/mpirun.sh`: on one node, or across the nodes of a PBS job when
the ranks need more than one node.

Layout:

```
$MPAS_GRIDS/<mesh>/              NCAR grid and partitions, <mesh>.grid.regen.nc (+ graph.info, partitions),
                                 operators-consistent.nc, operators-lsq2.nc, PROVENANCE
<root>/<mesh>[-ncar]/<case>_L<levels>/
    init/                        init.nc of init_atmosphere (1 rank), RUN_INFO
    <config>_np<ranks>/          namelists (.start, .restart), streams, history.*.nc, diag.*.nc, logs
                                 (one per segment), the latest restart file, RUN_INFO
```

## Configurations

| configuration | operator file | `.true.` among weightsOnEdge, coeffs_reconstruct, ke_use_reconstructed_vel, ke_use_vertex_reconstructed_vel |
|---|---|---|
| `trsk` | none | none (MPAS standard) |
| `consistent` | `operators-consistent.nc` | first three |
| `consistent-vke` | `operators-consistent.nc` | all four |
| `lsq2` | `operators-lsq2.nc` | first three |
| `lsq2-vke` | `operators-lsq2.nc` | all four |
| `trsk-newke-consistent` | `operators-consistent.nc` | last three |
| `trsk-newke-lsq2` | `operators-lsq2.nc` | last three |

## Choices

- Meshes: any NCAR quasi-uniform mesh `x1.<nCells>`, with the nominal spacing of NCAR's names,
  480 km times the square root of 2560 / (nCells - 2). `init_atmosphere` takes the regenerated
  mesh, on which the operator files are computed, so every configuration, `trsk` included, runs on
  it. `<mesh>-ncar` runs `trsk` on NCAR's own grid, which differs from the regenerated one in its
  areas (mimetic) and edges.
- Vertical grid: the MPAS JW initialization places the model top at 45 km with uniform layers
  (`config_ztop` is not used), so only the number of levels is chosen.
- Time step: 450 s at 120 km, proportional to the spacing (1800 s at 480 km, 28.125 s at 7.5 km).
- Off-centering of the acoustic steps: the v8 defaults of `&damping`, since `config_epssm` of the
  v7 namelist is no longer read. No Rayleigh damping (`config_xnutr = 0`), as in the test case.
- Output: 2D diagnostics once a day (`mslp`, 850 hPa vorticity, winds and temperature, 500 hPa
  height, lowest-level winds, which equal the reconstructed winds of the lowest level), and 3D
  history (`w`, `theta`, `rho`, `pressure`, reconstructed cell winds) at the start and the end
  only. Both intervals can be changed (`JW_DIAG_INTERVAL`, `JW_HISTORY_INTERVAL`). At 15 km and
  60 levels one 3D output takes about 9 GB and one 2D output 0.2 GB.
- Surface pressure: `surface_pressure` is computed by the physics only, so `check_runs.py`
  derives it from the two lowest levels with the formula of the physics interface (a few hPa
  above the exact value with 26 levels, so only differences between runs are meaningful).
- MPI: `usp-utils/machines/mpirun.sh`, ranks bound to cores inside PBS jobs, TCP on high ports.
  `MPAS_MPIRUN_OPTS` adds options.
- Output streams count their times from the start of the run (`reference_time`), so a restarted
  segment keeps the daily diagnostics and the final 3D output, and they replace a file left by an
  interrupted segment (`clobber_mode="replace_files"`).
