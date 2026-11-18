# <machine> (<site>): <OS>, <CPU>, <cores per node>, <scheduler>.
# Copy to <machine>.sh, fill in the values and add the machine's hostnames to
# the case statement of env.sh.
: "${APPTAINER:=apptainer}"
: "${MPAS_DATA_ROOT:=/path/to/large/storage/$USER}"
: "${MPAS_BIND:=$MPAS_DATA_ROOT}"
: "${MPAS_NODE_CORES:=8}"
: "${MPAS_SCHEDULER:=none}"
: "${MPAS_HIDE_ENV:=}"
