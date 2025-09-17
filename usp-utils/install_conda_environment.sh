#get directory where the sourced script is located
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INFO="${CYAN}[INFO]${NC}"
WARNING="${YELLOW}[WARNING]${NC}"

N=$(conda info --envs | grep '^cgfd-usp-mpas ' | wc -l)
if [ $N == 0 ]; then
    echo -e "${INFO} Creating 'cgfd-usp-mpas' conda environment"
    conda env create --name cgfd-usp-mpas --file=$SCRIPT_DIR/libs/cgfd-usp-mpas.yml
else
    echo -e "${INFO} 'cgfd-usp-mpas' conda environment already exists, updating it instead"
    conda env update --name cgfd-usp-mpas --file=$SCRIPT_DIR/libs/cgfd-usp-mpas.yml --prune
fi
