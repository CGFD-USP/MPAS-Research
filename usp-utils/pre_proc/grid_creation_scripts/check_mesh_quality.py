#!/usr/bin/env python
"""Quality metrics of an MPAS grid file, read with netCDF only.

  python check_mesh_quality.py <grid.nc> <fine km> [ratio] [-o <prefix>]

Writes <prefix>.json (scalars) and <prefix>.npz (profiles and histograms used by
plot_refined_meshes.py), and prints the scalars. <fine km> and ratio give the design cell width of
create_tropical_refined_grid.py that the realised spacing is compared with.

Cell spacing is the mean dcEdge of the cell edges. Triangles are the Delaunay dual of the Voronoi
mesh (cellsOnVertex). A triangle is obtuse when its largest angle exceeds 90 degrees, which is also
when its circumcentre (the Voronoi vertex) lies outside it.
"""
import argparse
import json
import os
import sys

import netCDF4
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_tropical_refined_grid import EARTH_RADIUS_KM, LAT0, RATIO, WIDTH, cell_width  # noqa: E402

CHUNK = 2_000_000
ANGLE_BINS = np.arange(0.0, 180.0 + 0.25, 0.25)
RATIO_BINS = np.linspace(1.0, 1.6, 241)
DEV_BINS = np.linspace(-0.4, 0.4, 161)
LAT_BINS = np.arange(-90.0, 90.0 + 1.0, 1.0)
MAP_SHAPE = (360, 720)
EPS_THRESHOLD = 0.01
EPS_BINS_SPACING = np.logspace(-0.1, 1.0, 45)  # edge length over the fine spacing


def in_band(lat, width=WIDTH):
    """Transition band of the design, |lat| within two widths of LAT0."""
    return np.abs(np.abs(lat) - LAT0) < 2.0 * width


def read(ds, name):
    return np.ma.getdata(ds.variables[name][:])


def triangle_angles(xyz, cells):
    """Angles (degrees, shape (n, 3)) of the chord triangles of the cell centres, per vertex."""
    p = xyz[cells]
    out = np.empty((len(cells), 3))
    for i in range(3):
        a, b = p[:, (i + 1) % 3] - p[:, i], p[:, (i + 2) % 3] - p[:, i]
        c = np.einsum("ij,ij->i", a, b) / np.sqrt(np.einsum("ij,ij->i", a, a) * np.einsum("ij,ij->i", b, b))
        out[:, i] = np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))
    return out


def ordering_fractions(ds):
    """Share of cell edges joining verticesOnCell(k), (k+1) (ordering P) or (k-1), (k) (ordering Q)."""
    eoc, voc, nec = read(ds, "edgesOnCell") - 1, read(ds, "verticesOnCell") - 1, read(ds, "nEdgesOnCell")
    voe = np.sort(read(ds, "verticesOnEdge") - 1, axis=1)
    k = np.arange(eoc.shape[1])[None, :]
    valid = k < nec[:, None]
    e = np.where(valid, eoc, 0)
    nxt = np.take_along_axis(voc, np.where(k + 1 < nec[:, None], k + 1, 0), 1)
    prv = np.take_along_axis(voc, np.where(k > 0, k - 1, nec[:, None] - 1), 1)
    res = {}
    for key, other in (("P", nxt), ("Q", prv)):
        pair = np.sort(np.stack([voc, other], -1), axis=-1)
        res[key] = float(np.mean((voe[e] == pair).all(-1)[valid]))
    return res


def centroid_offset(xyz, xv, voc, nec):
    """Distance from each generator to the centroid of its Voronoi cell (fan of chord triangles, projected to the
    sphere) over the square root of the cell area, both on the unit sphere."""
    out = np.empty(len(xyz))
    for i in range(0, len(xyz), CHUNK // 4):
        sl = slice(i, i + CHUNK // 4)
        c, n, v = xyz[sl], nec[sl], xv[voc[sl]]
        s, area = np.zeros_like(c), np.zeros(len(c))
        for k in range(v.shape[1]):
            a, b = v[:, k], v[np.arange(len(c)), np.where(k + 1 < n, k + 1, 0)]
            w = 0.5 * np.linalg.norm(np.cross(a - c, b - c), axis=1) * (k < n)
            s += w[:, None] * (c + a + b) / 3.0
            area += w
        cen = s / np.linalg.norm(s, axis=1)[:, None]
        out[sl] = np.linalg.norm(cen - c, axis=1) / np.sqrt(area)
    return out


def measure(path, fine, ratio=RATIO, width=WIDTH):
    ds = netCDF4.Dataset(path)
    radius = float(ds.sphere_radius) if "sphere_radius" in ds.ncattrs() else 1.0
    scale = EARTH_RADIUS_KM / radius if radius == 1.0 else radius / 1e3
    nc, ne, nv = (ds.dimensions[d].size for d in ("nCells", "nEdges", "nVertices"))
    lat = np.degrees(read(ds, "latCell"))
    lon = np.degrees(read(ds, "lonCell"))
    xyz = np.stack([read(ds, v) for v in ("xCell", "yCell", "zCell")], -1) / radius
    dc = read(ds, "dcEdge") * scale
    dv = read(ds, "dvEdge") * scale
    area = read(ds, "areaCell") * scale ** 2
    nec = read(ds, "nEdgesOnCell")
    coe = read(ds, "cellsOnEdge") - 1

    hc = (np.bincount(coe[:, 0], dc, nc) + np.bincount(coe[:, 1], dc, nc)) / nec
    sc = {"file": os.path.basename(path), "size_bytes": os.path.getsize(path), "nCells": nc, "nEdges": ne,
          "nVertices": nv, "sphere_radius": radius, "ordering": ordering_fractions(ds)}
    sc["nEdgesOnCell"] = {int(k): int(v) for k, v in zip(*np.unique(nec, return_counts=True))}

    # triangles
    cov = read(ds, "cellsOnVertex") - 1
    ang_hist, max_hist = np.zeros(len(ANGLE_BINS) - 1), np.zeros(len(ANGLE_BINS) - 1)
    amin, amax, obtuse, asum = 180.0, 0.0, 0, 0.0
    lat_v = np.degrees(read(ds, "latVertex"))
    band_dev, band_n = 0.0, 0
    for i in range(0, nv, CHUNK):
        a = triangle_angles(xyz, cov[i:i + CHUNK])
        ang_hist += np.histogram(a, ANGLE_BINS)[0]
        max_hist += np.histogram(a.max(1), ANGLE_BINS)[0]
        amin, amax = min(amin, a.min()), max(amax, a.max())
        obtuse += int((a.max(1) > 90.0).sum())
        bm = in_band(lat_v[i:i + CHUNK], width)
        band_dev += float((a.max(1)[bm] - 60.0).sum())
        band_n += int(bm.sum())
        asum += a.sum()
    sc["band_max_angle_minus_60_mean"] = band_dev / band_n
    sc.update(angle_min=float(amin), angle_max=float(amax), angle_mean=asum / (3 * nv), obtuse=obtuse)
    del cov

    # Voronoi edge against the segment between the cell centres
    voe = read(ds, "verticesOnEdge") - 1
    xv = np.stack([read(ds, v) for v in ("xVertex", "yVertex", "zVertex")], -1) / radius
    mid = 0.5 * (xyz[coe[:, 0]] + xyz[coe[:, 1]])
    d = xv[voe[:, 1]] - xv[voe[:, 0]]
    t = np.einsum("ij,ij->i", mid - xv[voe[:, 0]], d) / np.einsum("ij,ij->i", d, d)
    sc["edges_midpoint_outside"] = int(((t < 0.0) | (t > 1.0)).sum())
    # edge-point offset eps = |xt - xm| / dvEdge, xt midpoint of the cell arc, xm midpoint of the Voronoi arc
    xt = mid / np.linalg.norm(mid, axis=1)[:, None]
    xm = xv[voe[:, 0]] + xv[voe[:, 1]]
    xm /= np.linalg.norm(xm, axis=1)[:, None]
    eps = np.linalg.norm(xt - xm, axis=1) / np.linalg.norm(d, axis=1)
    xe = np.stack([read(ds, v) for v in ("xEdge", "yEdge", "zEdge")], -1) / radius
    xe_off = np.linalg.norm(xe - xt, axis=1) / np.linalg.norm(d, axis=1)
    lat_e = np.degrees(read(ds, "latEdge"))
    transition = in_band(lat_e, width)
    near_defect = (nec[coe[:, 0]] != 6) | (nec[coe[:, 1]] != 6)
    big = eps > EPS_THRESHOLD
    sc["edge_point"] = {"eps_max": float(eps.max()), "eps_rms": float(np.sqrt((eps ** 2).mean())),
                        "eps_gt_0.01": int(big.sum()), "eps_gt_0.01_share": float(big.mean()),
                        "eps_gt_0.01_next_to_non_hexagon": int((big & near_defect).sum()),
                        "eps_gt_0.01_in_transition": int((big & transition).sum()),
                        "edges_in_transition": int(transition.sum()),
                        "eps_max_in_transition": float(eps[transition].max()),
                        "eps_rms_in_transition": float(np.sqrt((eps[transition] ** 2).mean())),
                        "eps_rms_outside_transition": float(np.sqrt((eps[~transition] ** 2).mean())),
                        "xEdge_minus_xt_max": float(xe_off.max())}
    eb = np.clip(np.digitize(dc / fine, EPS_BINS_SPACING) - 1, 0, len(EPS_BINS_SPACING) - 2)
    cnt_e = np.bincount(eb, minlength=len(EPS_BINS_SPACING) - 1)
    emax = np.zeros(len(cnt_e))
    np.maximum.at(emax, eb, eps)
    eps_vs_h = np.column_stack([cnt_e, np.sqrt(np.bincount(eb, eps ** 2, len(cnt_e)) / np.maximum(cnt_e, 1)), emax])
    eps_lat = np.zeros((len(LAT_BINS) - 1, 2))
    lb = np.clip(np.digitize(lat_e, LAT_BINS) - 1, 0, len(LAT_BINS) - 2)
    np.maximum.at(eps_lat[:, 1], lb, eps)
    n_lat = np.bincount(lb, minlength=len(LAT_BINS) - 1)
    eps_lat[:, 0] = np.sqrt(np.bincount(lb, eps ** 2, len(n_lat)) / np.maximum(n_lat, 1))
    del xt, xm, xe
    off = centroid_offset(xyz, xv, read(ds, "verticesOnCell") - 1, nec)
    sc["centroid_offset"] = {"rms": float(np.sqrt((off ** 2).mean())), "max": float(off.max())}
    sc["dv_over_dc"] = {"min": float((dv / dc).min()), "median": float(np.median(dv / dc)),
                        "max": float((dv / dc).max())}
    del xv, mid, d, t

    # neighbouring cells
    h1, h2 = hc[coe[:, 0]], hc[coe[:, 1]]
    ratio_n = np.maximum(h1, h2) / np.minimum(h1, h2)
    grad = np.abs(h1 - h2) / dc
    sc["neighbour_ratio"] = {"max": float(ratio_n.max()), "p99.9": float(np.percentile(ratio_n, 99.9)),
                             "p99": float(np.percentile(ratio_n, 99)), "median": float(np.median(ratio_n))}
    sc["spacing_gradient"] = {"max": float(grad.max()), "p99.9": float(np.percentile(grad, 99.9)),
                              "median": float(np.median(grad))}
    ratio_hist = np.histogram(np.minimum(ratio_n, RATIO_BINS[-1] - 1e-9), RATIO_BINS)[0]

    # regularity and design
    hexa = area / (np.sqrt(3.0) / 2.0 * hc ** 2)
    dev = hc / cell_width(lat, fine, ratio, width) - 1.0
    sc["area_over_hexagon"] = {"mean": float(hexa.mean()), "std": float(hexa.std())}
    sc["spacing_minus_design"] = {"mean": float(dev.mean()), "rms": float(np.sqrt((dev ** 2).mean())),
                                  "p1": float(np.percentile(dev, 1)), "p99": float(np.percentile(dev, 99))}
    cb = in_band(lat, width)
    eb_ = in_band(lat_e, width)
    km_deg = np.radians(1.0) * EARTH_RADIUS_KM
    phi = np.linspace(0.0, 90.0, 9001)
    ib = in_band(phi, width)
    sc["band"] = {"cells": int(cb.sum()), "cell_share": float(cb.mean()),
                  "width_km": 4.0 * width * km_deg,
                  "design_grad_max": float(np.abs(np.gradient(cell_width(phi, fine, ratio, width), phi)).max() / km_deg),
                  "neighbour_ratio_minus_1_mean": float((ratio_n[eb_] - 1.0).mean()),
                  "neighbour_ratio_minus_1_p99": float(np.percentile(ratio_n[eb_] - 1.0, 99)),
                  "non_hexagon_share": float((nec[cb] != 6).mean()),
                  "area_over_hexagon_std": float(hexa[cb].std()),
                  "eps_rms": sc["edge_point"]["eps_rms_in_transition"],
                  "max_angle_minus_60_mean": sc.pop("band_max_angle_minus_60_mean"),
                  "cells_across": float(np.trapezoid(1.0 / cell_width(phi[ib], fine, ratio, width), phi[ib]) * km_deg)}
    sc["spacing_km"] = {"min": float(hc.min()), "max": float(hc.max())}

    # latitude profile and map
    ib = np.clip(np.digitize(lat, LAT_BINS) - 1, 0, len(LAT_BINS) - 2)
    order = np.argsort(ib, kind="stable")
    parts = np.split(hc[order], np.cumsum(np.bincount(ib, minlength=len(LAT_BINS) - 1))[:-1])
    prof = np.array([[len(q)] + (list(np.percentile(q, [0, 50, 100])) + [q.mean()] if len(q) else [np.nan] * 4)
                     for q in parts])
    jy = np.clip(((lat + 90.0) / 180.0 * MAP_SHAPE[0]).astype(int), 0, MAP_SHAPE[0] - 1)
    jx = np.clip((np.mod(lon, 360.0) / 360.0 * MAP_SHAPE[1]).astype(int), 0, MAP_SHAPE[1] - 1)
    flat = jy * MAP_SHAPE[1] + jx
    cnt = np.bincount(flat, minlength=MAP_SHAPE[0] * MAP_SHAPE[1])
    with np.errstate(invalid="ignore"):
        maps = {"map_spacing": (np.bincount(flat, hc, len(cnt)) / cnt).reshape(MAP_SHAPE),
                "map_deviation": (np.bincount(flat, dev, len(cnt)) / cnt).reshape(MAP_SHAPE)}
    arrays = {"lat_bins": LAT_BINS, "lat_profile": prof, "angle_bins": ANGLE_BINS, "angle_hist": ang_hist,
              "angle_max_hist": max_hist, "ratio_bins": RATIO_BINS, "ratio_hist": ratio_hist,
              "eps_spacing_bins": EPS_BINS_SPACING, "eps_vs_spacing": eps_vs_h, "eps_lat": eps_lat,
              "dev_bins": DEV_BINS, "dev_hist": np.histogram(np.clip(dev, DEV_BINS[0], DEV_BINS[-1] - 1e-9), DEV_BINS)[0],
              **maps}
    return sc, arrays


def check(path, fine, ratio=RATIO, prefix=None, width=WIDTH):
    sc, arrays = measure(path, fine, ratio, width)
    sc["width_deg"] = width
    prefix = prefix or os.path.splitext(path)[0] + ".quality"
    with open(prefix + ".json", "w") as f:
        json.dump(sc, f, indent=1)
    np.savez_compressed(prefix + ".npz", **arrays)
    print(json.dumps(sc, indent=1))
    return sc


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("grid")
    p.add_argument("fine", type=float)
    p.add_argument("ratio", type=float, nargs="?", default=RATIO)
    p.add_argument("--width", type=float, default=WIDTH, help="transition width of the design (degrees)")
    p.add_argument("-o", "--prefix", help="output prefix (default <grid>.quality)")
    a = p.parse_args()
    check(a.grid, a.fine, a.ratio, a.prefix, a.width)
