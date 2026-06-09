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

> **Two caveats when installing the Julia environment:**
> - Run it with `LD_LIBRARY_PATH` cleared, otherwise Julia segfaults in this
>   stack: `env -u LD_LIBRARY_PATH julia install_julia_environment.jl`.
> - `Pkg` may fail to resolve while favba's packages are temporarily out of sync
>   (a `Zeros` compat conflict). If so, a temporary workaround is tracked on the
>   `julia/zeros-compat-workaround` branch until the upstream packages are fixed.

## Installing libraries and building MPAS

Beyond the pre/post-processing tooling above, `usp-utils` also helps you
prepare a full build environment and compile the model, following the NCAR
MPAS-Atmosphere library workflow. The recommended end-to-end flow is documented
in **[`install/INSTALL_GUIDE.md`](install/INSTALL_GUIDE.md)**.

In short, the recommended order is:

1. **Conda environment** (pre/post-processing): `./install_conda_environment.sh`
2. **Julia environment** (mesh tools, optional): see the caveats above
3. **Source the environment**: `. setup_environment.sh`
4. **Download library sources**: `./install/download_mpas_lib_sources.sh <dir>`
5. **Build the I/O libraries**: copy the template to a git-ignored
   `install/mpas_lib_install.local.sh`, set `LIBSRC`/`LIBBASE` in the copy,
   then run it (it also builds its own MPICH — no system MPI required)
6. **Compile MPAS**: export the build environment, then
   `make gfortran CORE=init_atmosphere` and `make gfortran CORE=atmosphere`
   from the repository root
7. **Set up a run directory**:
   `./testing_and_setup/atmosphere/setup_run_dir.py <rundir>`

The `install/` directory contains the helpers for steps 4–5:

- `download_mpas_lib_sources.sh` — downloads and verifies the library source
  tarballs (the exact versions expected by the build script)
- `mpas_lib_install.sh` — **template** that builds MPICH, zlib, HDF5, PnetCDF,
  NetCDF-C, NetCDF-Fortran, and PIO from source. Copy it to
  `mpas_lib_install.local.sh` (git-ignored) and set your `LIBSRC`/`LIBBASE`
  there; the original template stays clean in the repo.

### Note to developers

New python **modules** (scripts containing definitions that are imported into other scripts) should be placed into `./libs/py`, not in the same folder as the actual scripts importing it.
