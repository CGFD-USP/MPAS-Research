# nemesis (Polimi MOX workstation): Rocky Linux 9, 2x AMD EPYC 9634 (Zen4),
# 168 cores, no scheduler. Home is the shared kami home (quota), large data
# goes to the local disk /home/nemesis.
: "${APPTAINER:=/opt/mox/apptainer/bin/apptainer}"
: "${MPAS_DATA_ROOT:=/home/nemesis/$USER}"
: "${MPAS_BIND:=$MPAS_DATA_ROOT}"
: "${MPAS_NODE_CORES:=168}"
: "${MPAS_SCHEDULER:=none}"
: "${MPAS_HIDE_ENV:=}"
