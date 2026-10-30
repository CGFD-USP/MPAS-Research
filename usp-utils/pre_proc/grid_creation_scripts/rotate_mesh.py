#!/usr/bin/env python3
"""Rotates a spherical MPAS mesh so that the point at latitude 0, longitude 0 moves to a given centre.

NCAR's variable-resolution meshes have their refinement centred at (0, 0). The rotation turns the cell, vertex and edge
positions and their latitudes and longitudes, and leaves everything else as it is, so the output is meant for
regenerate-mesh.jl, which recomputes the geometry from the cell and vertex positions and the topology.

Usage: rotate_mesh.py <grid.nc> <out.nc> --lat <deg> --lon <deg>
"""
import argparse
import shutil

import numpy as np
from netCDF4 import Dataset


def rotation(lat0, lon0):
    """R_z(lon0) R_y(-lat0), which maps (1, 0, 0) to the unit vector at (lat0, lon0)."""
    a, b = np.radians(lat0), np.radians(lon0)
    ry = np.array([[np.cos(a), 0.0, -np.sin(a)], [0.0, 1.0, 0.0], [np.sin(a), 0.0, np.cos(a)]])
    rz = np.array([[np.cos(b), -np.sin(b), 0.0], [np.sin(b), np.cos(b), 0.0], [0.0, 0.0, 1.0]])
    return rz @ ry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("grid")
    ap.add_argument("out")
    ap.add_argument("--lat", type=float, required=True, help="latitude of the new centre (deg)")
    ap.add_argument("--lon", type=float, required=True, help="longitude of the new centre (deg)")
    args = ap.parse_args()

    shutil.copyfile(args.grid, args.out)
    r = rotation(args.lat, args.lon)
    with Dataset(args.out, "r+") as ds:
        ds.set_auto_mask(False)
        for loc in ("Cell", "Vertex", "Edge"):
            p = np.vstack([ds[f"{c}{loc}"][:] for c in "xyz"])
            q = r @ p
            for i, c in enumerate("xyz"):
                ds[f"{c}{loc}"][:] = q[i]
            norm = np.linalg.norm(q, axis=0)
            ds[f"lat{loc}"][:] = np.arcsin(q[2] / norm)
            ds[f"lon{loc}"][:] = np.mod(np.arctan2(q[1], q[0]), 2.0 * np.pi)
        ds.setncattr("rotation", f"rotate_mesh.py: (0, 0) moved to lat {args.lat} lon {args.lon} (deg)")


if __name__ == "__main__":
    main()
