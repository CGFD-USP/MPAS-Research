#!/usr/bin/env python
"""Figures for the uniform JIGSAW meshes against NCAR's x1 meshes, and optimised against raw refined meshes.

  python plot_uniform_meshes.py <MPAS-Research meshes folder> <figure folder>

Reads meshes/uniform/{ncar/x1.<n>,uniform-<r>,uniform-cvt-<r>} and meshes/tropical-ref/tropical-*[-opt]
(quality json and npz of check_mesh_quality.py), and writes uniform_*.png and refined_opt_*.png.
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_refined_meshes import WIDTH, centres, colors  # noqa: E402  (also sets the style)

SPACING = (480, 240, 120, 60)
NCAR_CELLS = {480: 2562, 240: 10242, 120: 40962, 60: 163842}
SERIES = (("ncar", "NCAR x1 (SCVT)", "#3d3d3a", "o"), ("raw", "JIGSAW, odt+dqdx", "#d95f02", "s"),
          ("cvt", "JIGSAW, cvt+dqdx", "#1b9e77", "^"))


def path(root, kind, r):
    sub, name = {"ncar": ("ncar/x1.%d" % NCAR_CELLS[r], "x1.%d" % NCAR_CELLS[r]),
                 "raw": ("uniform-%d" % r,) * 2, "cvt": ("uniform-cvt-%d" % r,) * 2}[kind]
    return os.path.join(root, "uniform", sub, name + ".quality")


def load(prefix):
    return json.load(open(prefix + ".json")), np.load(prefix + ".npz")


def fig_scaling(root, out):
    fig, ax = plt.subplots(1, 3, figsize=(WIDTH, 2.8), constrained_layout=True)
    for kind, label, c, mk in SERIES:
        sc = [load(path(root, kind, r))[0] for r in SPACING]
        n = [s["nCells"] for s in sc]
        for a, key in zip(ax, ("eps_rms", "eps_max", "eps_gt_0.01_share")):
            a.loglog(n, [s["edge_point"][key] for s in sc], mk + "-", color=c, label=label)
    n = np.array([2562, 163842.0])
    ax[0].loglog(n, 0.0127 * (n / 2562) ** -0.5, "--", color="gray", label="slope -1/2")
    for a, t in zip(ax, ("rms of $\\varepsilon$", "max of $\\varepsilon$", "share of edges with $\\varepsilon>0.01$")):
        a.set_xlabel("number of cells")
        a.set_title(t)
    ax[0].legend()
    fig.suptitle("Uniform meshes, nominal spacing 480, 240, 120 and 60 km. Edge-point offset $\\varepsilon$")
    fig.savefig(os.path.join(out, "uniform_eps.png"))
    plt.close(fig)


def fig_lat(root, out):
    fig, ax = plt.subplots(1, 4, figsize=(WIDTH, 2.6), sharey=True, constrained_layout=True)
    for a, r in zip(ax, SPACING):
        for kind, label, c, mk in SERIES:
            sc, arr = load(path(root, kind, r))
            a.semilogy(centres(arr["lat_bins"]), np.maximum(arr["eps_lat"][:, 0], 1e-5), color=c, label=label)
        a.set_title("%d km" % r)
        a.set_xlabel("latitude (deg)")
    ax[0].set_ylabel("rms of $\\varepsilon$ per degree")
    ax[0].legend()
    fig.suptitle("Uniform meshes, edge-point offset $\\varepsilon$ against latitude")
    fig.savefig(os.path.join(out, "uniform_eps_lat.png"))
    plt.close(fig)


def fig_angles(root, out):
    fig, ax = plt.subplots(1, 4, figsize=(WIDTH, 2.6), sharey=True, constrained_layout=True)
    for a, r in zip(ax, SPACING):
        for kind, label, c, mk in SERIES:
            sc, arr = load(path(root, kind, r))
            h = arr["angle_max_hist"]
            a.plot(centres(arr["angle_bins"]), h / h.sum() / np.diff(arr["angle_bins"])[0], color=c, label=label)
        a.set_xlim(58, 92)
        a.set_title("%d km" % r)
        a.set_xlabel("largest angle (deg)")
    ax[0].set_ylabel("share of triangles per degree")
    ax[0].legend()
    fig.suptitle("Uniform meshes, largest angle of each triangle of the cell centres")
    fig.savefig(os.path.join(out, "uniform_angles.png"))
    plt.close(fig)


def fig_counts(root, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 2.8), constrained_layout=True)
    for kind, label, c, mk in SERIES:
        sc = [load(path(root, kind, r))[0] for r in SPACING]
        ax[0].loglog([s["nCells"] for s in sc],
                     [100 * (1 - s["nEdgesOnCell"].get("6", 0) / s["nCells"]) for s in sc], mk + "-", color=c, label=label)
        s = load(path(root, kind, 240))[0]
        k = np.arange(4, 9)
        ax[1].plot(k, [100 * s["nEdgesOnCell"].get(str(i), 0) / s["nCells"] for i in k], mk + "-", color=c, label=label)
    ax[0].set_xlabel("number of cells")
    ax[0].set_ylabel("cells that are not hexagons (%)")
    ax[1].set_yscale("symlog", linthresh=0.1)
    ax[1].set_xlabel("edges of the cell")
    ax[1].set_ylabel("share of cells (%)")
    ax[1].set_title("240 km meshes")
    ax[0].legend()
    fig.suptitle("Uniform meshes, cell shapes")
    fig.savefig(os.path.join(out, "uniform_counts.png"))
    plt.close(fig)


def fig_refined(root, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 2.8), sharey=True, constrained_layout=True)
    ncar = json.load(open(os.path.join(root, "tropical-ref", "ncar_reference", "ncar.json")))
    for a, (fam, title) in zip(ax, (("tropical", "family (a), fixed transition width"),
                                    ("tropical-fixcells", "family (b), transition scaled with the spacing"))):
        for suffix, label, c, mk in (("", "JIGSAW, odt+dqdx", "#d95f02", "s"), ("-opt", "JIGSAW, cvt+dqdx", "#1b9e77", "^")):
            fine, rms = [], []
            for r in (120, 60, 30, 15):
                p = os.path.join(root, "tropical-ref", "%s-%g-%gkm%s" % (fam, 4 * r, r, suffix), "")
                f = p + os.path.basename(p[:-1]) + ".quality.json"
                if os.path.exists(f):
                    fine.append(r)
                    rms.append(json.load(open(f))["edge_point"]["eps_rms"])
            a.loglog(fine, rms, mk + "-", color=c, label=label)
        a.loglog([15], [ncar["edge_point"]["eps_rms"]], "o", color="#3d3d3a", label="NCAR x4.1572866")
        a.set_title(title)
        a.set_xlabel("fine spacing (km)")
        a.set_xticks([15, 30, 60, 120], ["15", "30", "60", "120"])
        a.minorticks_off()
    ax[0].set_ylabel("rms of $\\varepsilon$")
    ax[0].legend()
    fig.suptitle("Tropical refined meshes (coarse = 4 x fine), edge-point offset")
    fig.savefig(os.path.join(out, "refined_opt_eps.png"))
    plt.close(fig)


if __name__ == "__main__":
    root, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    for f in (fig_scaling, fig_lat, fig_angles, fig_counts, fig_refined):
        f(root, out)
