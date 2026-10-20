# kami (Polimi MOX cluster): Rocky Linux 9, OpenPBS, nodes of 2x AMD EPYC 7413
# (Zen3) with 48 cores. Home is shared with nemesis (quota), large data goes to
# /scratch7, which the nodes mount and nemesis does not.
: "${APPTAINER:=/opt/mox/apptainer/bin/apptainer}"
: "${MPAS_DATA_ROOT:=/scratch7/$USER}"
: "${MPAS_BIND:=$MPAS_DATA_ROOT}"
: "${MPAS_NODE_CORES:=48}"
: "${MPAS_SCHEDULER:=pbs}"
# ncpus of a whole-node job: all threads of the compute nodes (96), so that it never lands on the
# smaller nodes outside the profile (kurama has 64)
: "${MPAS_NODE_NCPUS:=96}"
# the image's mpirun must not see the PBS job, whose node file it cannot read
: "${MPAS_HIDE_ENV:=PBS_ENVIRONMENT PBS_JOBID PBS_NODEFILE}"
case ":$PATH:" in
  *:/opt/pbs/bin:*) ;;
  *) [ -d /opt/pbs/bin ] && export PATH=$PATH:/opt/pbs/bin ;;
esac
# MPI between nodes: TCP on the 2x25 GbE bond (no InfiniBand), daemons started over ssh
: "${MPAS_MPI_NET:=bond0}"
: "${MPAS_SSH_KEY:=$HOME/.ssh/id_ed25519_kami}"
