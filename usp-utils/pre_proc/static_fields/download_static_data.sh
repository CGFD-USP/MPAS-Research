#!/usr/bin/env bash
#
# download_static_data.sh
#
# Download the inputs needed for MPAS init_atmosphere static-field generation
# (config_init_case = 7):
#   1. a global mesh from the NCAR MPAS-Atmosphere mesh repository
#      (grid.nc + graph.info + pre-made graph.info.part.N partitions);
#   2. the MPAS geographical ("static"/terrain) dataset that init_atmosphere
#      interpolates onto the mesh (topography, land use, soil, greenness, ...).
#
# Sources:
#   meshes        -> https://www2.mmm.ucar.edu/projects/mpas/atmosphere_meshes/
#   static (mpas) -> https://www2.mmm.ucar.edu/projects/mpas/site/downloads/static.html
#   WPS geog      -> https://www2.mmm.ucar.edu/wrf/src/wps_files/
#
# The default MPAS bundle (mpas_static.tar.bz2) is COMPLETE for the standard
# real-data config (GMTED2010 topo + MODIS 30s land use + STATSGO soil +
# Noah-MP). It contains every subdirectory mpas_init_atm_static.F reads for that
# config, including soilgrids/{soilcomp,texture_layer1-4} (required because
# config_noahmp_static defaults to TRUE even though it is not written into the
# generated namelist) and modis_landuse_20class_30s. The WRF geog_high_res
# bundle does NOT contain those, which is why 'mpas' is the default here.
#
# Optional add-ons (page above) — only for non-default configs:
#   ugwp -> topo_ugwp.tar.gz + ugwp_limb_tau.nc  (UGWP/GSL gravity-wave drag,
#           config_native_gwd_gsl_static = true / UGWP suite)
#   15s  -> modis_landuse_20class_15s.tar.bz2     (15-arc-second land use)
#   bnu  -> bnu_soiltype_top.tar.bz2              (BNU soil category, config_soilcat_data='BNU')
#
# IMPORTANT (extraction): the bundles carry a single leading directory
# (e.g. mpas_static/ or WPS_GEOG/). This script strips it so datasets land
# directly under WPS_GEOG/<dataset>, matching config_geog_data_path. Extracting
# the tarball "as is" produces WPS_GEOG/mpas_static/<dataset> and init_atmosphere
# then fails with "Could not find an 'index' file" — that is the usual pitfall.
#
# Usage:
#   ./download_static_data.sh [--mesh NAME] [--geog mpas|high|low|none]
#                             [--optional LIST|all] [--dest DIR] [--no-extract]
#
#   --mesh NAME     Mesh to download (default: x1.40962), or 'none' to skip.
#                   See the mesh page for the full list (x1.10242, x1.40962,
#                   x1.163842, x1.655362, x1.2621442, variable-res x4/x5..., etc.).
#   --geog SET      Geographical data set:
#                     mpas (~2.2 GB, DEFAULT) — MPAS-curated bundle. Complete.
#                     high (~2.6 GB) — WRF 'geog_high_res_mandatory' (INCOMPLETE
#                          for MPAS: lacks modis_landuse_20class_30s, soilgrids).
#                     low  (~150 MB) — WRF low-res mandatory.
#                     none — skip the geog.
#   --optional LIST Comma-separated add-ons to also fetch into WPS_GEOG:
#                   any of ugwp,15s,bnu  (or 'all'). Default: none.
#   --dest DIR      Base directory. Default: repo root above usp-utils.
#                   Tarballs cache into <dest>/met_data; datasets extract into
#                   <dest>/met_data/WPS_GEOG (= config_geog_data_path).
#   --no-extract    Download/verify the archives but do not extract them.
#
# Download just one component by setting the other to 'none', e.g.:
#   ./download_static_data.sh --mesh x1.10242 --geog none    # only a new mesh
#   ./download_static_data.sh --mesh none --geog mpas         # only the geog data
#   ./download_static_data.sh --mesh none --geog none --optional ugwp  # only add-ons
#
# Idempotent: existing, valid downloads are skipped; each archive's extraction is
# marked in WPS_GEOG/.extracted_<archive>; checksums recorded in SHA256SUMS.

set -uo pipefail

CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
INFO="${CYAN}[INFO]${NC}"; WARN="${YELLOW}[WARN]${NC}"; ERR="${RED}[ERROR]${NC}"; OK="${GREEN}[OK]${NC}"

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
DEFAULT_ROOT=$( cd -- "$SCRIPT_DIR/../../.." &> /dev/null && pwd )   # repo root

# --- Defaults / argument parsing ---------------------------------------------
MESH="x1.40962"
GEOG="mpas"
OPTIONAL=""
DEST="$DEFAULT_ROOT"
EXTRACT=1

while [ $# -gt 0 ]; do
    case "$1" in
        --mesh)       MESH="$2"; shift 2 ;;
        --geog)       GEOG="$2"; shift 2 ;;
        --optional)   OPTIONAL="$2"; shift 2 ;;
        --dest)       DEST="$2"; shift 2 ;;
        --no-extract) EXTRACT=0; shift ;;
        -h|--help)    grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo -e "${ERR} Unknown argument: $1"; exit 2 ;;
    esac
done

MESH_BASE="https://www2.mmm.ucar.edu/projects/mpas/atmosphere_meshes"
MPAS_BASE="https://www2.mmm.ucar.edu/projects/mpas"
GEOG_BASE="https://www2.mmm.ucar.edu/wrf/src/wps_files"
DL_DIR="$DEST/met_data"       # tarball download cache
GEOG_DIR="$DEST/met_data/WPS_GEOG"   # extraction target == config_geog_data_path

case "$GEOG" in
    mpas) GEOG_FILE="mpas_static.tar.bz2";            GEOG_URL="$MPAS_BASE/mpas_static.tar.bz2" ;;
    high) GEOG_FILE="geog_high_res_mandatory.tar.gz"; GEOG_URL="$GEOG_BASE/geog_high_res_mandatory.tar.gz" ;;
    low)  GEOG_FILE="geog_low_res_mandatory.tar.gz";  GEOG_URL="$GEOG_BASE/geog_low_res_mandatory.tar.gz" ;;
    none) GEOG_FILE=""; GEOG_URL="" ;;
    *) echo -e "${ERR} --geog must be mpas, high, low, or none"; exit 2 ;;
esac

# expand --optional all
if [ "$OPTIONAL" = "all" ]; then OPTIONAL="ugwp,15s,bnu"; fi

if [ "$MESH" = "none" ] && [ -z "$GEOG_FILE" ] && [ -z "$OPTIONAL" ]; then
    echo -e "${ERR} Nothing to do: --mesh none, --geog none, no --optional."
    exit 2
fi

# --- Helpers ------------------------------------------------------------------
# integrity test by archive type (gzip or bzip2); plain files (.nc) pass through.
verify_archive() {
    case "$1" in
        *.bz2) bzip2 -t "$1" 2>/dev/null ;;
        *.gz)  gzip  -t "$1" 2>/dev/null ;;
        *)     [ -s "$1" ] ;;
    esac
}

# fetch URL -> dest file (idempotent + integrity-checked). Returns non-zero on failure.
fetch() {
    local url="$1" dest="$2" name; name="$(basename "$dest")"
    if [ -f "$dest" ] && verify_archive "$dest"; then
        echo -e "${OK} ${name} already present and valid — skipping"
        return 0
    fi
    echo -e "${INFO} Downloading ${name}"
    if ! curl -fL -C - --retry 3 --retry-delay 5 -o "$dest" "$url"; then
        echo -e "${ERR} Download failed: ${url}"; rm -f "$dest"; return 1
    fi
    if ! verify_archive "$dest"; then
        echo -e "${ERR} Integrity check failed (corrupt/truncated): ${name}"; rm -f "$dest"; return 1
    fi
    echo -e "${OK} ${name}"
}

# extract an archive into WPS_GEOG, stripping a single leading directory if the
# archive has exactly one top-level component (mpas_static/, WPS_GEOG/, ...).
# Idempotent via a per-archive marker file. Returns non-zero on failure.
extract_into_geog() {
    local tar="$1" name; name="$(basename "$tar")"
    local marker="$GEOG_DIR/.extracted_${name}"
    mkdir -p "$GEOG_DIR"
    if [ -f "$marker" ]; then
        echo -e "${OK} ${name} already extracted into WPS_GEOG — skipping"
        return 0
    fi
    local tops n
    tops=$(tar tf "$tar" 2>/dev/null | sed 's#^\./##; /^$/d' | cut -d/ -f1 | sort -u | grep -c .)
    n="$tops"
    echo -e "${INFO} Extracting ${name} into WPS_GEOG (this takes a while)"
    if [ "$n" -eq 1 ]; then
        tar xf "$tar" --strip-components=1 -C "$GEOG_DIR" || return 1
    else
        tar xf "$tar" -C "$GEOG_DIR" || return 1
    fi
    touch "$marker"
    echo -e "${OK} extracted ${name} -> WPS_GEOG/"
}

record_sha() { ( cd "$1" && sha256sum "$2" 2>/dev/null >> SHA256SUMS && sort -u -o SHA256SUMS SHA256SUMS ); }

failures=0

# --- Mesh ---------------------------------------------------------------------
if [ "$MESH" != "none" ]; then
    MESH_DIR="$DEST/grids"
    mkdir -p "$MESH_DIR"
    echo -e "${INFO} Mesh '${MESH}' -> ${MESH_DIR}"
    mesh_tar="$MESH_DIR/${MESH}.tar.gz"
    if fetch "${MESH_BASE}/${MESH}.tar.gz" "$mesh_tar"; then
        if [ "$EXTRACT" -eq 1 ]; then
            if [ -f "$MESH_DIR/${MESH}.grid.nc" ]; then
                echo -e "${OK} ${MESH}.grid.nc already extracted"
            else
                echo -e "${INFO} Extracting ${MESH}.tar.gz"
                tar xzf "$mesh_tar" -C "$MESH_DIR" && echo -e "${OK} extracted ${MESH} (grid.nc + graph.info[.part.N])" || { echo -e "${ERR} Failed to extract ${MESH}.tar.gz"; failures=$((failures+1)); }
            fi
        fi
        record_sha "$MESH_DIR" "${MESH}.tar.gz"
    else
        failures=$((failures+1))
    fi
else
    echo -e "${INFO} Skipping mesh download (--mesh none)"
fi

# --- geog (default bundle) ----------------------------------------------------
if [ -n "$GEOG_FILE" ]; then
    mkdir -p "$DL_DIR"
    echo -e "${INFO} geog (${GEOG}) -> extract into ${GEOG_DIR}  (large: ~2.2 GB mpas / ~2.6 GB high)"
    geog_tar="$DL_DIR/${GEOG_FILE}"
    if fetch "${GEOG_URL}" "$geog_tar"; then
        [ "$EXTRACT" -eq 1 ] && { extract_into_geog "$geog_tar" || failures=$((failures+1)); }
        record_sha "$DL_DIR" "$GEOG_FILE"
    else
        failures=$((failures+1))
    fi
fi

# --- optional add-ons ---------------------------------------------------------
if [ -n "$OPTIONAL" ]; then
    mkdir -p "$DL_DIR"
    IFS=',' read -ra OPTS <<< "$OPTIONAL"
    for opt in "${OPTS[@]}"; do
        case "$opt" in
            ugwp)
                # terrain stats (geog) + non-grid GW flux file (a run-dir input)
                for f in topo_ugwp.tar.gz; do
                    if fetch "$MPAS_BASE/$f" "$DL_DIR/$f"; then
                        [ "$EXTRACT" -eq 1 ] && { extract_into_geog "$DL_DIR/$f" || failures=$((failures+1)); }
                        record_sha "$DL_DIR" "$f"
                    else failures=$((failures+1)); fi
                done
                if fetch "$MPAS_BASE/ugwp_limb_tau.nc" "$DL_DIR/ugwp_limb_tau.nc"; then
                    record_sha "$DL_DIR" "ugwp_limb_tau.nc"
                    echo -e "${INFO} ugwp_limb_tau.nc is a RUN-DIR input (ugwp_ngw stream), not a geog dataset: copy it into the atmosphere run dir. Kept in ${DL_DIR}."
                else failures=$((failures+1)); fi
                ;;
            15s)
                f="modis_landuse_20class_15s.tar.bz2"
                if fetch "$MPAS_BASE/$f" "$DL_DIR/$f"; then
                    [ "$EXTRACT" -eq 1 ] && { extract_into_geog "$DL_DIR/$f" || failures=$((failures+1)); }
                    record_sha "$DL_DIR" "$f"
                else failures=$((failures+1)); fi
                ;;
            bnu)
                f="bnu_soiltype_top.tar.bz2"
                if fetch "$MPAS_BASE/$f" "$DL_DIR/$f"; then
                    [ "$EXTRACT" -eq 1 ] && { extract_into_geog "$DL_DIR/$f" || failures=$((failures+1)); }
                    record_sha "$DL_DIR" "$f"
                else failures=$((failures+1)); fi
                ;;
            *) echo -e "${WARN} unknown --optional item '${opt}' (expected ugwp,15s,bnu) — skipping" ;;
        esac
    done
fi

echo ""
if [ "$failures" -eq 0 ]; then
    [ "$MESH" != "none" ]                      && echo -e "${OK} Mesh in ${DEST}/grids"
    { [ -n "$GEOG_FILE" ] || [ -n "$OPTIONAL" ]; } && echo -e "${OK} geog datasets in ${GEOG_DIR}"
    [ -n "$GEOG_FILE" ] && [ "$EXTRACT" -eq 1 ] && \
        echo -e "${INFO} Set config_geog_data_path = '${GEOG_DIR}/' in namelist.init_atmosphere"
    echo -e "${INFO} Next: see usp-utils/pre_proc/static_fields/STATIC_FIELDS_GUIDE.md to run init_atmosphere (case 7)."
    exit 0
else
    echo -e "${ERR} ${failures} step(s) failed — see messages above."
    exit 1
fi
