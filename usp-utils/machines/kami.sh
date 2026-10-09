# kami (Polimi MOX cluster): Rocky Linux 9, OpenPBS, nodes of 2x AMD EPYC 7413
# (Zen3) with 48 cores. Home is shared with nemesis (quota), large data goes to
# /scratch7, which the nodes mount and nemesis does not.
: "${APPTAINER:=/opt/mox/apptainer/bin/apptainer}"
: "${MPAS_DATA_ROOT:=/scratch7/$USER}"
: "${MPAS_BIND:=$MPAS_DATA_ROOT}"
: "${MPAS_NODE_CORES:=48}"
: "${MPAS_SCHEDULER:=pbs}"
# the image's mpirun must not see the PBS job, whose node file it cannot read
: "${MPAS_HIDE_ENV:=PBS_ENVIRONMENT PBS_JOBID PBS_NODEFILE}"
case ":$PATH:" in
  *:/opt/pbs/bin:*) ;;
  *) [ -d /opt/pbs/bin ] && export PATH=$PATH:/opt/pbs/bin ;;
esac
