# Pre/post-processing environment (Python + Julia)

The scripts in `pre_proc/` and `post_proc/` use a Python environment (the
`cgfd-usp-mpas` conda environment) and a shared Julia environment. Install them
once, then activate them every session.

> Looking to **build the MPAS model** instead? See [`README.md`](README.md).
> This file is only about the pre/post-processing toolbox.

## 1. Install (run once; re-run to update)

```bash
# Python environment 'cgfd-usp-mpas' (built from ../libs/cgfd-usp-mpas.yml):
bash install_conda_environment.sh

# Julia shared environment 'cgfd-usp-mpas'.
# MUST run with `env -u LD_LIBRARY_PATH`, otherwise Julia segfaults against the
# conda/MPAS libraries:
env -u LD_LIBRARY_PATH julia install_julia_environment.jl
```

Both scripts are idempotent — re-running them updates the existing environments.

## 2. Activate (every session)

From the `usp-utils/` directory:

```bash
source setup_environment.sh        # or setup_environment.fish if using the fish shell
```

This is the activation step for the **pre/post-processing tools**: it sets
`MPAS_ROOT` and `PYTHONPATH`, creates `runs/`, `grids/` and `met_data/` if
missing, and activates the `cgfd-usp-mpas` conda environment.

> `runs/`, `grids/` and `met_data/` are the suggested (and **git-ignored**) homes
> for simulations, meshes and input data — keep outputs there so `git add .`
> never stages them. See the [usp-utils README](../README.md#where-to-put-runs-and-data).

It is **not** the model build/run environment. To compile or run the MPAS model
you source a different script — `mpas_build_env.sh` (see [`README.md`](README.md)) —
which sets the PnetCDF/MPI library paths. The two are independent; source both if
you do pre-processing and run the model in the same shell.

## Notes

- Julia always needs `env -u LD_LIBRARY_PATH` (the conda/MPAS libraries make a
  plain `julia` segfault).
- New Python **modules** (files with definitions imported by other scripts) go in
  `../libs/py`, not next to the scripts that import them.
