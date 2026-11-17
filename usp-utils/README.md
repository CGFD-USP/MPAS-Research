# usp-utils

Scripts to build, run and prepare inputs for MPAS-A on this branch, with the consistent operators of Alves and Peixoto.
**Start with [`doc/README.md`](doc/README.md)**: building, the namelist options, the paper's schemes, the idealized tests, the
meshes and the real cases.

| Path | What it is |
|---|---|
| `doc/` | user guide of this branch |
| `install/` | image definition, model build (`install/container/`), native installers and setup guides |
| `machines/` | machine profiles (data roots, apptainer, cores, scheduler), `submit.sh` and `mpirun.sh`, with nemesis and kami as examples |
| `libs/` | conda environment file and Python modules |
| `pre_proc/` | mesh creation (`grid_creation_scripts/`), real data (`real_data/`) and static fields (`static_fields/`) |
| `proc/` | runs, one folder per benchmark and `real_case/`; `schemes.sh` maps scheme names to namelist options |

Where large data goes: sourcing `setup_environment.sh` creates `runs/`, `grids/` and `met_data/` at the repository root (all
git-ignored). Environment and image: [`install/README.md`](install/README.md), [`install/container/README.md`](install/container/README.md),
[`machines/README.md`](machines/README.md).

New Python modules (files with definitions imported by other scripts) go in `libs/py`, not next to the scripts that import them.
