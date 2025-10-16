## usp-utils
This directory contains several helper scripts and programs to use with MPAS

In order to use the scripts the user should source the setup_environment.sh file:
```sh
. setup_environment.sh # or setup_environment.fish if using fish sell
```
This script will set the necessary environment variables and create the necessary directories, if needed, to use the scripts provided in this directory.

We also provide the `install_conda_environment.sh` script that installs a conda environment with all packages needed to use the scripts provided. This script needs to be run only once, or when the conda environment needs to be updated.

If the user has installed the conda environment provided by `install_conda_environment.sh`, the `setup_environment.sh` will also automatically enable it.

Pre and post processing scripts are placed in `./pre_proc` and `./post_proc` respectively.

Julia scipts (`.jl` files) rely on a shared environment called `cgfd-usp-mpas` which can be installed with the `install_julia_environment.jl` script. The same script can also be used to update the environment.

### Note to developers

New python **modules** (scripts containing definitions that are imported into other scripts) should be placed into `./libs/py`, not in the same folder as the actual scripts importing it.
