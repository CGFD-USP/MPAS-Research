#!/usr/bin/env python
"""Cell-level maps and latitude profiles of the tropical meshes made from starting point sets, against the
frontal-Delaunay family (a) and NCAR's x4.1572866.

  python plot_mesh_maps.py <MPAS-Research meshes folder> <figure folder>

Reads the grid files of meshes/tropical-ref/tropical-<coarse>-<fine>km[-rings|-geo] and
ncar_reference/x4.1572866.grid.nc, writes start_cells_<coarse>-<fine>km.png (window across the
northern transition band), start_defects.png (non-hexagons and obtuse triangles on the globe) and
start_profiles.png (spacing over design, non-hexagon share and eps against latitude).
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
from matplotlib.collections import PolyCollection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_mesh_quality import triangle_angles  # noqa: E402
from create_tropical_refined_grid import EARTH_RADIUS_KM, LAT0, WIDTH as BLEND, cell_width  # noqa: E402
from plot_refined_meshes import WIDTH  # noqa: E402  (also sets the style)

SERIES = (("", "frontal Delaunay", "#d95f02"), ("-rings", "start: latitude rings", "#7570b3"),
          ("-geo", "start: icosahedral lattices", "#e6ab02"))
NCAR = ("NCAR x4.1572866", "#3d3d3a")
# lon0, lon1, lat0, lat1 (degrees) of the cell windows, across the northern band
WINDOWS = {30: (5.0, 17.0, 18.0, 48.0), 15: (5.0, 11.0, 24.0, 42.0)}
LAT_BINS = np.arange(0.0, 90.0 + 1.0, 1.0)


def path(root, suffix, r):
    name = "tropical-%g-%gkm%s" % (4 * r, r, suffix)
    return os.path.join(root, "tropical-ref", name, name + ".nc")


def ncar_path(root):
    return os.path.join(root, "tropical-ref", "ncar_reference", "x4.1572866.grid.nc")


def meshes(root, r):
    out = [(path(root, s, r), lab, c) for s, lab, c in SERIES]
    if r == 15:
        out.append((ncar_path(root), NCAR[0], NCAR[1]))
    return out


def read_mesh(p, fine):
    """Cell fields: lon, lat (deg), spacing over design - 1, max eps of the cell edges, nEdgesOnCell; obtuse vertices."""
    ds = netCDF4.Dataset(p)
    g = lambda v: ds.variables[v][:].filled() if np.ma.isMA(ds.variables[v][:]) else ds.variables[v][:]
    nc = ds.dimensions["nCells"].size
    xyz = np.stack([g(v) for v in ("xCell", "yCell", "zCell")], -1)
    xyz /= np.linalg.norm(xyz, axis=1)[:, None]
    xv = np.stack([g(v) for v in ("xVertex", "yVertex", "zVertex")], -1)
    xv /= np.linalg.norm(xv, axis=1)[:, None]
    nec, coe, voe = g("nEdgesOnCell"), g("cellsOnEdge") - 1, g("verticesOnEdge") - 1
    radius = float(ds.sphere_radius) if "sphere_radius" in ds.ncattrs() else 1.0
    dc = g("dcEdge") * (EARTH_RADIUS_KM / radius if radius == 1.0 else radius / 1e3)
    lat, lon = np.degrees(g("latCell")), np.degrees(g("lonCell"))
    hc = (np.bincount(coe[:, 0], dc, nc) + np.bincount(coe[:, 1], dc, nc)) / nec
    xt = xyz[coe[:, 0]] + xyz[coe[:, 1]]
    xt /= np.linalg.norm(xt, axis=1)[:, None]
    xm = xv[voe[:, 0]] + xv[voe[:, 1]]
    xm /= np.linalg.norm(xm, axis=1)[:, None]
    eps = np.linalg.norm(xt - xm, axis=1) / np.linalg.norm(xv[voe[:, 1]] - xv[voe[:, 0]], axis=1)
    ecell = np.zeros(nc)
    np.maximum.at(ecell, coe[:, 0], eps)
    np.maximum.at(ecell, coe[:, 1], eps)
    obt = np.flatnonzero(triangle_angles(xyz, g("cellsOnVertex") - 1).max(1) > 90.0)
    m = dict(lon=lon, lat=lat, dev=hc / cell_width(lat, fine) - 1.0, eps=ecell, nec=nec,
             obt_lon=np.degrees(g("lonVertex")[obt]), obt_lat=np.degrees(g("latVertex")[obt]),
             eps_edge=eps, lat_edge=np.degrees(g("latEdge")))
    m["ds"] = ds
    return m


def polygons(m, box):
    """Voronoi cells inside box as lon-lat polygons, and their indices."""
    ds = m["ds"]
    lo0, lo1, la0, la1 = box
    sel = np.flatnonzero((m["lon"] > lo0 - 1) & (m["lon"] < lo1 + 1) & (m["lat"] > la0 - 1) & (m["lat"] < la1 + 1))
    voc = ds.variables["verticesOnCell"][sel, :] - 1
    lonv, latv = np.degrees(ds.variables["lonVertex"][:]), np.degrees(ds.variables["latVertex"][:])
    polys = [np.column_stack([lonv[voc[i, :n]], latv[voc[i, :n]]]) for i, n in enumerate(m["nec"][sel])]
    return polys, sel


def fig_cells(root, out, r):
    box = WINDOWS[r]
    ms = meshes(root, r)
    fig, ax = plt.subplots(2, len(ms), figsize=(WIDTH, 6.4), sharex=True, sharey=True, constrained_layout=True)
    fields = (("dev", plt.cm.RdBu_r, (-0.15, 0.15), "spacing over design $- 1$"),
              ("eps", plt.cm.magma_r, (0.0, 0.08), "largest $\\varepsilon$ of the cell edges"))
    for j, (p, lab, _) in enumerate(ms):
        m = read_mesh(p, r)
        polys, sel = polygons(m, box)
        for i, (k, cmap, lim, clab) in enumerate(fields):
            a = ax[i, j]
            pc = PolyCollection(polys, array=m[k][sel], cmap=cmap, clim=lim, edgecolors="none")
            a.add_collection(pc)
            for n, mk, c in ((5, "o", "#1f78b4"), (7, "s", "#e31a1c")):
                q = sel[m["nec"][sel] == n]
                a.plot(m["lon"][q], m["lat"][q], mk, ms=2.2, mfc="none", mec=c, mew=0.7,
                       label="pentagon" if n == 5 else "heptagon")
            a.plot(m["obt_lon"], m["obt_lat"], "x", ms=4, color="k", mew=0.9, label="obtuse triangle")
            for s in (-1, 1):
                a.axhline(LAT0 + s * 2 * BLEND, color="0.4", lw=0.6, ls="--")
            a.set_xlim(box[0], box[1])
            a.set_ylim(box[2], box[3])
            a.set_aspect(1.0 / np.cos(np.radians(0.5 * (box[2] + box[3]))))
            a.grid(False)
            if i == 0:
                a.set_title(lab, fontsize=8)
            if j == len(ms) - 1:
                fig.colorbar(pc, ax=ax[i, :], shrink=0.8, label=clab, extend="both")
        m["ds"].close()
    for a in ax[-1]:
        a.set_xlabel("longitude (deg)")
    for a in ax[:, 0]:
        a.set_ylabel("latitude (deg)")
    fig.legend(*ax[0, 0].get_legend_handles_labels(), loc="outside lower center", ncol=3, markerscale=2)
    fig.suptitle("%g-%g km meshes, cells across the northern transition band (dashed: band edges)" % (4 * r, r))
    fig.savefig(os.path.join(out, "start_cells_%g-%gkm.png" % (4 * r, r)))
    plt.close(fig)


def fig_defects_and_profiles(root, out):
    r = 15
    ms = meshes(root, r)
    fig, ax = plt.subplots(2, 2, figsize=(WIDTH, 4.6), sharex=True, sharey=True, constrained_layout=True)
    prof = {}
    for a, (p, lab, c) in zip(ax.flat, ms):
        m = read_mesh(p, r)
        m["ds"].close()
        for n, col in ((5, "#1f78b4"), (7, "#e31a1c")):
            q = m["nec"] == n
            a.plot(m["lon"][q], m["lat"][q], ".", ms=0.8, color=col, label="pentagon" if n == 5 else "heptagon",
                   rasterized=True)
        a.plot(m["obt_lon"], m["obt_lat"], "x", ms=3, color="k", mew=0.8, label="obtuse triangle")
        a.set_title("%s: %d non-hexagons, %d obtuse" % (lab, (m["nec"] != 6).sum(), len(m["obt_lon"])), fontsize=8)
        a.set_xlim(0, 360)
        a.set_ylim(-90, 90)
        prof[lab] = (c, m)
    for a in ax[-1]:
        a.set_xlabel("longitude (deg)")
    for a in ax[:, 0]:
        a.set_ylabel("latitude (deg)")
    fig.legend(*ax[0, 0].get_legend_handles_labels(), loc="outside lower center", ncol=3, markerscale=6)
    fig.suptitle("60-15 km meshes, cells that are not hexagons and obtuse triangles")
    fig.savefig(os.path.join(out, "start_defects.png"))
    plt.close(fig)

    fig, ax = plt.subplots(1, 3, figsize=(WIDTH, 3.0), sharex=True, constrained_layout=True)
    lc = 0.5 * (LAT_BINS[1:] + LAT_BINS[:-1])
    for lab, (c, m) in prof.items():
        b = np.clip(np.digitize(np.abs(m["lat"]), LAT_BINS) - 1, 0, len(lc) - 1)
        n = np.bincount(b, minlength=len(lc))
        mean = np.bincount(b, m["dev"], len(lc)) / n
        lo, hi = np.full(len(lc), np.nan), np.full(len(lc), np.nan)
        for k in range(len(lc)):
            if n[k]:
                lo[k], hi[k] = np.percentile(m["dev"][b == k], [5, 95])
        ax[0].plot(lc, mean, color=c, label=lab)
        ax[0].fill_between(lc, lo, hi, color=c, alpha=0.15, lw=0)
        ax[1].semilogy(lc, np.maximum(100 * np.bincount(b, m["nec"] != 6, len(lc)) / n, 1e-3), color=c)
        be = np.clip(np.digitize(np.abs(m["lat_edge"]), LAT_BINS) - 1, 0, len(lc) - 1)
        ne = np.bincount(be, minlength=len(lc))
        ax[2].semilogy(lc, np.sqrt(np.bincount(be, m["eps_edge"] ** 2, len(lc)) / ne), color=c)
    for a in ax:
        a.axvspan(LAT0 - 2 * BLEND, LAT0 + 2 * BLEND, color="0.85", zorder=0, lw=0)
        a.set_xlabel("|latitude| (deg)")
        a.set_xlim(0, 90)
    ax[0].set_title("spacing over design $- 1$\n(mean, 5-95 % shaded)")
    ax[1].set_title("cells that are not\nhexagons (%)")
    ax[2].set_title("rms of $\\varepsilon$")
    fig.legend(*ax[0].get_legend_handles_labels(), loc="outside lower center", ncol=4)
    fig.suptitle("60-15 km meshes against latitude, both hemispheres (grey: transition band)")
    fig.savefig(os.path.join(out, "start_profiles.png"))
    plt.close(fig)


if __name__ == "__main__":
    root, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    for r in (30, 15):
        fig_cells(root, out, r)
    fig_defects_and_profiles(root, out)
