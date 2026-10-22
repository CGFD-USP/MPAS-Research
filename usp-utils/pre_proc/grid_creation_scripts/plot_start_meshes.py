#!/usr/bin/env python
"""Figures for the tropical meshes that JIGSAW makes from starting point sets, against the frontal-Delaunay
family (a) and NCAR's x4.1572866.

  python plot_start_meshes.py <MPAS-Research meshes folder> <figure folder>

Reads meshes/tropical-ref/tropical-<coarse>-<fine>km[-rings|-icos|-geo] (quality json and npz of
check_mesh_quality.py) and writes start_scaling.png, start_eps_lat.png, start_angles.png, start_spacing.png.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_refined_meshes import WIDTH, centres  # noqa: E402  (also sets the style)

FINE = (120, 60, 30, 15)
SERIES = (("", "frontal Delaunay (family a)", "#d95f02", "s"), ("-rings", "start: latitude rings", "#7570b3", "v"),
          ("-icos", "start: bisected icosahedron", "#1b9e77", "^"), ("-geo", "start: icosahedral lattices", "#e6ab02", "D"))
NCAR = ("NCAR x4.1572866 (SCVT)", "#3d3d3a")


def prefix(root, suffix, r):
    name = "tropical-%g-%gkm%s" % (4 * r, r, suffix)
    return os.path.join(root, "tropical-ref", name, name + ".quality")


def load(p):
    return json.load(open(p + ".json")), np.load(p + ".npz")


def ncar(root):
    return load(os.path.join(root, "tropical-ref", "ncar_reference", "ncar"))


def available(root, suffix):
    return [r for r in FINE if os.path.exists(prefix(root, suffix, r) + ".json")]


def fig_scaling(root, out):
    nc = ncar(root)[0]
    keys = (("eps rms", lambda s: s["edge_point"]["eps_rms"], "rms of $\\varepsilon$"),
            ("non-hex", lambda s: 100 * (1 - s["nEdgesOnCell"].get("6", 0) / s["nCells"]), "cells that are not hexagons (%)"),
            ("spacing", lambda s: s["spacing_minus_design"]["rms"], "rms of (spacing / design $- 1$)"))
    fig, ax = plt.subplots(1, 3, figsize=(WIDTH, 3.3), constrained_layout=True)
    for suffix, label, c, mk in SERIES:
        rs = available(root, suffix)
        sc = [load(prefix(root, suffix, r))[0] for r in rs]
        for a, (_, f, _) in zip(ax, keys):
            a.loglog(rs, [f(s) for s in sc], mk + "-", color=c, label=label)
    for a, (_, f, t) in zip(ax, keys):
        a.loglog([15], [f(nc)], "o", color=NCAR[1], label=NCAR[0])
        a.set_xlabel("fine spacing (km)")
        a.set_title(t)
        a.set_xticks(FINE, [str(r) for r in FINE])
        a.minorticks_off()
    fig.legend(*ax[0].get_legend_handles_labels(), loc="outside lower center", ncol=3)
    fig.suptitle("Tropical meshes (coarse = 4 x fine)")
    fig.savefig(os.path.join(out, "start_scaling.png"))
    plt.close(fig)


def fig_lat(root, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.3), sharey=True, constrained_layout=True)
    for a, r in zip(ax, (30, 15)):
        for suffix, label, c, mk in SERIES:
            _, arr = load(prefix(root, suffix, r))
            a.semilogy(centres(arr["lat_bins"]), np.maximum(arr["eps_lat"][:, 0], 1e-5), color=c, label=label)
        if r == 15:
            _, arr = ncar(root)
            a.semilogy(centres(arr["lat_bins"]), np.maximum(arr["eps_lat"][:, 0], 1e-5), color=NCAR[1], label=NCAR[0])
        a.set_title("%g-%g km meshes" % (4 * r, r))
        a.set_xlabel("latitude (deg)")
    ax[0].set_ylabel("rms of $\\varepsilon$ per degree")
    fig.legend(*ax[1].get_legend_handles_labels(), loc="outside lower center", ncol=3)
    fig.suptitle("Tropical meshes, edge-point offset $\\varepsilon$ against latitude")
    fig.savefig(os.path.join(out, "start_eps_lat.png"))
    plt.close(fig)


def fig_hist(root, out, name, key, bins, xlim, xlabel, title):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.3), sharey=True, constrained_layout=True)
    for a, rr in zip(ax, (30, 15)):
        for suffix, label, c, mk in SERIES:
            if rr in available(root, suffix):
                _, arr = load(prefix(root, suffix, rr))
                h = arr[key]
                a.plot(centres(arr[bins]), h / h.sum() / np.diff(arr[bins])[0], color=c, label=label)
        if rr == 15:
            _, arr = ncar(root)
            h = arr[key]
            a.plot(centres(arr[bins]), h / h.sum() / np.diff(arr[bins])[0], color=NCAR[1], label=NCAR[0])
        a.set_xlim(*xlim)
        a.set_xlabel(xlabel)
        a.set_title("%g-%g km meshes" % (4 * rr, rr))
    ax[0].set_ylabel("share of %s per unit" % ("cells" if key == "dev_hist" else "triangles"))
    fig.legend(*ax[1].get_legend_handles_labels(), loc="outside lower center", ncol=3)
    fig.suptitle(title)
    fig.savefig(os.path.join(out, name))
    plt.close(fig)


if __name__ == "__main__":
    root, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    fig_scaling(root, out)
    fig_lat(root, out)
    fig_hist(root, out, "start_angles.png", "angle_max_hist", "angle_bins", (58, 92), "largest angle (deg)",
             "Largest angle of each triangle of the cell centres")
    fig_hist(root, out, "start_spacing.png", "dev_hist", "dev_bins", (-0.3, 0.3), "cell spacing over design $- 1$",
             "Realised cell spacing against the design")
