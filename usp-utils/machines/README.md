# Machine profiles

Per-machine settings of the MPAS tools (where large data goes, which apptainer, cores, scheduler),
so the same scripts run on every machine. Each machine has one profile, `<machine>.sh`, and
`env.sh` picks it from the hostname.

| file | content |
|---|---|
| `env.sh` | picks and exports the profile of this machine (source it, bash) |
| `setup.sh` | prepares a machine: data and build roots, the MPAS image, the Julia checkouts |
| `nemesis.sh` | nemesis, Polimi MOX workstation (168 cores, no scheduler) |
| `kami.sh` | kami, Polimi MOX cluster (48 cores per node, OpenPBS) |
| `_template.sh` | starting point for a new machine |

## Use

On a new machine, once:

```bash
bash usp-utils/machines/setup.sh
```

It checks apptainer, creates the data root and the build root, builds the image of
[`../install/container/`](../install/container/README.md) when `.apptainer/mpas.sif` is missing
(about 10 min), and, when `<MPAS-Research>/external` holds checkouts of the Julia packages, points
the image's Julia environment at them (`develop_julia_packages.jl`). Running it again only checks.

In every shell that runs the tools:

```bash
source usp-utils/machines/env.sh
```

## Variables

Values already exported are kept, so exporting one before sourcing overrides the profile.

| variable | meaning | nemesis | kami |
|---|---|---|---|
| `MPAS_MACHINE` | profile name, set it to skip the hostname detection | `nemesis` | `kami` |
| `MPAS_ROOT` | the MPAS-Research tree | from `env.sh` | from `env.sh` |
| `APPTAINER` | apptainer executable | `/opt/mox/apptainer/bin/apptainer` | same |
| `MPAS_DATA_ROOT` | per-user large storage (runs, grids, operator files), never the quota-limited home | `/home/nemesis/$USER` | `/scratch7/$USER` |
| `MPAS_BIND` | folders the image sees besides home, colon separated | the data root | the data root |
| `MPAS_NODE_CORES` | physical cores of one node | 168 | 48 |
| `MPAS_SCHEDULER` | `none` or `pbs` | `none` | `pbs` |
| `MPAS_HIDE_ENV` | variables hidden from the image by `run.sh` | none | `PBS_ENVIRONMENT PBS_JOBID PBS_NODEFILE` |
| `MPAS_BUILD_ROOT` | MPAS builds | `~/mpas-builds` | same (shared home) |

On kami, `env.sh` also adds `/opt/pbs/bin` to `PATH`, and the image's `mpirun` inside a PBS job
runs with the PBS variables hidden, since it would otherwise look for the job's node file, which
the image cannot read. Home is shared between nemesis and kami, so the image and the builds serve
both, while the data roots are separate (nemesis does not mount `/scratch7`).

## Adding a machine

1. Copy `_template.sh` to `<machine>.sh` and fill in its values.
2. Add the machine's hostnames (`hostname -s`, compute nodes included) to the `case` statement of
   `env.sh`.
3. Run `bash usp-utils/machines/setup.sh` there.
