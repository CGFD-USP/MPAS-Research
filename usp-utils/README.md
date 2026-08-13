# usp-utils

Helper scripts and tools for working with MPAS: environment/build setup, plus
pre- and post-processing.

## Where to start

Set up what you need **before** running any pre/post-processing:

1. **Installation & environment** — see [`install/`](install/). Two independent
   tracks, install only what you need:
   - Python/Julia pre/post-processing tools →
     [`install/environment_setup.md`](install/environment_setup.md)
   - MPAS model build (compile/run the model) →
     [`install/README.md`](install/README.md)
2. **Activate the toolbox** (each session) to use the Python/Julia scripts:
   ```bash
   source usp-utils/setup_environment.sh        # or setup_environment.fish if using the fish shell
   ```
   This activates the **pre/post-processing** tools (Python/Julia). The model
   build/run environment is a separate script (`install/mpas_build_env.sh`).
3. **Run pre/post-processing** — the scripts in `pre_proc/` and `post_proc/`.

## Where to put runs and data

Sourcing `setup_environment.sh` creates three standard directories at the repo
root (if they don't already exist). These are the **suggested locations** for the
heavy, non-versioned files of the workflow:

| Directory   | Put here                                                        |
|-------------|-----------------------------------------------------------------|
| `runs/`     | Model run directories — one per simulation (the suggested place to run the model) |
| `grids/`    | MPAS meshes                                                      |
| `met_data/` | Meteorological input (GFS/ERA5 downloads, WPS intermediate files) |

All three are **git-ignored**, so it is safe to keep large outputs here — a
`git add .` will never stage them. Keeping your simulations under `runs/` is the
recommended way to avoid accidentally committing model output.

## Folder map

| Path                   | What it is                                              |
|------------------------|---------------------------------------------------------|
| `setup_environment.sh` | **Source each session** for the pre/post-proc tools — `.fish` variant for the fish shell |
| `install/`             | Installers + setup guides (environment + model build)   |
| `libs/`                | Conda env file (`cgfd-usp-mpas.yml`) and Python modules |
| `pre_proc/`            | Pre-processing scripts (static fields, real data, …)    |
| `post_proc/`           | Post-processing / plotting scripts                      |

## Pre- and post-processing

The `pre_proc/` and `post_proc/` directories hold the data-preparation and
plotting scripts, each documented in its own subdirectory. They are covered
separately from this installation guide.

## Note to developers

New Python **modules** (files with definitions imported by other scripts) go in
`libs/py`, not next to the scripts that import them.
