# Author: Guilherme L. Torres Mendonça
# 15/03/2024

These are template scripts designed to automate the whole process of running a simulation with MPAS-A. The scripts can be run independently or automatically in sequence (for instance for sensitivity tests), and are enumerated following the needed steps to run a simulation, starting from the mesh generation. Scripts whose names do not start with a number are only auxiliary.

Technically, to run a simulation with these scripts, one just needs to:
1) Create a separate directory that will contain all simulation data;
2) Copy these scripts to the created directory;
3) Edit the input_file.txt, entering in the format indicated there all input information needed for running the simulation
4) Run the enumerated scripts in the appropriate order.

Remark: The needed conda environments to run the scripts can be installed by running 0_create_envs.sh.
