# MPAS build dependencies (lean PnetCDF-only setup)

This directory holds a minimal toolchain for compiling MPAS-Atmosphere v8.

## Why so few libraries?

MPAS v8 bundles its own I/O layer, **SMIOL** (`src/external/SMIOL`), and uses it
automatically whenever the `PIO` environment variable is **unset**. In that mode
the only external I/O dependency is **PnetCDF**. There is no need for PIO,
NetCDF-C, NetCDF-Fortran, HDF5 or zlib.

So the full dependency set is just:

| Component  | Source                                   | Notes                                     |
|------------|------------------------------------------|-------------------------------------------|
| Compilers  | system / HPC module stack                | GCC works from v10 to v16                 |
| MPI        | system / HPC module stack (**preferred**) | or build MPICH here (optional)            |
| PnetCDF    | built by `mpas_lib_install.sh`           | the only required external library        |

> Prefer the MPI provided by your system or HPC site — it is usually tuned for
> the local interconnect (e.g. InfiniBand). Only build MPICH yourself when no
> system MPI is available.

## Quick start

You need three things: a Fortran/C **compiler**, an **MPI** library, and
**PnetCDF**. The compiler is almost always already on the machine; this guide
helps you find out whether MPI is there too, and builds PnetCDF for you.

> Where do I run these? The install commands and `source` work from **any
> directory** (all paths are absolute). Only the final `make` must run from the
> MPAS repository root. Below we assume you start at the repo root, e.g.
> `cd /p1-swell/danilocs/MPAS-Research`.

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
cd /path/to/MPAS-Research        # <- replace with your actual repo/worktree path
make gnu CORE=init_atmosphere
make clean CORE=atmosphere && make gnu CORE=atmosphere
```

Common errors:
- `The PNETCDF environment variable isn't set` — you skipped the `source` line
  (or opened a new terminal; re-run it).
- `... previously compiled with incompatible options` — that source tree has
  leftover objects from an earlier build; run `make clean CORE=<core>` first, or
  add `AUTOCLEAN=true` to the `make` command.

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
  sourced in this shell (new terminal, or you switched git branch — see caveat
  below). Re-run the `source` line.

> **Branch caveat.** This script is committed only on the `setup/installation`
> branch, so `usp-utils/install/` is empty on other branches and the `source`
> path vanishes there. Since the machine environment is the same regardless of
> which branch you work on, keep a **branch-independent copy outside the repo**
> (e.g. `~/mpas-build/mpas_build_env.sh`) and source that one instead — it
> survives `git checkout`/`git clean`.

## Configuration

Both scripts read overridable environment variables (with sensible defaults):

| Variable          | Default                  | Meaning                                       |
|-------------------|--------------------------|-----------------------------------------------|
| `MPAS_LIBS`       | `$HOME/mpas-build/libs`  | install prefix for PnetCDF (and MPICH)        |
| `MPAS_SRC`        | `$HOME/mpas-build/sources` | tarball download / extract dir              |
| `BUILD_MPICH`     | `0`                      | set `1` to build MPICH from source            |
| `MPICH_VERSION`   | `4.2.3`                  | see <https://www.mpich.org/downloads/>        |
| `PNETCDF_VERSION` | `1.13.0`                 | see <https://parallel-netcdf.github.io/>      |
| `MPI_HOME`        | *(empty)*                | set only for a self-built / non-system MPI    |

## `make gnu` vs `make gfortran`

The two GNU targets in the top-level `Makefile` differ **only** in two
compile-time diagnostic flags present in the `gnu` recipe: `-std=f2008` and
`-fimplicit-none` (in both `FFLAGS_OPT` and `FFLAGS_DEBUG`). Everything else —
compilers, `-fdefault-real-8`, `-O3`, big-endian conversion, OpenMP — is
identical. Neither flag changes code generation, optimisation, numeric KINDs or
endianness, so the produced binaries are numerically identical. `make gnu` is
just the stricter target and is the recommended one.
