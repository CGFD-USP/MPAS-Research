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


def polygon_inside_point(points):
    """
    Return a (lat, lon) point guaranteed to be inside the polygon.

    MPAS-Limited-Area needs the reference point to lie inside the region, and
    for concave polygons the vertex mean (``polygon_center``) can fall outside.
    Use shapely's representative_point() when available, otherwise fall back to
    the vertex mean. ``points`` is a list of (lat, lon) tuples.
    """
    try:
        from shapely.geometry import Polygon
        poly = Polygon([(lon, lat) for (lat, lon) in points])
        pt = poly.representative_point()
        return pt.y, pt.x  # (lat, lon)
    except Exception:
        return polygon_center(points)


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


def read_region_spec(path):
    """
    Read back an MPAS-Limited-Area points file written by write_region_spec.

    The inverse of write_region_spec, so an existing ``<name>.pts`` can be
    reused to rebuild a region at a different resolution instead of retyping
    its coordinates.

    Returns
    -------
    dict
        ``name``, ``shape`` ("circle", "ellipse" or "custom"), ``clat``,
        ``clon``, and whichever of ``region_radius_km``, ``semi_major_km``,
        ``semi_minor_km``, ``orientation_deg``, ``boundary_points`` apply.
        Lengths are converted from the file's metres to km.
    """
    spec = {"name": None, "shape": None, "clat": None, "clon": None,
            "region_radius_km": None, "semi_major_km": None,
            "semi_minor_km": None, "orientation_deg": 0.0,
            "boundary_points": []}

    with open(path) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue

            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip().lower()
                value = value.strip()

                if key == "name":
                    spec["name"] = value
                elif key == "type":
                    shape = value.lower()
                    if shape not in ("circle", "ellipse", "custom"):
                        raise ValueError(
                            "%r has Type: %s, which this script cannot rebuild "
                            "(only circle, ellipse and custom)" % (path, value))
                    spec["shape"] = shape
                elif key == "point":
                    lat, _, lon = value.partition(',')
                    spec["clat"], spec["clon"] = float(lat), float(lon)
                elif key == "radius":
                    spec["region_radius_km"] = float(value) / 1000.0
                elif key == "semi-major-axis":
                    spec["semi_major_km"] = float(value) / 1000.0
                elif key == "semi-minor-axis":
                    spec["semi_minor_km"] = float(value) / 1000.0
                elif key == "orientation-angle":
                    spec["orientation_deg"] = float(value)
                # unknown keys (channel bounds etc.) are ignored on purpose

            elif ',' in line:
                lat, _, lon = line.partition(',')
                spec["boundary_points"].append((float(lat), float(lon)))

    if spec["shape"] is None:
        raise ValueError("%r has no 'Type:' line; is it really a points file?"
                         % path)
    if spec["clat"] is None:
        raise ValueError("%r has no 'Point:' line" % path)
    if spec["shape"] == "custom" and len(spec["boundary_points"]) < 3:
        raise ValueError("%r is Type: custom but lists only %d boundary points"
                         % (path, len(spec["boundary_points"])))

    return spec


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


# ----------------------------------------------------------------------------
# Geometry for regional meshes with a buffer / transition zone
#
# Everything below works in a local azimuthal-equidistant plane centred on the
# region, where distance from the centre is exact and the antimeridian / pole
# wrapping problems disappear for any region well under a hemisphere. That lets
# us use shapely for the two hard parts: offsetting the region boundary outward
# by a constant distance, and testing which grid points are inside it.
# ----------------------------------------------------------------------------

# Sphere radius (km) used by the new buffer code. The legacy
# latlon_to_distance_center uses 6367 km; the difference is ~0.07 %, i.e. well
# under half a kilometre over the radii involved here, and the legacy value is
# left alone so existing meshes stay reproducible.
EARTH_RADIUS_KM = 6371.0

# A region much larger than this cannot be treated as flat in the local plane.
MAX_REGION_RADIUS_KM = 8000.0


def latlon_to_local_xy(lats, lons, clat, clon, radius_km=EARTH_RADIUS_KM):
    """
    Project (lat, lon) in degrees to a local azimuthal-equidistant plane in km.

    The centre maps to (0, 0); great-circle distance from the centre and
    bearing are both preserved exactly, which is what the buffer geometry
    needs. ``x`` points east, ``y`` points north.
    """
    lats = np.radians(np.asarray(lats, dtype=float))
    lons = np.radians(np.asarray(lons, dtype=float))
    clat_r, clon_r = np.radians(clat), np.radians(clon)

    dlon = lons - clon_r
    cos_c = (np.sin(clat_r) * np.sin(lats)
             + np.cos(clat_r) * np.cos(lats) * np.cos(dlon))
    c = np.arccos(np.clip(cos_c, -1.0, 1.0))          # angular distance
    dist = c * radius_km

    # bearing from the centre, clockwise from north
    bearing = np.arctan2(np.cos(lats) * np.sin(dlon),
                         np.cos(clat_r) * np.sin(lats)
                         - np.sin(clat_r) * np.cos(lats) * np.cos(dlon))

    return dist * np.sin(bearing), dist * np.cos(bearing)


def local_xy_to_latlon(x_km, y_km, clat, clon, radius_km=EARTH_RADIUS_KM):
    """Inverse of latlon_to_local_xy; returns (lats, lons) in degrees."""
    x_km = np.asarray(x_km, dtype=float)
    y_km = np.asarray(y_km, dtype=float)
    clat_r, clon_r = np.radians(clat), np.radians(clon)

    dist = np.hypot(x_km, y_km)
    bearing = np.arctan2(x_km, y_km)
    c = dist / radius_km

    lats = np.arcsin(np.sin(clat_r) * np.cos(c)
                     + np.cos(clat_r) * np.sin(c) * np.cos(bearing))
    lons = clon_r + np.arctan2(np.sin(bearing) * np.sin(c) * np.cos(clat_r),
                               np.cos(c) - np.sin(clat_r) * np.sin(lats))

    lons = (np.degrees(lons) + 180.0) % 360.0 - 180.0
    return np.degrees(lats), lons


def _densify_xy(x, y, spacing_km):
    """Insert points along a closed polyline so no segment exceeds spacing_km."""
    xs, ys = [], []
    n = len(x)
    for i in range(n):
        j = (i + 1) % n
        seg = np.hypot(x[j] - x[i], y[j] - y[i])
        steps = max(1, int(np.ceil(seg / spacing_km)))
        for k in range(steps):
            f = k / steps
            xs.append(x[i] + f * (x[j] - x[i]))
            ys.append(y[i] + f * (y[j] - y[i]))
    return np.asarray(xs), np.asarray(ys)


def region_boundary_polygon(shape, clat, clon, region_radius_km=None,
                            semi_major_km=None, semi_minor_km=None,
                            orientation_deg=0.0, boundary_points=None,
                            spacing_km=None, n_points=720):
    """
    Densified boundary of the area of interest as a list of (lat, lon) degrees.

    This is the *core* boundary -- the edge of the region the user actually
    cares about -- not the cut boundary. ``spacing_km`` caps the distance
    between consecutive points; it should be small compared with the buffer
    width so that distances measured to the sampled polyline are accurate.
    """
    if shape == "circle":
        if region_radius_km is None:
            raise ValueError("circle boundary needs region_radius_km")
        if spacing_km:
            n_points = max(n_points,
                           int(np.ceil(2.0 * np.pi * region_radius_km
                                       / spacing_km)))
        th = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
        x = region_radius_km * np.sin(th)
        y = region_radius_km * np.cos(th)

    elif shape == "ellipse":
        if semi_major_km is None or semi_minor_km is None:
            raise ValueError("ellipse boundary needs semi_major_km and "
                             "semi_minor_km")
        if spacing_km:
            n_points = max(n_points,
                           int(np.ceil(2.0 * np.pi * semi_major_km
                                       / spacing_km)))
        th = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
        # semi-major along the bearing given by orientation_deg (clockwise
        # from north), matching write_region_spec's convention
        u = semi_major_km * np.cos(th)
        v = semi_minor_km * np.sin(th)
        a = np.radians(orientation_deg)
        x = u * np.sin(a) + v * np.cos(a)
        y = u * np.cos(a) - v * np.sin(a)

    elif shape in ("box", "polygon", "custom"):
        if not boundary_points:
            raise ValueError("%s boundary needs boundary_points" % shape)
        lats = [p[0] for p in boundary_points]
        lons = [p[1] for p in boundary_points]
        x, y = latlon_to_local_xy(lats, lons, clat, clon)
        if spacing_km:
            x, y = _densify_xy(x, y, spacing_km)

    else:
        raise ValueError("Unknown region shape: %r" % shape)

    rmax = float(np.max(np.hypot(x, y)))
    if rmax > MAX_REGION_RADIUS_KM:
        raise ValueError(
            "region extends %.0f km from its centre, beyond the %.0f km limit "
            "of the local-plane buffer geometry. Use a smaller region."
            % (rmax, MAX_REGION_RADIUS_KM))

    lats, lons = local_xy_to_latlon(x, y, clat, clon)
    return list(zip(lats.tolist(), lons.tolist()))


def _as_ccw_polygon(x, y):
    """Build a CCW shapely polygon from local-plane coordinates."""
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    return orient(Polygon(np.column_stack([x, y])), 1.0)


def offset_polygon_km(points, delta_km, clat, clon, quad_segs=32):
    """
    Push a boundary outward by a constant ``delta_km`` measured perpendicular
    to the boundary.

    Uses shapely's buffer in the local azimuthal-equidistant plane, which is
    the true constant-distance offset: convex corners are rounded exactly the
    way the distance field rounds them, and self-intersections created across
    the mouth of a concave notch are dissolved. Naively pushing each vertex
    radially away from the centre would leave the band up to 4x too thin near
    the corners of an elongated box, and would self-intersect for concave
    polygons.

    Parameters
    ----------
    points : list of (lat, lon)
    delta_km : float
        Outward offset in km. Non-positive returns ``points`` unchanged.
    clat, clon : float
        Centre of the local projection.

    Returns
    -------
    list of (lat, lon)
        A simple, counter-clockwise polygon.
    """
    if delta_km <= 0.0:
        return list(points)

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    x, y = latlon_to_local_xy(lats, lons, clat, clon)

    poly = _as_ccw_polygon(x, y).buffer(delta_km, quad_segs=quad_segs,
                                        join_style="round")

    if poly.geom_type == "MultiPolygon":
        parts = sorted(poly.geoms, key=lambda g: g.area, reverse=True)
        print("WARNING: offsetting the region boundary produced %d disjoint "
              "pieces; keeping the largest (%.0f%% of the total area)."
              % (len(parts), 100.0 * parts[0].area / poly.area))
        poly = parts[0]
    if poly.interiors:
        from shapely.geometry import Polygon
        print("WARNING: offset boundary contains %d hole(s); they are dropped "
              "-- create_region only understands a simple outer ring."
              % len(poly.interiors))
        poly = Polygon(poly.exterior)

    from shapely.geometry.polygon import orient
    poly = orient(poly, 1.0)

    ox, oy = np.asarray(poly.exterior.coords[:-1]).T
    olat, olon = local_xy_to_latlon(ox, oy, clat, clon)
    return list(zip(olat.tolist(), olon.tolist()))


def circle_distance_fn(clat, clon, radius_km):
    """
    Signed-distance callable for a circular region (negative inside).

    Exact and allocation-light -- the fast path used by --shape circle.
    """
    def dist_fn(lons, lats, pad_km=None):
        d = latlon_to_distance_center(lons, lats, clon=clon, clat=clat)
        return d - radius_km

    return dist_fn


def polygon_distance_fn(points, clat, clon, spacing_km=None, workers=-1):
    """
    Signed-distance callable for an arbitrary region boundary.

    Builds a KDTree over the densified boundary in 3-D Cartesian space and
    converts the chord distance it returns back to a great-circle distance.
    The sign is resolved with a vectorised point-in-polygon test in the local
    plane, run only on the points close enough to possibly be inside -- for a
    global lat/lon grid that is a small fraction of the total.

    Parameters
    ----------
    points : list of (lat, lon)
        Region boundary, already densified enough that the chord between
        consecutive points is short compared with the buffer width.
    clat, clon : float
        Centre of the region (used for the cheap distance pre-filter and the
        local projection).
    spacing_km : float, optional
        Re-densify the boundary to at most this spacing before building the
        tree.
    workers : int
        Passed to cKDTree.query; -1 uses all cores.
    """
    from scipy.spatial import cKDTree
    from shapely import contains_xy

    lats = np.asarray([p[0] for p in points], dtype=float)
    lons = np.asarray([p[1] for p in points], dtype=float)

    bx, by = latlon_to_local_xy(lats, lons, clat, clon)
    poly = _as_ccw_polygon(bx, by)

    if spacing_km:
        bx, by = _densify_xy(bx, by, spacing_km)
        lats, lons = local_xy_to_latlon(bx, by, clat, clon)

    r_max = float(np.max(np.hypot(bx, by)))

    lat_r, lon_r = np.radians(lats), np.radians(lons)
    boundary_xyz = np.column_stack([np.cos(lat_r) * np.cos(lon_r),
                                    np.cos(lat_r) * np.sin(lon_r),
                                    np.sin(lat_r)])
    tree = cKDTree(boundary_xyz)

    def dist_fn(lons2d, lats2d, pad_km=None):
        lons2d = np.asarray(lons2d, dtype=float)
        lats2d = np.asarray(lats2d, dtype=float)
        lons2d, lats2d = np.broadcast_arrays(lons2d, lats2d)

        d_centre = latlon_to_distance_center(lons2d, lats2d, clon=clon,
                                             clat=clat)

        # Anything comfortably beyond the region cannot be inside it and is
        # far enough that the caller's profile has flattened out; skip the
        # expensive work there and report a distance that is merely large.
        pad = r_max + (pad_km if pad_km is not None else 4.0 * r_max)
        near = d_centre <= pad
        out = d_centre - r_max      # monotone, correct far-field ordering
        if not near.any():
            return out

        lat_n = np.radians(lats2d[near])
        lon_n = np.radians(lons2d[near])
        query = np.column_stack([np.cos(lat_n) * np.cos(lon_n),
                                 np.cos(lat_n) * np.sin(lon_n),
                                 np.sin(lat_n)])
        chord, _ = tree.query(query, workers=workers)
        gc = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2.0, 0.0, 1.0))

        x, y = latlon_to_local_xy(lats2d[near], lons2d[near], clat, clon)
        inside = contains_xy(poly, x, y)
        out[near] = np.where(inside, -gc, gc)
        return out

    return dist_fn
