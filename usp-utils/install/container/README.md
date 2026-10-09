# MPAS container image (apptainer)

One image with everything needed to build and run MPAS and to use the usp-utils tools, for
machines that have apptainer (or singularity) but no suitable compiler, MPI and PnetCDF stack,
such as Rocky Linux workstations and clusters. It replaces both native tracks of this folder,
the model build ([`../README.md`](../README.md)) and the pre/post-processing environment
([`../environment_setup.md`](../environment_setup.md)), with the same package lists.

## Content

| component | version | in the image |
|---|---|---|
| base | Ubuntu 24.04 LTS | |
| compilers | GCC and gfortran 13 (Ubuntu) | `gcc`, `gfortran` |
| MPI | Open MPI 4.1 (Ubuntu) | `mpif90`, `mpirun` |
| PnetCDF | 1.14.1, built against that Open MPI | `/opt/pnetcdf`, `PNETCDF` set |
| NetCDF tools | Ubuntu packages | `ncdump`, NCO |
| Python | conda environment of [`../../libs/cgfd-usp-mpas.yml`](../../libs/cgfd-usp-mpas.yml) | `/opt/conda/envs/cgfd-usp-mpas`, `python3` |
| Julia | 1.12.7, shared environment `@cgfd-usp-mpas` of [`../install_julia_environment.jl`](../install_julia_environment.jl) without GLMakie | `/opt/julia`, depot `/opt/julia-depot` |
| LaTeX | TeX Live (Ubuntu), with the packages of the Copernicus class | `latexmk`, `pdflatex`, `bibtex` |

## Build

```bash
bash usp-utils/install/container/build.sh               # into <MPAS-Research>/.apptainer/mpas.sif
bash usp-utils/install/container/build.sh /path/to.sif  # elsewhere
```

The build needs no root (unprivileged apptainer), downloads every component with a checked
checksum, and ends with the image's tests (compilers, MPI, PnetCDF, Python and Julia imports,
latexmk). Rebuild after changing `mpas.def`, `libs/cgfd-usp-mpas.yml` or
`install_julia_environment.jl`. Where `apptainer` is not on `PATH`, set `APPTAINER` to its
path (for example `/opt/mox/apptainer/bin/apptainer` on the Polimi machines). Keep `.apptainer/`
out of git by listing it in `.git/info/exclude`.

| file | content |
|---|---|
| `mpas.def` | image definition |
| `build.sh` | stages the environment files and builds the image |
| `precompile_julia.jl` | build step that precompiles the Julia environment |
| `run.sh` | runs a command in the image |
| `../develop_julia_packages.jl` | points the Julia environment at local checkouts of its packages (below) |

## Use

`run.sh` runs any command in the image from the current folder:

```bash
c=usp-utils/install/container/run.sh
bash $c bash                                                     # shell in the image
bash $c make gnu CORE=init_atmosphere AUTOCLEAN=true PRECISION=double
bash $c make gnu CORE=atmosphere AUTOCLEAN=true PRECISION=double
bash $c mpirun -n 8 ./atmosphere_model                           # from a run folder
bash $c julia usp-utils/pre_proc/grid_creation_scripts/regenerate-mesh.jl --help
bash $c python3 usp-utils/post_proc/plotting_scripts/mpas_plot.py --help
bash $c latexmk -pdf paper.tex
```

The image sets `PNETCDF` and the paths, and `run.sh` sets `MPAS_ROOT` and `PYTHONPATH`, so
neither `mpas_build_env.sh` nor `setup_environment.sh` is sourced inside it.

| variable | purpose | default |
|---|---|---|
| `MPAS_SIF` | image | `<MPAS-Research>/.apptainer/mpas.sif` |
| `APPTAINER` | apptainer executable | `apptainer` or `singularity` on `PATH` |
| `MPAS_BIND` | extra folders visible in the image, colon separated (data outside home) | none |
| `MPAS_JULIA_DEPOT` | writable Julia depot | `~/.julia-mpas` |
| `MPAS_HIDE_ENV` | variables hidden from the image, space separated (a scheduler's job variables) | none |

On the machines with a profile in [`../../machines/`](../../machines/README.md), sourcing its
`env.sh` sets `APPTAINER`, `MPAS_BIND` and `MPAS_HIDE_ENV`.

## Local checkouts of the Julia packages

To run the operator and mesh scripts with checkouts of the Julia packages (a branch, uncommitted
edits) instead of the versions in the image, clone them into one folder, by convention
`<MPAS-Research>/external` (listed in `.git/info/exclude`), and develop them once:

```bash
mkdir -p external && cd external
git clone git@github.com:favba/TensorsLite.jl.git
for p in TensorsLiteGeometry VoronoiMeshes VoronoiOperators MPASMeshes; do
  git clone git@github.com:CGFD-USP/$p.jl.git
done
cd .. && bash usp-utils/install/container/run.sh julia usp-utils/install/develop_julia_packages.jl external
```

`develop_julia_packages.jl` copies `@cgfd-usp-mpas` from the image into `MPAS_JULIA_DEPOT`, afresh
on every run so that the copy follows the image after a rebuild, and points it at every package
of `external/`, so the scripts' `--project=@cgfd-usp-mpas` uses the
checkouts while the other dependencies stay those precompiled in the image. Edits take effect on
the next Julia start, after a recompilation of the changed packages. Deleting
`$MPAS_JULIA_DEPOT/environments/cgfd-usp-mpas` returns to the image's environment. The same
script works natively, where it develops the checkouts in the `~/.julia` environment.

## Notes

- Julia packages installed from git (TensorsLite and the CGFD packages) and SmallCollections
  compile on their first use on each CPU type, about a minute, into `MPAS_JULIA_DEPOT`, and load
  in seconds afterwards, until the next image build. LLVM fails on the SIMD code of the former for a generic CPU, and the
  latter picks its instructions (AVX-512 or not) from the CPU it is compiled on, so an image
  cache built on a newer CPU would crash on an older one. The other dependencies are
  precompiled in the image for the CPUs of current x86-64 machines.
  The writable depot is separate from `~/.julia`, so a native `@cgfd-usp-mpas` environment does
  not shadow the image's one.
- GLMakie needs a display and is left out. Plots in the image go through Python.
- `python3` is the conda environment's. Its other executables come after the system compilers
  and MPI on `PATH`, so a build always uses the image's Open MPI.
- `mpirun` of the image runs within one node. Runs across nodes need a host MPI that can start
  the image's ranks, which is not set up here.
