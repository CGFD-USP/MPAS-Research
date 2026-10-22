#!/usr/bin/env python
"""Figures for the tropical meshes made by continuation in the density (A) and by coarsening NCAR's x4.1572866 (B),
against the frontal-Delaunay, rings and geo meshes and NCAR.

  python plot_continuation_meshes.py <MPAS-Research meshes folder> <M4 mesh folder> <figure folder>

Reads meshes/tropical-ref/tropical-<coarse>-<fine>km[-rings|-geo] and the folders of run_continuation_study.sh
(A, s<fine>/) and run_coarsen_meshes.sh (B, b/), writes cont_scaling.png, cont_profiles.png and
cont_cells_<coarse>-<fine>km.png.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plot_mesh_maps as maps  # noqa: E402
from create_tropical_refined_grid import cell_width  # noqa: E402
from plot_refined_meshes import WIDTH, centres  # noqa: E402  (also sets the style)

FINE = (120, 60, 30, 15)
A_NAME = "t%g-%g-c5-q1e-4-p1"
# label, colour, marker, mesh folder of the fine spacing r
SERIES = (
    ("frontal Delaunay", "#d95f02", "s", lambda g, m, r: (os.path.join(g, "tropical-ref"), "tropical-%g-%gkm" % (4 * r, r))),
    ("start: latitude rings", "#7570b3", "v", lambda g, m, r: (os.path.join(g, "tropical-ref"), "tropical-%g-%gkm-rings" % (4 * r, r))),
    ("start: icosahedral lattices", "#e6ab02", "D", lambda g, m, r: (os.path.join(g, "tropical-ref"), "tropical-%g-%gkm-geo" % (4 * r, r))),
    ("A: continuation from the icosahedral lattice", "#e7298a", "P", lambda g, m, r: (os.path.join(m, "s%g" % r), A_NAME % (4 * r, r))),
    ("B: NCAR coarsened level by level", "#1b9e77", "^", lambda g, m, r: (os.path.join(m, "b"), "chain-%g-%g" % (4 * r, r))),
    ("B: NCAR coarsened in one jump", "#66a61e", "o", lambda g, m, r: (os.path.join(m, "b"), "jump-%g-%g" % (4 * r, r))),
)
NCAR = ("NCAR x4.1572866 (SCVT)", "#3d3d3a")


def quality(folder, name):
    p = os.path.join(folder, name, name + ".quality")
    return (json.load(open(p + ".json")), np.load(p + ".npz")) if os.path.exists(p + ".json") else None


def series(g, m):
    out = []
    for label, c, mk, where in SERIES:
        q = {r: quality(*where(g, m, r)) for r in FINE}
        out.append((label, c, mk, {r: v for r, v in q.items() if v}))
    return out


def ncar(g):
    return quality(os.path.join(g, "tropical-ref", "ncar_reference"), "ncar") or \
        (json.load(open(os.path.join(g, "tropical-ref", "ncar_reference", "ncar.json"))),
         np.load(os.path.join(g, "tropical-ref", "ncar_reference", "ncar.npz")))


def fig_scaling(g, m, out):
    keys = (lambda s: s["edge_point"]["eps_rms"],
            lambda s: 100 * (1 - s["nEdgesOnCell"].get("6", 0) / s["nCells"]),
            lambda s: s["spacing_minus_design"]["rms"])
    titles = ("rms of $\\varepsilon$", "cells that are not hexagons (%)", "rms of (spacing / design $- 1$)")
    fig, ax = plt.subplots(1, 3, figsize=(WIDTH, 3.3), constrained_layout=True)
    for label, c, mk, q in series(g, m):
        for a, f in zip(ax, keys):
            a.loglog(list(q), [f(v[0]) for v in q.values()], mk + "-", color=c, label=label)
    nc = ncar(g)[0]
    for a, f, t in zip(ax, keys, titles):
        a.loglog([15], [f(nc)], "o", color=NCAR[1], label=NCAR[0])
        a.set_xlabel("fine spacing (km)")
        a.set_title(t)
        a.set_xticks(FINE, [str(r) for r in FINE])
        a.minorticks_off()
    fig.legend(*ax[0].get_legend_handles_labels(), loc="outside lower center", ncol=2)
    fig.suptitle("Tropical meshes (coarse = 4 x fine)")
    fig.savefig(os.path.join(out, "cont_scaling.png"))
    plt.close(fig)


def fig_profiles(g, m, out, r=60):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.3), sharey=False, constrained_layout=True)
    for label, c, mk, q in series(g, m):
        if r in q:
            arr = q[r][1]
            lat = centres(arr["lat_bins"])
            ax[0].plot(lat, arr["lat_profile"][:, 4] / cell_width(lat, r) - 1.0, color=c, label=label)
            ax[1].semilogy(lat, np.maximum(arr["eps_lat"][:, 0], 1e-5), color=c)
    ax[0].set_title("mean cell spacing over design $- 1$")
    ax[1].set_title("rms of $\\varepsilon$ per degree")
    for a in ax:
        a.set_xlabel("latitude (deg)")
    fig.legend(*ax[0].get_legend_handles_labels(), loc="outside lower center", ncol=2)
    fig.suptitle("%g-%g km meshes against latitude" % (4 * r, r))
    fig.savefig(os.path.join(out, "cont_profiles.png"))
    plt.close(fig)


def fig_cells(g, m, out, r):
    ms = []
    for label, c, mk, where in SERIES:
        folder, name = where(g, m, r)
        if name.endswith("rings") or name.startswith("jump"):
            continue
        if os.path.exists(os.path.join(folder, name, name + ".nc")):
            ms.append((os.path.join(folder, name, name + ".nc"), label.replace("A: continuation from the icosahedral lattice", "A: continuation"), c))
    maps.fig_cells(g, out, r, ms, "cont_cells_%g-%gkm.png" % (4 * r, r),
                   "%g-%g km meshes, cells across the northern transition band (dashed: band edges)" % (4 * r, r))


if __name__ == "__main__":
    g, m, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    fig_scaling(g, m, out)
    fig_profiles(g, m, out)
    fig_cells(g, m, out, 60)
