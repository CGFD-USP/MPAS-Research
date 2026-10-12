# Benchmark runs

Scripts that set up and run MPAS benchmarks, one folder per benchmark, between the meshes and
operator files of [`../pre_proc/`](../pre_proc/) and the analysis of
[`../post_proc/`](../post_proc/). Benchmarks always run through these scripts, so every run can
be repeated, and the scripts run unchanged on every machine with a profile in
[`../machines/`](../machines/README.md): they take the storage, the image and the scheduler from
the profile, and run MPAS in the image of [`../install/container/`](../install/container/README.md).

| folder | benchmark |
|---|---|
| [`jw_baroclinic_wave/`](jw_baroclinic_wave/README.md) | Jablonowski and Williamson baroclinic wave and its steady state, with the custom operator configurations |

Rules shared by the benchmarks:

- The model is a build of `install/container/build_mpas.sh`, given by `MPAS_BUILD`, and the
  meshes come from `MPAS_GRIDS` (default `$MPAS_DATA_ROOT/mpas_grids`).
- Every run goes to its own folder under a root given on the command line, which is never
  overwritten. The folder keeps the namelists, the streams, links to its inputs, the MPAS logs and
  `RUN_INFO` (build, binary checksum, host, wall time, status, and a `rerun` line that repeats the
  run by hand).
- Long runs go through `machines/submit.sh`, detached on a workstation or as a job on a cluster.
