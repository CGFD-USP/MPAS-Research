# Machine profiles

Per-machine settings of the MPAS tools (where large data goes, which apptainer, cores, scheduler),
so the same scripts run on every machine. Each machine has one profile, `<machine>.sh`, and
`env.sh` picks it from the hostname.

| file | content |
|---|---|
| `env.sh` | picks and exports the profile of this machine (source it, bash) |
| `setup.sh` | prepares a machine: data and build roots, the MPAS image, the Julia checkouts |
| `submit.sh` | runs a command on the compute resources: detached without a scheduler, a job of one or more nodes with PBS |
| `mpirun.sh` | runs an MPI program of the MPAS image on this node, or across the nodes of a PBS job |
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

Long runs go through `submit.sh`, which needs no change between machines:

```bash
bash usp-utils/machines/submit.sh <cores> <log> <command ...>
```

Without a scheduler it starts the command detached (`setsid nohup`) and prints its process id,
which is also its session id (stop it with `pkill -s <id>`). With PBS it submits a job of
`<cores>` cores on each of `MPAS_JOB_NODES` nodes (default 1; whole nodes when more than one;
`MPAS_QSUB_OPTS` adds options such as a walltime or `-l place=excl`) and prints the job id.
Either way the command runs in the current folder and writes its output to `<log>`, since kami
does not deliver the job output files.

MPI programs of the image run through `mpirun.sh <ranks> <program> [arguments]`. On one node it
calls the image's `mpirun` (ranks bound to cores inside a PBS job, unbound elsewhere). When the
ranks need more nodes than one of the PBS job, the image's `mpirun` starts its daemons on the other
nodes over ssh, inside the image: the hostnames come from `pbs_tmrsh`, the host keys from IPA
(`sss_ssh_knownhostsproxy`) or `ssh-keyscan`, and MPI traffic stays on `MPAS_MPI_NET`. The TCP
transport listens on ports from 50000, because nemesis and kami refuse some low ports (IPv4 and
IPv6), which left ranks unreachable and crashed runs of more than about 24 ranks.

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
| `MPAS_MPI_NET` | network interface of MPI between nodes (`mpirun.sh`) | none | `bond0` (2x25 GbE, no InfiniBand) |
| `MPAS_SSH_KEY` | ssh key accepted between the nodes of a job (`mpirun.sh`) | none | `~/.ssh/id_ed25519_kami` |

On kami, `env.sh` also adds `/opt/pbs/bin` to `PATH`, and the image's `mpirun` inside a PBS job
runs with the PBS variables hidden, since it would otherwise look for the job's node file, which
the image cannot read. Home is shared between nemesis and kami, so the image and the builds serve
both, while the data roots are separate (nemesis does not mount `/scratch7`).

## Adding a machine

1. Copy `_template.sh` to `<machine>.sh` and fill in its values.
2. Add the machine's hostnames (`hostname -s`, compute nodes included) to the `case` statement of
   `env.sh`.
3. Run `bash usp-utils/machines/setup.sh` there.
