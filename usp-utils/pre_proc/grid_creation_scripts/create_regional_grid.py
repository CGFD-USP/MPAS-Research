#!/usr/bin/env python
#
#  Create a regional (limited-area) mesh for MPAS-Atmosphere.
#
#  A regional MPAS mesh is made in two steps:
#     1. build a GLOBAL, locally-refined mesh (fine over the area of interest,
#        coarse everywhere else) -- reuses jigsaw_util.build_global_mesh
#     2. CUT the area of interest out of that global mesh with the NCAR
#        MPAS-Limited-Area tool (`create_region`) -- via regional_util
#
#  Smart-transition default
#  ------------------------
#  Generating meshes is expensive, so the global background is coarse by
#  default (200 km). The high-resolution flat zone is sized to fully contain
#  the area of interest (plus a small buffer), so EVERY cell kept inside the
#  region ends up at the requested spacing, while the (coarser) transition belt
#  falls OUTSIDE the region and is discarded by the cut -- minimising the number
#  of grid points that are generated but not used.
#
#  by Claude (USP MPAS-Research) 2026, building on create_spherical_grid.py
#

import argparse
import os
import sys

import jigsaw_util as jutil
import regional_util as rutil

# MPAS-Limited-Area keeps a 7-cell relaxation belt OUTSIDE the region boundary.
# To keep that belt at full resolution too, the flat high-res zone must extend
# past the area of interest by ~ this many cells (7 layers + a small margin).
DEFAULT_BUFFER_CELLS = 10


def main(args):

    mpas_root = os.getenv('MPAS_ROOT')
    if not mpas_root:
        print("ERROR: environment variable MPAS_ROOT is not set.")
        print("Source the usp-utils environment first "
              "(see usp-utils/setup_environment.sh).")
        sys.exit(1)

    out_dir = mpas_root + "/grids/" + args.output
    out_base = os.path.basename(args.output)
    global_base = out_dir + "/" + out_base + "_global"
    global_mesh = global_base + ".nc"
    region_spec = out_dir + "/" + out_base + ".pts"
    p = bool(args.plots)

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    else:
        print("Base dir already exists: ", out_dir)

    # ------------------------------------------------------------------
    # 1) Work out the geometry of the region and the high-resolution zone
    # ------------------------------------------------------------------
    boundary_points = None
    if args.shape == "circle":
        if args.region_radius is None or args.clat is None or args.clon is None:
            print("ERROR: --shape circle needs -clat, -clon and "
                  "--region-radius.")
            sys.exit(1)
        clat, clon = args.clat, args.clon
        # radius of the area of interest (what gets kept by the cut)
        area_radius = args.region_radius

    elif args.shape == "ellipse":
        if None in (args.clat, args.clon, args.semi_major, args.semi_minor):
            print("ERROR: --shape ellipse needs -clat, -clon, --semi-major "
                  "and --semi-minor.")
            sys.exit(1)
        clat, clon = args.clat, args.clon
        # the flat high-res zone must cover the longest axis
        area_radius = max(args.semi_major, args.semi_minor)

    elif args.shape == "box":
        if None in (args.lat_min, args.lat_max, args.lon_min, args.lon_max):
            print("ERROR: --shape box needs --lat-min --lat-max "
                  "--lon-min --lon-max.")
            sys.exit(1)
        clat, clon = rutil.box_center(args.lat_min, args.lat_max,
                                      args.lon_min, args.lon_max)
        # circle that contains the whole box -> sizes the high-res flat zone
        area_radius = rutil.box_circumscribed_radius_km(
            args.lat_min, args.lat_max, args.lon_min, args.lon_max)
        boundary_points = rutil.box_boundary_points(
            args.lat_min, args.lat_max, args.lon_min, args.lon_max)

    elif args.shape == "polygon":
        if not args.polygon_file:
            print("ERROR: --shape polygon needs --polygon-file FILE.")
            sys.exit(1)
        boundary_points = rutil.read_polygon_file(args.polygon_file)
        # use a user-given inside point, else the polygon centroid
        if args.clat is not None and args.clon is not None:
            clat, clon = args.clat, args.clon
        else:
            clat, clon = rutil.polygon_center(boundary_points)
        area_radius = rutil.max_radius_km(clat, clon, boundary_points)

    else:
        print("Unknown shape:", args.shape)
        sys.exit(1)

    # Flat high-resolution zone: large enough to cover the whole area of
    # interest PLUS the MPAS relaxation belt, so every kept cell (interior and
    # relaxation) is at the target spacing and the transition belt (discarded by
    # the cut) starts only beyond it.
    if args.buffer is not None:
        buffer = args.buffer
    else:
        buffer = DEFAULT_BUFFER_CELLS * args.r
    radius_high = area_radius + buffer

    print("Region centre (lat, lon): %.3f, %.3f" % (clat, clon))
    print("Area of interest radius : %.1f km" % area_radius)
    print("High-res flat zone radius: %.1f km (area + %.1f km buffer)"
          % (radius_high, buffer))
    print("Background (global) spacing: %.1f km" % args.l)
    print("Target spacing inside region: %.1f km" % args.r)

    # ------------------------------------------------------------------
    # 2) Build the global, locally-refined mesh
    # ------------------------------------------------------------------
    print("\n[1/3] Building global locally-refined mesh ...")
    jutil.build_global_mesh(
        "localref", global_base, out_dir, global_mesh,
        r=args.r, l=args.l, rad=radius_high, tr=args.tr,
        clon=clon, clat=clat, plots=False)

    # ------------------------------------------------------------------
    # 3) Write the region spec and cut the regional mesh out
    # ------------------------------------------------------------------
    print("\n[2/3] Writing region specification -> %s" % region_spec)
    if args.shape == "circle":
        rutil.write_region_spec(region_spec, out_base, "circle",
                                clat=clat, clon=clon,
                                region_radius_km=area_radius)
    elif args.shape == "ellipse":
        rutil.write_region_spec(region_spec, out_base, "ellipse",
                                clat=clat, clon=clon,
                                semi_major_km=args.semi_major,
                                semi_minor_km=args.semi_minor,
                                orientation_deg=args.orientation)
    else:  # box / polygon -> custom polygon
        rutil.write_region_spec(region_spec, out_base, "custom",
                                clat=clat, clon=clon,
                                boundary_points=boundary_points)

    print("\n[3/3] Cutting regional mesh with MPAS-Limited-Area ...")
    rutil.cut_regional_mesh(global_mesh, region_spec, out_dir)

    regional_mesh = "%s/%s.grid.nc" % (out_dir, out_base)

    # Optional quick-look plot of the resulting regional mesh resolution.
    # By default it goes next to the grid; --plot-out overrides the location.
    plot_png = None
    if p or args.plot_out:
        plot_png = jutil.resolve_plot_path(args.plot_out, out_dir, out_base)
        print("\nPlotting resolution -> %s" % plot_png)
        jutil.plot_resolution(regional_mesh, plot_png, states=True)

    print("\nDone! Regional mesh written under: " + out_dir)
    print("  global (pre-cut) mesh : %s" % global_mesh)
    print("  region spec           : %s" % region_spec)
    print("  regional mesh         : %s" % regional_mesh)
    print("  partition graph       : %s/%s.graph.info" % (out_dir, out_base))
    if plot_png:
        print("  resolution plot       : %s" % plot_png)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument(
        "-r", "--high", dest="r",
        required=False, default=30, type=float,
        help="Target grid spacing INSIDE the region, in km (default: 30 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-l", "--low", dest="l",
        required=False, default=200, type=float,
        help="Background (global) grid spacing in km. Kept coarse on purpose "
             "since\nit is discarded by the cut (default: 200 km)",
        metavar="FLOAT")

    parser.add_argument(
        "--shape", dest="shape",
        required=False, default="circle", type=str,
        help="Region shape (default: circle):\n"
             "  circle  -> -clat -clon --region-radius\n"
             "  ellipse -> -clat -clon --semi-major --semi-minor "
             "[--orientation]\n"
             "  box     -> --lat-min --lat-max --lon-min --lon-max\n"
             "  polygon -> --polygon-file [-clat -clon as inside point]",
        metavar="STR")

    parser.add_argument(
        "-clat", "--center_latitude", dest="clat",
        required=False, default=None, type=float,
        help="Latitude (deg) of the region centre - circle/ellipse "
             "(or inside point for polygon)",
        metavar="FLOAT")

    parser.add_argument(
        "-clon", "--center_longitude", dest="clon",
        required=False, default=None, type=float,
        help="Longitude (deg) of the region centre - circle/ellipse "
             "(or inside point for polygon)",
        metavar="FLOAT")

    parser.add_argument(
        "--region-radius", dest="region_radius",
        required=False, default=None, type=float,
        help="Radius of the area of interest in km - circle shape",
        metavar="FLOAT")

    parser.add_argument(
        "--semi-major", dest="semi_major",
        required=False, default=None, type=float,
        help="Ellipse semi-major axis in km - ellipse shape",
        metavar="FLOAT")
    parser.add_argument(
        "--semi-minor", dest="semi_minor",
        required=False, default=None, type=float,
        help="Ellipse semi-minor axis in km - ellipse shape",
        metavar="FLOAT")
    parser.add_argument(
        "--orientation", dest="orientation",
        required=False, default=0.0, type=float,
        help="Ellipse orientation in deg, clockwise from north - ellipse "
             "shape (default: 0)",
        metavar="FLOAT")

    parser.add_argument(
        "--polygon-file", dest="polygon_file",
        required=False, default=None, type=str,
        help="Text file with 'lat, lon' boundary points (one per line) - "
             "polygon shape",
        metavar="PATH")

    parser.add_argument(
        "--lat-min", dest="lat_min", required=False, default=None, type=float,
        help="South edge (deg) - box shape", metavar="FLOAT")
    parser.add_argument(
        "--lat-max", dest="lat_max", required=False, default=None, type=float,
        help="North edge (deg) - box shape", metavar="FLOAT")
    parser.add_argument(
        "--lon-min", dest="lon_min", required=False, default=None, type=float,
        help="West edge (deg) - box shape", metavar="FLOAT")
    parser.add_argument(
        "--lon-max", dest="lon_max", required=False, default=None, type=float,
        help="East edge (deg) - box shape", metavar="FLOAT")

    parser.add_argument(
        "--buffer", dest="buffer",
        required=False, default=None, type=float,
        help="Extra high-resolution margin (km) added around the area of\n"
             "interest, so the MPAS relaxation belt also stays at full\n"
             "resolution. Default: 10 x the high-res spacing (-r), which\n"
             "covers the 7-cell relaxation zone with a small margin.",
        metavar="FLOAT")

    parser.add_argument(
        "-tr", "--transitionradius", dest="tr",
        required=False, default=600, type=float,
        help="Transition-zone radius in km between high and low resolution.\n"
             "It lies OUTSIDE the region and is discarded, so it mainly "
             "affects\ngeneration cost (default: 600 km)",
        metavar="FLOAT")

    parser.add_argument(
        "-o", "--output", dest="output",
        required=False, default="regional_grid", type=str,
        help="Output basename for directory and files.",
        metavar="STR")

    parser.add_argument(
        "-p", "--plot", dest="plots",
        required=False, action="store_true",
        help="If given, save a quick-look PNG of the regional mesh resolution.\n"
             "By default it is written next to the grid, as\n"
             "$MPAS_ROOT/grids/<output>/<output>_resolution.png.\n"
             "No plot unless this flag is present.")

    parser.add_argument(
        "--plot-out", dest="plot_out",
        required=False, default=None, type=str,
        help="Custom path for the resolution plot (a file, or a directory in\n"
             "which <output>_resolution.png is written). Implies --plot.\n"
             "Omit to use the default location next to the grid.",
        metavar="PATH")

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    main(args)
