#!/usr/bin/env python
"""Tropically refined spherical MPAS grid made with JIGSAW and MPAS-Tools.

The cell width depends on latitude only and follows the density blend used by the NCAR
60-15 km tropical mesh (x4.1572866). The fine resolution holds in the tropics, the coarse
one (RATIO times larger) at high latitudes, and a tanh transition of fixed angular position
and width joins them. Meshes of different fine resolution r are therefore the same design
scaled in cell size, which makes them a convergence sequence.

  cell width h(lat) = (r^-4 + (RATIO^-4 - 1) r^-4 s(lat))^(-1/4),
  s(lat) = (1 + tanh((|lat| - LAT0) / WIDTH)) / 2

Usage (in the MPAS image, see usp-utils/install/container/run.sh):
  python create_tropical_refined_grid.py -r 15              60-15 km mesh
  python create_tropical_refined_grid.py -r 7.5 -o <dir>    30-7.5 km mesh into <dir>/<name>/

With --band-ref the transition width scales with the fine spacing instead (the same number of
cells across the band at every level), and the mesh is named tropical-fixcells-<coarse>-<fine>km.

With --start continuation JIGSAW starts from the defect-free icosahedral lattice with the cell count of the design and
optimises it through a sequence of cell width functions, from uniform to the design, each started from the previous mesh.

With --start mapped JIGSAW optimises that lattice with its latitudes moved to follow the design.

With --start coarsen JIGSAW optimises the cell centres of the --source mesh after --levels decimations that double the
spacing (the design must be the one of the coarser mesh).

With --start rings, icos or geo JIGSAW does not mesh from scratch but optimises a given almost regular point set
(tropical_start_set.py) and its Delaunay triangulation, which keeps the hexagonal connectivity of the set.
The defaults then are mesh_iter 0, merge and split of cells allowed, the CVT kernel (override with --mesh-iter and --jig),
and the mesh name gets the suffix -rings, -icos or -geo.

The mesh is written to <out>/<name>/<name>.nc (unit sphere, as MPAS-Tools writes it) with
<name>.graph.info, <name>.log.json (settings, times, peak memory) and, unless --nocheck,
<name>.quality.json and <name>.quality.npz from check_mesh_quality.py.
"""
import argparse
import ast
import glob
import json
import os
import resource
import shutil
import subprocess
import sys
import time

import numpy as np

EARTH_RADIUS_KM = 6371.229
RATIO = 4.0
# position and width (degrees) of the tanh blend fitted to the NCAR 60-15 km mesh
LAT0, WIDTH = 32.6, 4.8
# the lat-lon grid of the cell width function is this many times finer than the fine cell width
GRID_REFINE = 10


def cell_width(lat, fine, ratio=RATIO, width=WIDTH):
    """Cell width (km) at latitudes lat (degrees) for fine cell width `fine` (km)."""
    s = 0.5 * (1.0 + np.tanh((np.abs(lat) - LAT0) / width))
    return (fine ** -4 + ((ratio * fine) ** -4 - fine ** -4) * s) ** -0.25


def cell_width_grid(fine, ratio=RATIO, width=WIDTH):
    """Cell width on a lat-lon grid fine enough to resolve fine/GRID_REFINE, as JIGSAW reads it."""
    km_per_deg = np.radians(1.0) * EARTH_RADIUS_KM
    nlat = int(np.ceil(180.0 * km_per_deg * GRID_REFINE / fine)) + 1
    lat = np.linspace(-90.0, 90.0, nlat)
    lon = np.linspace(-180.0, 180.0, 73)
    return np.tile(cell_width(lat, fine, ratio, width)[:, None], (1, lon.size)), lon, lat


def transition_width(fine, band_ref=None):
    """Width (degrees) of the transition. With band_ref (a fine spacing) it scales with the fine
    spacing, so the band holds the same number of cells at every level."""
    return WIDTH if band_ref is None else WIDTH * fine / band_ref


def mesh_name(fine, ratio=RATIO, band_ref=None):
    return "tropical-%s%g-%gkm" % ("" if band_ref is None else "fixcells-", ratio * fine, fine)


def continuation_params(steps, power):
    """Parameters t_k, k = 1..steps, of the continuation from the uniform mesh (t = 0) to the design (t = 1).
    power > 1 makes the steps smaller towards the end."""
    return [1.0 - (1.0 - k / steps) ** power for k in range(1, steps + 1)]


def write_hfun(jig, path, width_of_lat, fine, ratio, width):
    _, lon, lat = cell_width_grid(fine, ratio, width)
    cw = np.tile(width_of_lat(lat)[:, None], (1, lon.size))
    hmat = jig.jigsaw_msh_t()
    hmat.mshID = "ELLIPSOID-GRID"
    hmat.xgrid, hmat.ygrid, hmat.value = np.radians(lon), np.radians(lat), cw
    jig.savemsh(path, hmat)


def count_cells(jig, mesh_file):
    mesh = jig.jigsaw_msh_t()
    jig.loadmsh(mesh_file, mesh)
    return int(mesh.vert3.size)


def run_jigsaw(base, fine, ratio, width, args):
    import jigsawpy as jig
    opts = jig.jigsaw_jig_t()
    opts.geom_file, opts.jcfg_file = base + ".msh", base + ".jig"
    opts.mesh_file, opts.hfun_file = base + "-MESH.msh", base + "-HFUN.msh"
    design = lambda lat: cell_width(lat, fine, ratio, width)
    source_design = None if args.source_width is None else \
        (lambda lat: cell_width(lat, fine / 2 ** args.levels, ratio, args.source_width))
    geom = jig.jigsaw_msh_t()
    geom.mshID = "ELLIPSOID-MESH"
    geom.radii = EARTH_RADIUS_KM * np.ones(3, float)
    jig.savemsh(opts.geom_file, geom)
    opts.hfun_scal, opts.hfun_hmax, opts.hfun_hmin = "absolute", float("inf"), 0.0
    opts.mesh_dims = +2
    opts.mesh_iter = args.mesh_iter
    if args.start != "frontal":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tropical_start_set
        opts.init_file = base + "-INIT.msh"
        jig.savemsh(opts.init_file, tropical_start_set.start_mesh(args.start, design, EARTH_RADIUS_KM, args.source, args.levels, args.direction, source_design))
        opts.optm_kern, opts.optm_zip_, opts.optm_div_ = "cvt+dqdx", True, True
    opts.optm_iter, opts.optm_qlim, opts.optm_qtol = args.optm_iter, args.qlim, args.qtol
    opts.numthread = args.threads
    for key, value in args.jig:
        setattr(opts, key, value)
    opts.verbosity = +1
    steps_log = []
    if args.start == "continuation":
        steps = continuation_params(args.steps, args.power)
        # passes (t, exponent of the cell width, merge and split)
        plan = [(t, 1.0, True) for t in steps] if not args.pre_power else \
            [(t, args.pre_power, False) for t in steps] + [(1.0, 1.0, True)]
    else:
        plan = [(1.0, 1.0, True)]
    for k, (t, expo, remesh) in enumerate(plan):
        t0 = time.time()
        width_t = design if args.start != "continuation" else tropical_start_set.blend_width(design, EARTH_RADIUS_KM, t, expo)
        write_hfun(jig, opts.hfun_file, width_t, fine, ratio, width)
        if args.start == "continuation":
            opts.optm_zip_ = opts.optm_div_ = remesh
        jig.savejig(opts.jcfg_file, opts)
        subprocess.check_call(["jigsaw", opts.jcfg_file])
        if len(plan) > 1:
            steps_log.append({"t": round(t, 6), "power": expo, "remesh": remesh, "s": round(time.time() - t0, 1),
                              "cells": count_cells(jig, opts.mesh_file)})
            print("pass %d/%d %s" % (k + 1, len(plan), steps_log[-1]), flush=True)
            if k + 1 < len(plan):
                shutil.copy(opts.mesh_file, opts.init_file)
    return opts.mesh_file, steps_log


def convert_to_mpas(mesh_file, out_dir, base, cell_width_lonlat):
    """MPAS grid file of a JIGSAW mesh, with meshDensity = (min width / width)^4 of the design (cell_width_lonlat =
    cellWidth, lon, lat), which MPAS uses to scale the horizontal mixing."""
    import xarray
    from mpas_tools.io import write_netcdf
    from mpas_tools.mesh.conversion import convert
    from mpas_tools.mesh.creation.jigsaw_to_netcdf import jigsaw_to_netcdf
    from mpas_tools.ocean.inject_meshDensity import inject_spherical_meshDensity
    jigsaw_to_netcdf(msh_filename=mesh_file, output_name=base + "_triangles.nc", on_sphere=True,
                     sphere_radius=1.0)
    mesh = convert(xarray.open_dataset(base + "_triangles.nc"), dir=out_dir,
                   graphInfoFileName=base + ".graph.info")
    write_netcdf(mesh, base + ".nc")
    inject_spherical_meshDensity(*cell_width_lonlat, base + ".nc")


def peak_gb():
    kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return max(kb, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 2 ** 20


def jigsaw_option(text):
    """key=value, with the value as a Python literal when it is one (True, 1e-8) and a string otherwise."""
    key, value = text.split("=", 1)
    try:
        value = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        pass
    return key, value


def main(args):
    fine = args.fine
    width = transition_width(fine, args.band_ref)
    name = args.name or mesh_name(fine, args.ratio, args.band_ref) + ("" if args.start == "frontal" else "-" + args.start)
    out_dir = os.path.join(args.out, name)
    base = os.path.join(out_dir, name)
    os.makedirs(out_dir, exist_ok=True)
    log = {"name": name, "fine_km": fine, "coarse_km": fine * args.ratio, "ratio": args.ratio,
           "lat0_deg": LAT0, "width_deg": width, "band_ref_km": args.band_ref, "radius_km": EARTH_RADIUS_KM,
           "start": args.start, "jigsaw": {"mesh_iter": args.mesh_iter, "optm_iter": args.optm_iter, "optm_qlim": args.qlim,
                      "optm_qtol": args.qtol, "numthread": args.threads, **dict(args.jig)}}
    t0 = time.time()
    mesh_file, log["steps"] = run_jigsaw(base, fine, args.ratio, width, args)
    log["jigsaw_s"], log["jigsaw_peak_gb"] = round(time.time() - t0, 1), round(peak_gb(), 2)
    t1 = time.time()
    convert_to_mpas(mesh_file, out_dir, base, cell_width_grid(fine, args.ratio, width))
    log["convert_s"], log["peak_gb"] = round(time.time() - t1, 1), round(peak_gb(), 2)
    for ext in (".msh", ".jig", "-MESH.msh", "-HFUN.msh", "_triangles.nc", "-INIT.msh"):
        if os.path.exists(base + ext):
            os.remove(base + ext)
    for d in glob.glob(os.path.join(out_dir, "*/")):
        shutil.rmtree(d)
    log["total_s"] = round(time.time() - t0, 1)
    log["size_bytes"] = os.path.getsize(base + ".nc")
    with open(base + ".log.json", "w") as f:
        json.dump(log, f, indent=1)
    print("mesh %s written, %.0f s, peak %.1f GB" % (base + ".nc", log["total_s"], log["peak_gb"]))
    if not args.nocheck:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import check_mesh_quality as chk
        chk.check(base + ".nc", fine, args.ratio, base + ".quality", width)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-r", "--fine", type=float, required=True, help="fine cell width in the tropics (km)")
    p.add_argument("--ratio", type=float, default=RATIO, help="coarse over fine cell width (default %g)" % RATIO)
    p.add_argument("-o", "--out", default=os.path.join(os.environ.get("MPAS_ROOT", "."), "meshes", "tropical-ref"),
                   help="folder holding the mesh folder (default $MPAS_ROOT/meshes/tropical-ref)")
    p.add_argument("--band-ref", dest="band_ref", type=float,
                   help="fine spacing (km) at which the transition width is WIDTH, and the width scales with the "
                        "fine spacing (fixed number of cells across the transition). Default: fixed width")
    p.add_argument("--name", help="mesh name (default tropical-<coarse>-<fine>km)")
    p.add_argument("--optm-iter", dest="optm_iter", type=int, default=5000000,
                   help="maximum JIGSAW optimisation iterations")
    p.add_argument("--start", choices=("frontal", "rings", "icos", "geo", "continuation", "mapped", "coarsen"), default="frontal",
                   help="frontal: JIGSAW meshes from scratch. rings, icos or geo: JIGSAW optimises an almost regular "
                        "point set (reduced latitude-longitude rings, bisected icosahedron points kept by the density, "
                        "or icosahedral lattices of stepped frequency. continuation: the icosahedral lattice of the "
                        "design's cell count, optimised through --steps cell widths from uniform to the design)")
    p.add_argument("--source", help="--start coarsen: MPAS grid file whose cell centres are decimated")
    p.add_argument("--direction", type=float, nargs=3, default=(1.0, 0.0, 0.0), metavar=("X", "Y", "Z"),
                   help="--start coarsen: the decimation starts at the cell closest to this direction (default 1 0 0)")
    p.add_argument("--source-width", dest="source_width", type=float,
                   help="--start coarsen: transition width (degrees) of the source mesh. The decimated points are moved in "
                        "latitude to the cell fraction of this mesh's design")
    p.add_argument("--levels", type=int, default=1, help="--start coarsen: number of decimations, each doubling the spacing")
    p.add_argument("--pre-power", dest="pre_power", type=float, default=0.0,
                   help="--start continuation: first run the steps with merge and split off and the cell width raised to this "
                        "power (4 makes the CVT kernel realise the design), then one pass with the design (default 0: off)")
    p.add_argument("--steps", type=int, default=10, help="--start continuation: number of density steps (default 10)")
    p.add_argument("--power", type=float, default=1.0,
                   help="--start continuation: step k has t = 1 - (1 - k/steps)^power, so power > 1 ends with small steps")
    p.add_argument("--mesh-iter", dest="mesh_iter", type=int,
                   help="maximum JIGSAW meshing iterations (default 5000000, 0 with another --start)")
    p.add_argument("--qlim", type=float, default=0.9375, help="JIGSAW optm_qlim, quality threshold")
    p.add_argument("--qtol", type=float, default=1.0e-3, help="JIGSAW optm_qtol, quality tolerance")
    p.add_argument("--threads", type=int, default=8, help="JIGSAW threads")
    p.add_argument("--jig", type=jigsaw_option, action="append", default=[], metavar="KEY=VALUE",
                   help="any other JIGSAW option, e.g. --jig optm_dual=True --jig optm_kern=cvt+odt")
    p.add_argument("--nocheck", action="store_true", help="skip check_mesh_quality")
    args = p.parse_args()
    if args.mesh_iter is None:
        args.mesh_iter = 5000000 if args.start == "frontal" else 0
    main(args)
