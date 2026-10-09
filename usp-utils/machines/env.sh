# Machine settings of the MPAS tools (bash): source usp-utils/machines/env.sh
# Picks the profile <machine>.sh of this folder from the hostname, or from
# $MPAS_MACHINE, and exports its variables. Values already set are kept.
#   MPAS_MACHINE     machine name, the profile file without .sh
#   MPAS_ROOT        the MPAS-Research tree holding this file
#   APPTAINER        apptainer executable
#   MPAS_DATA_ROOT   per-user large storage (runs, grids, operator files)
#   MPAS_BIND        folders the image must see, colon separated
#   MPAS_NODE_CORES  physical cores of one node
#   MPAS_SCHEDULER   none or pbs
#   MPAS_HIDE_ENV    variables hidden from the image (run.sh)
#   MPAS_BUILD_ROOT  where build_mpas.sh writes, default ~/mpas-builds
# A new machine: copy _template.sh to <machine>.sh and add its hostnames below.
_mpas_here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -z "${MPAS_MACHINE:-}" ]; then
  case "$(hostname -s)" in
    nemesis*) MPAS_MACHINE=nemesis ;;
    kami* | e[0-9][0-9]s[0-9]*) MPAS_MACHINE=kami ;;
  esac
fi
if [ -z "${MPAS_MACHINE:-}" ] || [ ! -f "$_mpas_here/$MPAS_MACHINE.sh" ]; then
  echo "no machine profile for '${MPAS_MACHINE:-$(hostname -s)}' in $_mpas_here, see README.md there" >&2
  unset _mpas_here
  return 1
fi
. "$_mpas_here/$MPAS_MACHINE.sh"
: "${MPAS_ROOT:=$(dirname "$(dirname "$_mpas_here")")}"
: "${MPAS_BUILD_ROOT:=$HOME/mpas-builds}"
unset _mpas_here
export MPAS_MACHINE MPAS_ROOT APPTAINER MPAS_DATA_ROOT MPAS_BIND MPAS_NODE_CORES \
  MPAS_SCHEDULER MPAS_HIDE_ENV MPAS_BUILD_ROOT
