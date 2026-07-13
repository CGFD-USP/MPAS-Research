# MPAS model build — dependencies (lean PnetCDF-only setup)

A minimal toolchain for compiling and running MPAS-Atmosphere v8.

> Setting up the **Python/Julia pre/post-processing tools** instead? See
> [`environment_setup.md`](environment_setup.md). This file is only about
> building and running the model.

## Quick start

You need three things: a Fortran/C **compiler**, an **MPI** library, and
**PnetCDF**. The compiler is almost always already on the machine; this guide
helps you find out whether MPI is there too, and builds PnetCDF for you.

> **Where do I run these?** Run everything below from the **MPAS repository
> root**, e.g. `cd /home/your-user/Downloads/MPAS-Research`. (Only the final
> `make` strictly requires it — the install script and the `source` use absolute
> paths and would work from anywhere — but staying at the root keeps every
> command below copy-pastable.)

MPAS v8 bundles its own I/O layer, **SMIOL** (`src/external/SMIOL`), and uses it
automatically whenever the `PIO` environment variable is **unset**. The full dependency set is:

| Component  | Source                                   | Notes                                     |
|------------|------------------------------------------|-------------------------------------------|
| Compilers  | system / HPC module stack                | GCC works from v10 to v16                 |
| MPI        | system / HPC module stack (**preferred**) | or build MPICH here (optional)            |
| PnetCDF    | built by `mpas_lib_install.sh`           | the only required external library        |

> Prefer the MPI provided by your system or HPC site — it is usually tuned for
> the local interconnect (e.g. InfiniBand). Only build MPICH yourself when no
> system MPI is available.

### Step 1 — check what you already have

```bash
gfortran --version     # should print a version (GCC 10–16 all work). If "not
                       # found", you have no compiler — ask your sysadmin.

which mpif90           # prints a PATH  -> you HAVE MPI, go to Step 2A
                       # "not found"    -> you have NO MPI, go to Step 2B
```

On a shared HPC cluster, MPI is often hidden behind *modules*. Test with:

```bash
module avail           # lists software you can load -> you are on an HPC, use 2A
                       # "command not found" -> plain workstation, use 2B
```

### Step 2A — you already have MPI (or an HPC module)

```bash
module load openmpi                       # only on HPC; skip on a workstation
bash usp-utils/install/mpas_lib_install.sh
```

### Step 2B — you have no MPI (build it automatically)

`BUILD_MPICH=1` downloads and compiles MPICH for you, then PnetCDF:

```bash
BUILD_MPICH=1 bash usp-utils/install/mpas_lib_install.sh
```

### Step 3 — set the environment and compile MPAS

```bash
# source the env from wherever the script lives (absolute path works anywhere):
source /path/to/MPAS-Research/usp-utils/install/mpas_build_env.sh

# then cd into the MPAS source you want to build -- the folder that contains the
# top-level `Makefile` -- and run make THERE (this is the only step that cares
# about the current directory):
cd /path/to/MPAS-Research        # <- replace with your actual repo path
make gnu CORE=init_atmosphere AUTOCLEAN=true
make gnu CORE=atmosphere      AUTOCLEAN=true
```

`AUTOCLEAN=true` re-cleans the tree automatically when it still holds objects
from an earlier build with different options; without it the build aborts with
*"previously compiled with incompatible options"*.

> **Precision — single is the default (and usually what you want).** Since MPAS
> v8.1/8.2 the default real kind is **single** precision (the `Makefile` help
> says: *"Default is to use single-precision"*). It runs faster, uses less RAM
> and writes smaller output, and NCAR reports no accuracy or stability
> degradation for typical forecasts — so it is the right choice for most runs,
> and it is what the commands above build.
>
> The trade-off is resolution: the smallest representable relative error is
> ~2e-7 in single, against ~2e-16 in double. If your analysis depends on small
> residuals of large terms (energy budgets, conversion / energetics diagnostics),
> build in double instead. The flag must be passed to **both** cores:
>
> ```bash
> make gnu CORE=init_atmosphere PRECISION=double AUTOCLEAN=true
> make gnu CORE=atmosphere      PRECISION=double AUTOCLEAN=true
> ```

Common errors:
- `The PNETCDF environment variable isn't set` — you skipped the `source` line
  (or opened a new terminal; re-run it).
- `... previously compiled with incompatible options` — the source tree holds
  leftover objects from an earlier build. `AUTOCLEAN=true` (above) handles this;
  otherwise run `make clean CORE=<core>` first.

### Step 4 — run the model (same env, in EVERY new shell)

The same `source` is required not only to **compile** but to **run**
`init_atmosphere_model` / `atmosphere_model`: it puts the MPICH `mpiexec`/`mpirun`
on `PATH` and the runtime libraries on `LD_LIBRARY_PATH`. Source it once per shell
(a new terminal needs it again):

```bash
source /path/to/MPAS-Research/usp-utils/install/mpas_build_env.sh
cd /path/to/MPAS-Research/runs/<your_run_dir>
mpiexec -n 64 ./atmosphere_model            # or: nohup mpiexec -n 64 ./atmosphere_model &
```

Run errors:
- `mpiexec: command not found` / `mpirun: command not found` — the env was not
  sourced in this shell (e.g. a new terminal). Re-run the `source` line.

> **Tip.** Since the build environment must be sourced in every new shell, you
> may want a copy outside the repo (e.g. `~/mpas-build/mpas_build_env.sh`) and
> source that one — it stays put across `git checkout` / `git clean`.

## Configuration

Both scripts read overridable environment variables (with sensible defaults):

| Variable          | Default                  | Meaning                                       |
|-------------------|--------------------------|-----------------------------------------------|
| `MPAS_LIBS`       | `$HOME/mpas-build/libs`  | install prefix for PnetCDF (and MPICH)        |
| `MPAS_SRC`        | `$HOME/mpas-build/sources` | tarball download / extract dir              |
| `BUILD_MPICH`     | `0`                      | set `1` to build MPICH from source            |
| `MPICH_VERSION`   | `4.2.3`                  | see <https://www.mpich.org/downloads/>        |
| `PNETCDF_VERSION` | `1.14.1`                 | see <https://parallel-netcdf.github.io/>      |
| `MPI_HOME`        | *(empty)*                | set only for a self-built / non-system MPI    |
