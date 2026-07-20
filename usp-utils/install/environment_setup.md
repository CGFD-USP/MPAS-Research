# Pre/post-processing environment (Python + Julia)

The scripts in `pre_proc/` and `post_proc/` use a Python environment (the
`cgfd-usp-mpas` conda environment) and a shared Julia environment. Install them
once, then activate them every session.

> Looking to **build the MPAS model** instead? See [`README.md`](README.md).
> This file is only about the pre/post-processing toolbox.

## 1. Install (run once; re-run to update)

~~~bash
cd usp-utils/install

# Python environment 'cgfd-usp-mpas' (built from ../libs/cgfd-usp-mpas.yml):
bash install_conda_environment.sh

# Julia shared environment 'cgfd-usp-mpas'.
# `env -u LD_LIBRARY_PATH` is a safety net, not always required -- see the note
# on LD_LIBRARY_PATH below. It is harmless when unnecessary:
env -u LD_LIBRARY_PATH julia install_julia_environment.jl
~~~

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

### `LD_LIBRARY_PATH` and Julia (when `env -u` is actually needed)

Julia ships **its own copies** of several common libraries (`libcurl.so.4`,
`libcrypto.so.3`, `libgcc_s.so.1`, `libgfortran.so.5`, `libgomp.so.1`,
`libgmp.so.10`, …) under `<julia>/lib/julia`. If `LD_LIBRARY_PATH` points at a
directory that carries *different builds of those same SONAMEs*, the dynamic
loader picks those instead of Julia's own, and Julia crashes with a segfault as
soon as it loads `Pkg` (which uses libcurl/TLS).

**This is not always a problem.** On a machine where `LD_LIBRARY_PATH` is empty —
the common case — plain `julia` works fine. Check yours:

```bash
echo $LD_LIBRARY_PATH        # empty -> you don't need `env -u` at all
```

Measured on this stack (Julia 1.12, `import Pkg`):

| `LD_LIBRARY_PATH` contains          | Result       |
|-------------------------------------|--------------|
| *(empty)*                           | works        |
| the MPAS build libs (MPICH/PnetCDF) | works — no SONAME overlap with Julia |
| an active conda env's `lib/`        | **segfault** |
| `/usr/lib/x86_64-linux-gnu`         | **segfault** |

So the MPAS build environment is **not** the culprit; a populated system or conda
library path is. Where `LD_LIBRARY_PATH` is set (some systems export it globally
from the shell profile), run Julia with it cleared — it is harmless when it was
not needed anyway:

```bash
env -u LD_LIBRARY_PATH julia <script>.jl
```

### Python modules

New Python **modules** (files with definitions imported by other scripts) go in
`../libs/py`, not next to the scripts that import them.
