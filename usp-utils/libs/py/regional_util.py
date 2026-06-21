#!/usr/bin/env python
#
#  Helpers to turn a global MPAS mesh into a regional (limited-area) mesh.
#
#  This module does NOT re-implement the cutting algorithm. It is glue around
#  the official NCAR/MPAS-Dev tool "MPAS-Limited-Area" (the `create_region`
#  command / `limited_area` python package), in the same spirit that
#  jigsaw_util calls the external `jigsaw` binary.
#
#  Workflow for a regional mesh:
#     1. build a global, locally-refined mesh   -> jigsaw_util.build_global_mesh
#     2. write a region specification ("points file") -> write_region_spec
#     3. cut the region out of the global mesh        -> cut_regional_mesh
#

import os
import shutil
import subprocess

import numpy as np

from jigsaw_util import latlon_to_distance_center


def box_center(lat_min, lat_max, lon_min, lon_max):
    """Return the (lat, lon) centre of a lat/lon box, in degrees."""
    return 0.5 * (lat_min + lat_max), 0.5 * (lon_min + lon_max)


def box_circumscribed_radius_km(lat_min, lat_max, lon_min, lon_max):
    """
    Smallest radius (km) of a circle centred on the box centre that still
    contains all four corners. Used to size the high-resolution flat zone so
    the whole box ends up at the target spacing.
    """
    clat, clon = box_center(lat_min, lat_max, lon_min, lon_max)
    corners = [(lat_min, lon_min), (lat_min, lon_max),
               (lat_max, lon_min), (lat_max, lon_max)]
    dists = [latlon_to_distance_center(lon, lat, clon=clon, clat=clat)
             for (lat, lon) in corners]
    return float(np.max(dists))


def box_boundary_points(lat_min, lat_max, lon_min, lon_max, n_per_edge=20):
    """
    Sample points counter-clockwise along the edges of a lat/lon box.

    MPAS-Limited-Area "custom" regions are defined by a closed list of
    boundary (lat, lon) points; sampling several points per edge approximates
    the rectangle well on the sphere.
    """
    pts = []
    # bottom edge (west -> east) at lat_min
    for lon in np.linspace(lon_min, lon_max, n_per_edge, endpoint=False):
        pts.append((lat_min, lon))
    # east edge (south -> north) at lon_max
    for lat in np.linspace(lat_min, lat_max, n_per_edge, endpoint=False):
        pts.append((lat, lon_max))
    # top edge (east -> west) at lat_max
    for lon in np.linspace(lon_max, lon_min, n_per_edge, endpoint=False):
        pts.append((lat_max, lon))
    # west edge (north -> south) at lon_min
    for lat in np.linspace(lat_max, lat_min, n_per_edge, endpoint=False):
        pts.append((lat, lon_min))
    return pts


def read_polygon_file(path):
    """
    Read a custom boundary polygon from a text file.

    Each non-empty, non-comment line holds one ``lat, lon`` pair (comma or
    whitespace separated), in degrees. ``#`` starts a comment. Returns a list of
    ``(lat, lon)`` float tuples.
    """
    points = []
    with open(path) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            parts = line.replace(',', ' ').split()
            if len(parts) < 2:
                continue
            points.append((float(parts[0]), float(parts[1])))
    if len(points) < 3:
        raise ValueError("Polygon file %r needs at least 3 lat,lon points"
                         % path)
    return points


def polygon_center(points):
    """Mean (lat, lon) of a list of (lat, lon) points - a rough inside point."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def max_radius_km(clat, clon, points):
    """Largest great-circle distance (km) from (clat, clon) to any point."""
    return float(max(latlon_to_distance_center(plon, plat, clon=clon, clat=clat)
                     for (plat, plon) in points))


def write_region_spec(path, name, shape, clat=None, clon=None,
                      region_radius_km=None, boundary_points=None,
                      semi_major_km=None, semi_minor_km=None,
                      orientation_deg=0.0):
    """
    Write an MPAS-Limited-Area "points file" describing the region to keep.

    Parameters
    ----------
    path : str
        Output points-file path.
    name : str
        Region name (also the basename of the regional mesh produced).
    shape : str
        "circle", "ellipse" or "custom".
    clat, clon : float
        Centre / reference point in degrees. For "custom" this must be a point
        *inside* the region.
    region_radius_km : float
        Circle radius in km (shape == "circle").
    boundary_points : list of (lat, lon)
        Boundary polygon in degrees (shape == "custom").
    semi_major_km, semi_minor_km : float
        Ellipse semi-axes in km (shape == "ellipse").
    orientation_deg : float
        Ellipse orientation in degrees, clockwise from north (shape ==
        "ellipse").

    Returns
    -------
    str
        ``path``.
    """
    lines = ["Name: %s" % name]

    if shape == "circle":
        if clat is None or clon is None or region_radius_km is None:
            raise ValueError("circle region needs clat, clon and "
                             "region_radius_km")
        lines.append("Type: circle")
        lines.append("Point: %s, %s" % (clat, clon))
        # MPAS-Limited-Area expects the radius in metres.
        lines.append("radius: %s" % (region_radius_km * 1000.0))

    elif shape == "ellipse":
        if None in (clat, clon, semi_major_km, semi_minor_km):
            raise ValueError("ellipse region needs clat, clon, semi_major_km "
                             "and semi_minor_km")
        lines.append("Type: ellipse")
        lines.append("Point: %s, %s" % (clat, clon))
        # Semi-axes are given to the tool in metres.
        lines.append("Semi-major-axis: %s" % (semi_major_km * 1000.0))
        lines.append("Semi-minor-axis: %s" % (semi_minor_km * 1000.0))
        lines.append("Orientation-angle: %s" % orientation_deg)

    elif shape == "custom":
        if clat is None or clon is None or not boundary_points:
            raise ValueError("custom region needs clat, clon (a point inside "
                             "the region) and boundary_points")
        lines.append("Type: custom")
        lines.append("Point: %s, %s" % (clat, clon))
        for (plat, plon) in boundary_points:
            lines.append("%s, %s" % (plat, plon))

    else:
        raise ValueError("Unknown region shape: %r" % shape)

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return path


def cut_regional_mesh(global_mesh, region_spec, work_dir):
    """
    Cut a regional (limited-area) mesh out of a global mesh.

    Calls the external `create_region` command from MPAS-Limited-Area. It reads
    the region name from the points file and writes ``<name>.grid.nc`` and
    ``<name>.graph.info`` into ``work_dir``.

    Raises a clear, actionable error if the tool is not installed.
    """
    if shutil.which("create_region") is None:
        raise RuntimeError(
            "The 'create_region' command (MPAS-Limited-Area) was not found.\n"
            "Upstream ships no setup.py, so install it from a local clone with\n"
            "a minimal local setup.py:\n"
            "    git clone https://github.com/MPAS-Dev/MPAS-Limited-Area.git\n"
            "    cd MPAS-Limited-Area\n"
            "    printf 'from setuptools import setup\\n"
            "setup(name=\"mpas-limited-area\", version=\"0.0.0\",\\n"
            "      packages=[\"limited_area\"], scripts=[\"create_region\"],\\n"
            "      install_requires=[\"numpy\", \"netCDF4\"])\\n' > setup.py\n"
            "    pip install -e .\n"
            "See grid_creation_scripts/README.md for details.")

    cmd = ["create_region", region_spec, global_mesh]
    print("Running:", " ".join(cmd), "(in", work_dir + ")")
    ret = subprocess.call(cmd, cwd=work_dir)
    if ret != 0:
        raise RuntimeError("create_region failed with exit code %d" % ret)

# NOTE: the generic mesh-resolution plot lives in jigsaw_util.plot_resolution
# (shared by both the global and regional grid scripts).
