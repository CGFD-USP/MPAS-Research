#!/usr/bin/env bash
# Runs a command on the compute resources of this machine (profile from env.sh):
# detached in the background without a scheduler, or as a PBS job of <cores>
# cores on one node. The command runs in the current folder, its output goes to
# <log>, and the process or job id is printed.
#   MPAS_JOB_NAME   job name (default mpas)
#   MPAS_QSUB_OPTS  further qsub options, e.g. "-l walltime=24:00:00 -l place=excl"
# Usage: bash usp-utils/machines/submit.sh <cores> <log> <command ...>
#   e.g. bash usp-utils/machines/submit.sh 4 smoke.log bash scripts/jw/smoke.sh
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/env.sh"
[ $# -ge 3 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
cores=$1
log=$(realpath -m "$2")
shift 2
job="cd $(printf %q "$PWD") && $(printf '%q ' "$@") > $(printf %q "$log") 2>&1"
case $MPAS_SCHEDULER in
  none)
    setsid nohup bash -c "$job" > /dev/null 2>&1 < /dev/null &
    echo "process $!, log $log"
    ;;
  pbs)
    # a job script on stdin, since kami fails jobs given as "qsub -- <executable>"
    # shellcheck disable=SC2086
    id=$(printf '#!/bin/bash\n%s\n' "$job" | qsub -N "${MPAS_JOB_NAME:-mpas}" \
      -l "select=1:ncpus=$cores:mpiprocs=$cores" -j oe ${MPAS_QSUB_OPTS:-})
    echo "job $id, log $log"
    ;;
  *)
    echo "unknown scheduler $MPAS_SCHEDULER" >&2
    exit 1
    ;;
esac
