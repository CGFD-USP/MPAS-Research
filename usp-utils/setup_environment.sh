#get directory where the sourced script is located
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INFO="${CYAN}[INFO]${NC}"
WARNING="${YELLOW}[WARNING]${NC}"

export MPAS_ROOT=$( cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd )
echo -e "${INFO} New environment variable set: MPAS_ROOT=$MPAS_ROOT"

if [ ! -d "$MPAS_ROOT/runs" ]; then
    mkdir "$MPAS_ROOT/runs"
    echo -e "${INFO} Created runs directory at $MPAS_ROOT/runs"
fi

if [ ! -d "$MPAS_ROOT/grids" ]; then
    mkdir "$MPAS_ROOT/grids"
    echo -e "${INFO} Created grids directory at $MPAS_ROOT/grids"
fi

if [ ! -d "$MPAS_ROOT/met_data" ]; then
    mkdir "$MPAS_ROOT/met_data"
    echo -e "${INFO} Created meterological data directory at $MPAS_ROOT/met_data"
fi

export PYTHONPATH="$SCRIPT_DIR/libs/py:$PYTHONPATH"
echo -e "${INFO} New environment variable set: PYTHONPATH=$PYTHONPATH"

if ! command -v conda &> /dev/null; then
    echo -e "${WARNING} Couldn't find 'conda', the 'cgfd-usp-mpas' conda environment will not be activated. Python scripts might not work."
    return 1
fi

# 'conda activate' needs the 'conda' shell function; load it if only the binary
# is on PATH (e.g. in a shell where 'conda init' hasn't run).
if ! type conda 2> /dev/null | grep -q 'function'; then
    __conda_sh="$(conda info --base 2> /dev/null)/etc/profile.d/conda.sh"
    [ -f "$__conda_sh" ] && source "$__conda_sh"
fi

# Activate only if the env exists, then confirm from CONDA_DEFAULT_ENV rather than
# from 'activate's exit code (which can be non-zero even on a successful activation).
if conda env list 2> /dev/null | awk '{print $1}' | grep -qx 'cgfd-usp-mpas'; then
    conda activate cgfd-usp-mpas
    if [ "$CONDA_DEFAULT_ENV" = "cgfd-usp-mpas" ]; then
        echo -e "${INFO} Conda environment 'cgfd-usp-mpas' activated"
    else
        echo -e "${WARNING} Found the 'cgfd-usp-mpas' environment but 'conda activate' did not take effect (is conda initialised in this shell?). Python scripts might not work."
        return 1
    fi
else
    echo -e "${WARNING} The 'cgfd-usp-mpas' conda environment was not found. It will not be activated and Python scripts might not work. To install it, run: bash $SCRIPT_DIR/install/install_conda_environment.sh"
    return 1
fi
