#!/usr/bin/env python
#
#  Basic script to creat spherical grids for MPAS-Atmosphere
#  by Pedro S. Peixoto Dec 2021 <ppeixoto@usp.br>
#  update by F.A.V.B. Alves on Sept 2025
#
#  Based on 
#  http://mpas-dev.github.io/MPAS-Tools/stable/mesh_creation.html#spherical-meshes
#  and Jigsaw scripts: https://github.com/dengwirda/jigsaw-python/tree/master/tests
 
import argparse
import os
import sys

import jigsaw_util as jutil

#import mpas_tools
#print(mpas_tools.__file__)

###TO DO:
#
# - Add a tetris case
# - Variable resolution function - set ID number for each case
# - Read mesh xyz from file and convert to mpas grid (after possible scvt optimization)
#
#

def main(args):

    mpas_root = os.getenv('MPAS_ROOT')
    if not mpas_root:
        print("ERROR: environment variable MPAS_ROOT is not set. Source usp-utils/setup_environment.sh first.")
        sys.exit(1)

    out_dir = mpas_root + "/grids/" + args.output
    out_base = os.path.basename(args.output)
    out_basepath = out_dir + "/" + out_base
    out_filename = out_dir + "/" + out_base + ".nc"
    p = bool(args.plots)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    else:
        print("Base dir already exists: ", out_dir)

    if args.opt not in ("unif", "icos", "localref"):
        print("Unknown option")
        exit(1)

    # The whole jigsaw -> NetCDF -> MPAS pipeline lives in jigsaw_util so it can
    # be shared with the regional mesh creator (create_regional_grid.py).
    jutil.build_global_mesh(
        args.opt, out_basepath, out_dir, out_filename,
        r=args.r, l=args.l, rad=args.rad, tr=args.tr,
        clon=args.clon, clat=args.clat, plots=False)

    # Optional quick-look plot of the final mesh resolution. By default it goes
    # next to the grid; --plot-out overrides the location.
    plot_png = None
    if p or args.plot_out:
        plot_png = jutil.resolve_plot_path(args.plot_out, out_dir, out_base)
        print("Plotting resolution -> %s" % plot_png)
        jutil.plot_resolution(out_filename, plot_png)

    print("Done! Mesh saved to "+out_dir)
    if plot_png:
        print("Resolution plot: "+plot_png)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument(
        "-r",  "--high", dest="r",
        required=False, default=30, type=float,
        help="Grid spacing for high resolution area - depends on the grid \
choice, see -g (default: 30 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-l", "--low", dest="l", 
        required=False, default=150, type=float,
        help="Level of refinement on icosahedral grid, or global grid spacing \
            (resolution area) for localref\
            grid option, see -g (default: 150 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-rad", "--radius", dest="rad", 
        required=False, default=50, type=float,
        help="radius of influence of high resolution area in km - only valid \
for localref grid option, see -g (default: 50 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-tr",  "--transitionradius", dest="tr",
        required=False, default=600, type=float,
        help="radius of transition zone between high and low resolution in km \
- only valid for local ref grid option, see -g (default: 600 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-clat",  "--center_latitude", dest="clat",
        required=False, default=0.0, type=float,
        help="Latitude (in degrees) of centre point of refinement \
- only valid for local ref grid option, see -g (default: 0 deg)",
        metavar="FLOAT")

    parser.add_argument(
        "-clon",  "--center_longitude", dest="clon",
        required=False, default=0.0, type=float,
        help="Longitude (in degrees) of centre point of refinement \
- only valid for local ref grid option, see -g (default: 0 deg)",
        metavar="FLOAT")

    parser.add_argument(
        "-o", "--output", dest="output",
        required=False, default="grid", type=str,
        help="output basename for directory and files.",
        metavar="STR")

    parser.add_argument(
        "-p", "--plot", dest="plots",
        required=False, action="store_true",
        help="If given, save a quick-look PNG of the final mesh resolution next \
to\nthe grid ($MPAS_ROOT/grids/<output>/<output>_resolution.png).\nNo plot \
unless this flag is present.")

    parser.add_argument(
        "--plot-out", dest="plot_out",
        required=False, default=None, type=str,
        help="Custom path for the resolution plot (a file, or a directory in \
which\n<output>_resolution.png is written). Implies --plot.",
        metavar="PATH")

    parser.add_argument(
        "-g", "--grid", dest="opt",
        required=True, default="icos", type=str,
        help="""Grid option: \n 
        "unif": Uniform resolution spherical grid (hand tune \
cellWidthVsLatLon function) \n
        "icos": Spherical icosahedral grid \n
        "localref" : Variable resolution spherical grid (hand tune \
cellWidthVsLatLon function) \n
            """,
        metavar="STR")

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    main(args)
