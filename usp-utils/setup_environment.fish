#get directory where the sourced script is located
set SCRIPT_DIR (dirname (realpath (status current-filename)))

set CYAN '\033[0;36m'
set YELLOW '\033[1;33m'
set NC '\033[0m' # No Color

set INFO "$CYAN""[INFO]""$NC"
set WARNING "$YELLOW""[WARNING]""$NC"

set -x MPAS_ROOT (dirname (realpath "$SCRIPT_DIR../"))
echo -e "$INFO New enviroment variable set: MPAS_ROOT=$MPAS_ROOT"

if [ ! -d "$MPAS_ROOT/runs" ]
    mkdir "$MPAS_ROOT/runs"
    echo -e "$INFO Created runs directory at $MPAS_ROOT/runs"
end

if [ ! -d "$MPAS_ROOT/grids" ]
    mkdir "$MPAS_ROOT/grids"
    echo -e "$INFO Created grids directory at $MPAS_ROOT/grids"
end

if [ ! -d "$MPAS_ROOT/met_data" ]
    mkdir "$MPAS_ROOT/met_data"
    echo -e "$INFO Created meterological data directory at $MPAS_ROOT/met_data"
end

set -x PYTHONPATH "$SCRIPT_DIR/libs/py:$PYTHONPATH"
echo -e "$INFO New enviroment variable set: PYTHONPATH=$PYTHONPATH"

conda &> /dev/null
if [ ! $status ]
    echo -e "$WARNING Couldn't find 'conda' binary, 'cgfd-usp-mpas' conda environment will not be activated. Python scripts might not work."
    return 1
end

set N (conda info --envs | grep '^cgfd-usp-mpas ' | wc -l)
if [ $N = 0 ]
    echo -e "$WARNING Couldn't find the 'cgfd-usp-mpas' conda environment. It will not be activated and Python scripts might not work. If you wish to install the conda environment please run the script in $SCRIPT_DIR/install_conda_environment.sh"
    return 1
end

conda activate cgfd-usp-mpas
echo -e "$INFO Conda enviroment 'cgfd-usp-mpas' activated"
