# Schemes of the consistent operators for the benchmark and real-case harnesses (bash): source schemes.sh
# The single place that maps the name of a configuration to namelist options of &nhyd_model.
# scheme_options <name> prints one "key = value" line per option. A name ending in +em also sets
# config_edge_midpoint_flux (F(Cons)).
#   name                    paper name        tangential  kinetic energy  vertex blend
#   trsk                    MPAS              trsk        trsk            default
#   trsk-newke-consistent   T(MPAS)-KE(Cons)  trsk        perot           default
#   trsk-newke-lsq2         T(MPAS)-KE(LSq2)  trsk        lsq2            default
#   consistent-vke          T(Cons)-KE(Cons)  perot       perot           default
#   lsq2-vke                T(Cons)-KE(LSq2)  perot       lsq2            default
#   consistent, lsq2        as the two above, cell kinetic energy alone (config_ke_cell_weight = 1)
#   trsk-cellke-consistent, trsk-cellke-lsq2    as trsk-newke-*, cell kinetic energy alone
#   consistent-trskke       T(Cons)-KE(MPAS)  perot       trsk            default
#   trsk-cellvel            MPAS with the Perot cell wind (config_cell_wind_reconstruction = 'perot'), physics and output
scheme_options() {
  local tangential ke blend cell=
  case ${1%+em} in
    trsk) tangential=trsk ke=trsk blend=blend ;;
    trsk-cellvel) tangential=trsk ke=trsk blend=blend cell=perot ;;
    trsk-newke-consistent) tangential=trsk ke=perot blend=blend ;;
    trsk-newke-lsq2) tangential=trsk ke=lsq2 blend=blend ;;
    trsk-cellke-consistent) tangential=trsk ke=perot blend=cell ;;
    trsk-cellke-lsq2) tangential=trsk ke=lsq2 blend=cell ;;
    consistent-vke) tangential=perot ke=perot blend=blend ;;
    lsq2-vke) tangential=perot ke=lsq2 blend=blend ;;
    consistent) tangential=perot ke=perot blend=cell ;;
    lsq2) tangential=perot ke=lsq2 blend=cell ;;
    consistent-trskke) tangential=perot ke=trsk blend=blend ;;
    *) echo "unknown configuration $1" >&2; return 1 ;;
  esac
  echo "config_tangential_reconstruction = '$tangential'"
  echo "config_ke_reconstruction = '$ke'"
  [ "$blend" != cell ] || echo "config_ke_cell_weight = 1.0"
  [ -z "$cell" ] || echo "config_cell_wind_reconstruction = '$cell'"
  [ "$1" = "${1%+em}" ] || echo "config_edge_midpoint_flux = true"
  return 0
}
