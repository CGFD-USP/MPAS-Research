# Installing libraries and building MPAS — recommended workflow

This guide walks you, end to end, through preparing the environment and
compiling the MPAS model on a fresh Linux machine, following the **NCAR
MPAS-Atmosphere tutorial** approach for the I/O libraries.

There are two independent concerns; you can do both or just the one you need:

| Concern | What it is for | Tooling |
|---------|----------------|---------|
| **Python / Julia environments** | pre- and post-processing: mesh creation, plotting, NetCDF handling | conda + Julia |
| **C/Fortran build toolchain** | actually compiling `init_atmosphere_model` and `atmosphere_model` | MPICH + HDF5 + (Pn)etCDF + PIO, then `make` |

> You can compile MPAS **without** conda/Julia, but you will need them to
> generate Voronoi meshes and to process model I/O for real runs.

All commands below assume you start from the repository's `usp-utils/`
directory unless stated otherwise.

---

## Step 0 — Check prerequisites

You need a C/C++/Fortran compiler, `make`, `cmake` (for PIO), `git`,
`curl`/`wget`, and `tar`/`gzip`/`bzip2` (HDF5 ships as `.tar.bz2`):

```sh
gfortran --version && gcc --version && g++ --version
make --version && cmake --version
git --version && curl --version && bzip2 --version
```

For the Python/Julia tooling you also need `conda` on your `PATH`, and
[`juliaup`](https://github.com/JuliaLang/juliaup) (or any Julia ≥ 1.10) if you
plan to use the mesh-generation scripts.

> **Two independent tracks.** Steps 1–3 set up the Python/Julia tooling for
> pre/post-processing. Steps 4–6 build and compile the model and do **not**
> require the conda or Julia environments — they only need the build
> environment from Step 5. You can run them in a clean shell if you prefer.

---

## Step 1 — Conda environment (pre/post-processing)

Run once. Creates the `cgfd-usp-mpas` conda environment from
`libs/cgfd-usp-mpas.yml`:

```sh
./install_conda_environment.sh
```

Re-running it later updates the environment instead.

---

## Step 2 — Julia environment (only if you use the `.jl` mesh tools)

The `.jl` scripts rely on a **shared** Julia environment, also called
`cgfd-usp-mpas`.

> **Important — two known gotchas on this stack:**
>
> 1. **Segfault from `LD_LIBRARY_PATH`.** In the MPAS/conda environment,
>    `LD_LIBRARY_PATH` shadows Julia's bundled libraries and crashes `Pkg`
>    during network/git operations. Always install/update the Julia
>    environment with that variable cleared:
>    ```sh
>    env -u LD_LIBRARY_PATH julia install_julia_environment.jl
>    ```
> 2. **Possible upstream version conflict.** `Pkg` may fail to resolve when
>    favba's packages are temporarily out of sync (e.g. a `Zeros` compat
>    mismatch between `TensorsLite` and `VoronoiMeshes`/`MPASMeshes`). If you
>    hit that, a temporary workaround is tracked separately on the
>    `julia/zeros-compat-workaround` branch — use it (or check with the team)
>    until the upstream packages are back in sync.

To **run** the mesh scripts afterwards you do *not* need to activate anything
manually — they select the shared environment via their shebang
(`--project=@cgfd-usp-mpas`). Running the scripts (as opposed to installing
packages) does not trigger the segfault, so no `LD_LIBRARY_PATH` handling is
needed at run time.

---

## Step 3 — Source the environment

This sets `MPAS_ROOT`, creates the `runs/`, `grids/`, and `met_data/`
directories, puts the helper Python modules on `PYTHONPATH`, and activates the
conda environment:

```sh
. setup_environment.sh      # or setup_environment.fish for the fish shell
```

---

## Step 4 — Build the I/O libraries (NCAR workflow)

The model needs MPI, HDF5, PnetCDF, NetCDF-C, NetCDF-Fortran, and PIO. The
`install/mpas_lib_install.sh` script builds them all from source — including
its **own MPICH**, so you do not need a system MPI. It is kept as the
**unmodified NCAR script** — try it as-is first; if a step fails, see
[Known build issues (optional fixes)](#known-build-issues-optional-fixes) below.

> **PIO is optional.** MPAS v8 ships a bundled I/O layer (SMIOL,
> `src/external/SMIOL`) and falls back to it automatically when the `PIO`
> environment variable is unset. The NCAR workflow here builds and uses PIO; if
> you skip it (omit PIO from the build and leave `PIO` unset in Step 5), MPAS
> still compiles and runs using SMIOL. `NETCDF` and `PNETCDF` are always
> required.

### 4a. Download the source tarballs

```sh
./install/download_mpas_lib_sources.sh /path/to/sources
# default if omitted: $HOME/mpas-build/sources
```

This fetches the six tarballs in the exact versions `mpas_lib_install.sh`
expects, verifies their integrity, and writes a `SHA256SUMS` manifest. Pass
`--with-pio` to also pre-clone `NCAR/ParallelIO` (otherwise the install script
clones it itself at build time).

### 4b. Point the install script at your paths

`mpas_lib_install.sh` is a **versioned template** with placeholder paths — do
not edit it in place. Instead copy it to a personal `*.local.sh` (these are
git-ignored, so your machine-specific paths never get committed):

```sh
cp install/mpas_lib_install.sh install/mpas_lib_install.local.sh
```

Then edit the two paths at the top of your `mpas_lib_install.local.sh`:

```sh
export LIBSRC=/path/to/sources       # same directory you downloaded into
export LIBBASE=/path/to/mpas-libs    # writable install prefix for the libs
```

> Pick a disk with room for both (the build is sizeable). E.g.
> `LIBSRC=$HOME/mpas-build/sources`, `LIBBASE=$HOME/mpas-build/libs`, or a
> scratch disk like `/p1-swell/<user>/mpas-build/...`.

### 4c. Run the build

Run it from an empty working directory (it extracts the tarballs into the
current directory and cleans up as it goes):

```sh
mkdir -p /path/to/build_work && cd /path/to/build_work
bash /full/path/to/usp-utils/install/mpas_lib_install.local.sh 2>&1 | tee mpas_lib_build.log
```

Order built: MPICH → zlib → HDF5 → PnetCDF → NetCDF-C → NetCDF-Fortran → PIO.

### Known build issues (optional fixes)

Run the unmodified script first. If a step fails, the fixes below have worked
for us — apply them **in your `.local.sh` copy**, not in the versioned template.
They depend on the compiler/OS, so they are not guaranteed to be the right fix
on every system. **If you hit a build failure and find a different solution,
please add it here** so the next person benefits.

- **MPICH configure fails on the Fortran check** with
  `gfortran allows mismatched arguments... no` /
  `configure: error: The Fortran compiler gfortran will not compile files that`
  `call the same routine with arguments of different types` — this happens with
  **gfortran ≥ 10**, because MPICH 3.3.1's F77 check uses `FFLAGS`, which in the
  original script does not carry the needed flag. Add
  `-fallow-argument-mismatch` to `FFLAGS` in your `.local.sh`:
  ```sh
  export FFLAGS="-g -fbacktrace -fallow-argument-mismatch"
  ```
  *Verified on gfortran 13.3.* If MPICH does not build, every later library
  that configures with `CC=mpicc` will then fail with the misleading
  `C compiler cannot create executables` (the cascade from the missing `mpicc`).

---

## Step 5 — Export the build environment

`mpas_lib_install.sh` sets the needed variables, but only inside its own
shell — they are gone once it exits. Before compiling MPAS, set them in your
shell (adjust `LIBBASE` to the value you used above). Save this block as
`install/mpas_build_env.local.sh` (git-ignored by `*.local.sh`) and `source`
it whenever you build or run the model:

```sh
export LIBBASE=/path/to/mpas-libs
export PATH="$LIBBASE/bin:$PATH"                 # so make finds the MPICH mpif90/mpicc
export LD_LIBRARY_PATH="$LIBBASE/lib:$LD_LIBRARY_PATH"
export NETCDF="$LIBBASE"
export PNETCDF="$LIBBASE"
export PIO="$LIBBASE"
export MPAS_EXTERNAL_LIBS="-L$LIBBASE/lib -lhdf5_hl -lhdf5 -ldl -lz"
export MPAS_EXTERNAL_INCLUDES="-I$LIBBASE/include"
```

Verify the MPI wrappers are found:

```sh
which mpif90 mpicc      # should point inside $LIBBASE/bin
```

---

## Step 6 — Compile MPAS

From the **repository root** (`$MPAS_ROOT`), build the two atmosphere cores.
The `gfortran` target uses the MPICH wrappers (`mpif90`/`mpicc`):

```sh
cd "$MPAS_ROOT"
make gfortran CORE=init_atmosphere
make clean    CORE=atmosphere      # clean shared objects between cores
make gfortran CORE=atmosphere
```

Useful options: `PRECISION=double`, `DEBUG=true`, `OPENMP=true`. (`gnu` is an
alias of the `gfortran` target.)

On success you get the executables `init_atmosphere_model` and
`atmosphere_model` in the repository root. They are git-ignored build
artifacts, so they persist on disk across branch switches in the same working
directory (valid as long as `src/` is unchanged).

---

## Step 7 — Set up a run directory

Use the helper to link the freshly built executables and copy the default
namelists, streams, and physics lookup tables into a run directory:

```sh
./testing_and_setup/atmosphere/setup_run_dir.py "$MPAS_ROOT/runs/my_first_run"
```

Then place your mesh in `grids/` and meteorological input in `met_data/`, edit
the namelists/streams, and run the cores. MPAS is an MPI program, so launch it
with `mpirun` (make sure the Step 5 environment is sourced, so the MPICH
`mpirun` is on your `PATH`):

```sh
cd "$MPAS_ROOT/runs/my_first_run"
mpirun -np 4 ./init_atmosphere_model     # build initial conditions
# ... edit namelist.atmosphere / streams.atmosphere ...
mpirun -np 4 ./atmosphere_model          # integrate the model
```

> Running `./atmosphere_model` directly with no namelist/inputs aborts via
> `MPI_Abort` almost immediately — that is expected, not a build problem.

---

## Quick reference (the whole flow)

```sh
# one-time environment setup
./install_conda_environment.sh
env -u LD_LIBRARY_PATH julia install_julia_environment.jl   # see Step 2 if Pkg fails to resolve (Zeros conflict)
. setup_environment.sh

# build the I/O libraries (NCAR workflow)
./install/download_mpas_lib_sources.sh "$HOME/mpas-build/sources"
cp install/mpas_lib_install.sh install/mpas_lib_install.local.sh   # then edit LIBSRC/LIBBASE in the copy
mkdir -p "$HOME/mpas-build/work" && cd "$HOME/mpas-build/work"
bash "$MPAS_ROOT/usp-utils/install/mpas_lib_install.local.sh" 2>&1 | tee build.log

# compile the model
source "$MPAS_ROOT/usp-utils/install/mpas_build_env.local.sh"   # export block from Step 5
cd "$MPAS_ROOT"
make gfortran CORE=init_atmosphere
make clean CORE=atmosphere && make gfortran CORE=atmosphere

# prepare and launch a run
./testing_and_setup/atmosphere/setup_run_dir.py "$MPAS_ROOT/runs/my_first_run"
cd "$MPAS_ROOT/runs/my_first_run"
mpirun -np 4 ./init_atmosphere_model      # then edit namelist.atmosphere and run atmosphere_model
```

---

## Troubleshooting

- **Julia segfaults during `Pkg` operations** — clear `LD_LIBRARY_PATH`:
  `env -u LD_LIBRARY_PATH julia ...` (see Step 2).
- **Julia resolve fails on `Zeros`** — temporary upstream conflict; see Step 2 and the
  `julia/zeros-compat-workaround` branch.
- **`make` can't find `mpif90`/`mpicc`** — `$LIBBASE/bin` is not on `PATH`; re-source
  the Step 5 environment.
- **`ERROR: The PNETCDF environment variable isn't set.`** — export `PNETCDF=$LIBBASE`
  (Step 5).
- **Library build fails with `C compiler cannot create executables`** — this is almost
  always a *cascade*: MPICH failed to build first (so `mpicc` is missing), and the later
  libs that use `CC=mpicc` then can't link. Scroll up to the MPICH step — with gfortran
  ≥ 10 the real error there is the Fortran mismatched-arguments check. See
  [Known build issues (optional fixes)](#known-build-issues-optional-fixes) for the
  `FFLAGS` fix to apply in your `.local.sh`.
- **Switching to a branch that changes `src/`** — rebuild; the on-disk binary is not
  recompiled automatically and is not tracked by git.
