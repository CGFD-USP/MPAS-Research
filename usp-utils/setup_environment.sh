#get directory where the sourced script is located
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INFO="${CYAN}[INFO]${NC}"
WARNING="${YELLOW}[WARNING]${NC}"

export MPAS_ROOT=$( cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd )
echo -e "${INFO} New enviroment variable set: MPAS_ROOT=$MPAS_ROOT"

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
echo -e "${INFO} New enviroment variable set: PYTHONPATH=$PYTHONPATH"

conda &> /dev/null
status=$?
if [ ! $status == "0" ]; then
    echo -e "${WARNING} Couldn't find 'conda' binary, 'cgfd-usp-mpas' conda environment will not be activated. Python scripts might not work."
    return 1
fi

conda activate cgfd-usp-mpas &> /dev/null
status=$?
if [ ! $status == "0" ]; then
    echo -e "${WARNING} Couldn't find the 'cgfd-usp-mpas' conda environment. It will not be activated and Python scripts might not work. If you wish to install the conda environment please run the script in $SCRIPT_DIR/install_conda_environment.sh"
    return 1
fi

echo -e "${INFO} Conda enviroment 'cgfd-usp-mpas' activated"
