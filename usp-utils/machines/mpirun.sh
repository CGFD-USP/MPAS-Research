#!/usr/bin/env bash
# Runs an MPI program of the MPAS image on <ranks> ranks, in the current folder:
# - on this node, without a scheduler or when the ranks fit the node of the job
#   (the first one);
# - over the nodes of a PBS job otherwise: the image's mpirun starts its daemons
#   on the other nodes over ssh, inside the image, reaching the nodes by their
#   node file names (the MPI network) with host keys from IPA
#   (sss_ssh_knownhostsproxy) or ssh-keyscan.
# TCP listens on high ports (50000 and up), since these hosts refuse some low
# ones. Profile variables (machines/<machine>.sh):
#   MPAS_MPI_NET   network interface between nodes (all when empty)
#   MPAS_SSH_KEY   ssh key accepted between the nodes
#   MPAS_MPI_BIND  rank binding, core or none (default core in a PBS job, none elsewhere)
# Further mpirun options: $MPAS_MPIRUN_OPTS.
# Usage: bash usp-utils/machines/mpirun.sh <ranks> <program> [arguments]
set -eu
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
. "$here/env.sh"
[ $# -ge 2 ] || { sed -n 's/^# Usage: //p' "$0" >&2; exit 1; }
ranks=$1
shift
run=$MPAS_ROOT/usp-utils/install/container/run.sh
sif=${MPAS_SIF:-$MPAS_ROOT/.apptainer/mpas.sif}
opts=(--mca btl self,vader,tcp
  --mca btl_tcp_port_min_v4 50000 --mca btl_tcp_port_range_v4 2000
  --mca btl_tcp_port_min_v6 50000 --mca btl_tcp_port_range_v6 2000)
# shellcheck disable=SC2206
opts+=(${MPAS_MPIRUN_OPTS:-})

nodes=1 ppn=$ranks
if [ "$MPAS_SCHEDULER" = pbs ] && [ -n "${PBS_NODEFILE:-}" ]; then
  ppn=$(grep -cx "$(head -1 "$PBS_NODEFILE")" "$PBS_NODEFILE")
  nodes=$(((ranks + ppn - 1) / ppn))
  bind=${MPAS_MPI_BIND:-core}
else
  bind=${MPAS_MPI_BIND:-none}
fi
[ "$nodes" -gt 1 ] || ppn=$ranks
opts+=(--bind-to "$bind" --map-by "ppr:$ppn:node")

if [ "$nodes" -eq 1 ]; then
  exec bash "$run" mpirun -n "$ranks" "${opts[@]}" "$@"
fi

[ "$((nodes * ppn))" -eq "$ranks" ] || { echo "$ranks ranks do not fill $nodes nodes of $ppn" >&2; exit 1; }
[ "$(uniq "$PBS_NODEFILE" | wc -l)" -ge "$nodes" ] || { echo "the job has fewer than $nodes nodes" >&2; exit 1; }
# a work folder that every node sees (the run folder)
work=$(mktemp -d "$PWD/.mpirun.XXXXXX")
trap 'rm -rf "$work"' EXIT
# The node file names the nodes on the MPI network, while IPA knows their ssh
# host keys under their hostnames: each node copies its /etc/hostname here
# (pbs_tmrsh runs a program, not a shell), and its keys from IPA are recorded
# under its node file name; ssh-keyscan for a node that IPA does not know.
for v in $(uniq "$PBS_NODEFILE" | head -n "$nodes"); do
  pbs_tmrsh "$v" /usr/bin/cp /etc/hostname "$work/hostname.$v" || { echo "pbs_tmrsh failed on $v" >&2; exit 1; }
  h=$(tr -d ' \n' < "$work/hostname.$v")
  keys=
  if [ -n "$h" ] && command -v sss_ssh_knownhostsproxy > /dev/null; then
    # IPA can fail transiently when several jobs start together
    for try in 1 2 3; do
      keys=$(sss_ssh_knownhostsproxy -k "$h" 2> /dev/null) && [ -n "$keys" ] && break
      sleep 5
    done
  fi
  # mpirun reaches a node by its short name
  if [ -n "$keys" ]; then
    echo "$keys" | sed "s/^/$v,${v%%.*} /" >> "$work/known_hosts"
  else
    keys=$(ssh-keyscan -t ed25519 "$v" 2> /dev/null)
    [ -n "$keys" ] || { echo "no ssh host key for $v" >&2; exit 1; }
    echo "host key of $v from ssh-keyscan (not in IPA)" >&2
    echo "$keys" | sed "s/^[^ ]*/$v,${v%%.*}/" >> "$work/known_hosts"
  fi
  echo "$v slots=$ppn" >> "$work/hostfile"
done

# the remote daemons see the folders that run.sh binds
binds=(--bind "$MPAS_ROOT")
IFS=: read -r -a extra <<< "${MPAS_BIND:-}"
for p in "${extra[@]}"; do
  [ -n "$p" ] && [ -d "$p" ] && binds+=(--bind "$p")
done
ssh_args="-o IdentitiesOnly=yes -o BatchMode=yes -o UserKnownHostsFile=$work/known_hosts -o StrictHostKeyChecking=yes"
[ -z "${MPAS_SSH_KEY:-}" ] || ssh_args="-i $MPAS_SSH_KEY $ssh_args"
opts+=(--hostfile "$work/hostfile"
  --mca plm_rsh_args "$ssh_args"
  --mca orte_launch_agent "$APPTAINER exec ${binds[*]} $sif orted"
  --mca plm_rsh_no_tree_spawn 1
  # a detached daemon would leave apptainer to unmount the image under the ranks
  --mca orte_leave_session_attached 1)
[ -z "${MPAS_MPI_NET:-}" ] || opts+=(--mca btl_tcp_if_include "$MPAS_MPI_NET" --mca oob_tcp_if_include "$MPAS_MPI_NET")
bash "$run" mpirun -n "$ranks" "${opts[@]}" "$@"
