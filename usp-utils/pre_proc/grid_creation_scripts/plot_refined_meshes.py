#!/usr/bin/env python
"""Figures comparing the tropically refined meshes with the NCAR 60-15 km mesh.

  python plot_refined_meshes.py <mesh folder> <figure folder>

<mesh folder> holds the mesh folders of create_tropical_refined_grid.py (each with its
<name>.quality.json and .npz from check_mesh_quality.py) and ncar_reference/ncar.json and .npz.
"""
import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_tropical_refined_grid import EARTH_RADIUS_KM, WIDTH, cell_width  # noqa: E402

WIDTH = 7.0  # inches, drawn and saved at this width
INK, GRID = "#3d3d3a", "#e4e3dd"
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Latin Modern Roman", "DejaVu Serif"], "mathtext.fontset": "cm",
    "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 1.3, "savefig.dpi": 200,
})
NCAR_FINE = 15.0


FAMILIES = {"fixed": ("tropical-[0-9]*", "fixed transition width", ""),
            "fixcells": ("tropical-fixcells-*", "transition scaled with the spacing", "fixcells_")}


def load(folder, family="fixed"):
    """List of (name, label, fine km, scalars, arrays), coarse to fine, then the NCAR mesh."""
    meshes = []
    for js in glob.glob(os.path.join(folder, FAMILIES[family][0], "*.quality.json")):
        sc = json.load(open(js))
        name = os.path.basename(js).split(".quality")[0]
        coarse, fine = (float(v) for v in name.replace("fixcells-", "")[len("tropical-"):-len("km")].split("-"))
        meshes.append((name, "%g-%g km" % (coarse, fine), fine, sc, np.load(js[:-5] + ".npz")))
    meshes.sort(key=lambda m: -m[2])
    ref = os.path.join(folder, "ncar_reference", "ncar")
    ncar = ("ncar", "NCAR x4.1572866, 60-15 km", NCAR_FINE, json.load(open(ref + ".json")), np.load(ref + ".npz"))
    return meshes, ncar


FAMILY, PREFIX = "", ""


def suptitle(fig, text):
    fig.suptitle(text + ("\n(%s)" % FAMILY if FAMILY else ""))


def colors(n):
    return plt.cm.viridis(np.linspace(0.0, 0.85, n))


def centres(b):
    return 0.5 * (b[1:] + b[:-1])


def save(fig, folder, name):
    fig.savefig(os.path.join(folder, PREFIX + name), dpi=200)
    plt.close(fig)


def fig_profile(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    lat = centres(ncar[4]["lat_bins"])
    for (name, label, fine, sc, arr), c in zip(meshes, colors(len(meshes))):
        m = arr["lat_profile"][:, 2]
        ax[0].plot(lat, m, color=c, label=label)
        ax[1].plot(lat, m / fine, color=c, label=label)
    m = ncar[4]["lat_profile"][:, 2]
    for a, scale in zip(ax, (1.0, NCAR_FINE)):
        a.plot(lat, m / scale, "k--", label=ncar[1])
    for k, widths in enumerate(sorted({m[3].get("width_deg", WIDTH) for m in meshes})):
        ax[1].plot(lat, cell_width(lat, 1.0, width=widths), color="0.55", lw=3, alpha=0.5, zorder=0,
                   label="design $h(\\varphi)$" if k == 0 else None)
    ax[0].set_yscale("log")
    ax[0].set_ylabel("median cell spacing per 1$^\\circ$ band (km)")
    ax[1].set_ylabel("cell spacing over fine spacing")
    ax[0].set_title("Cell spacing, all levels", loc="left")
    ax[1].set_title("Scaled by the fine spacing", loc="left")
    for a in ax:
        a.set_xlabel("latitude (degrees)")
        a.set_xlim(-90, 90)
    ax[1].legend(loc="center", frameon=False)
    suptitle(fig, "Tropical refinement, resolution against latitude (spacing = mean dcEdge of the cell)")
    save(fig, out, "profile.png")


def fig_gradient(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    lat = centres(ncar[4]["lat_bins"])
    km_deg = np.radians(1.0) * EARTH_RADIUS_KM
    for (name, label, fine, sc, arr), c in zip(meshes, colors(len(meshes))):
        h = arr["lat_profile"][:, 2]
        ax[0].plot(lat, np.abs(np.gradient(h, lat)) / km_deg, color=c, label=label)
        ax[1].plot(lat, np.abs(np.gradient(np.log(h), lat)) / km_deg * fine, color=c, label=label)
    h = ncar[4]["lat_profile"][:, 2]
    ax[0].plot(lat, np.abs(np.gradient(h, lat)) / km_deg, "k--", label=ncar[1])
    ax[1].plot(lat, np.abs(np.gradient(np.log(h), lat)) / km_deg * NCAR_FINE, "k--", label=ncar[1])
    ax[0].set_ylabel("$|dh/ds|$ of the band median (km per km)")
    ax[1].set_ylabel("$|d\\ln h/ds|$ times fine spacing (km)")
    ax[0].set_title("Spacing gradient along a meridian", loc="left")
    ax[1].set_title("Relative change per km, times fine spacing", loc="left")
    for a in ax:
        a.set_xlabel("latitude (degrees)")
        a.set_xlim(0, 70)
    ax[0].set_yscale("log")
    ax[0].set_ylim(1e-3, 1)
    ax[0].legend(frameon=False, loc="upper left")
    suptitle(fig, "Smoothness of the transition (northern hemisphere, 1$^\\circ$ band medians)")
    save(fig, out, "gradient.png")


def fig_maps(meshes, ncar, out):
    mine = [m for m in meshes if m[2] == NCAR_FINE]
    fig, ax = plt.subplots(2, 2, figsize=(WIDTH, 4.2), constrained_layout=True, sharex=True, sharey=True)
    for col, (label, arr) in enumerate(((ncar[1], ncar[4]), ("JIGSAW " + mine[0][1], mine[0][4]))):
        for row, (key, cmap, lim, text) in enumerate((("map_spacing", "viridis", (10, 60), "spacing (km)"),
                                                      ("map_deviation", "RdBu_r", (-0.2, 0.2),
                                                       "spacing over design minus 1"))):
            im = ax[row, col].imshow(arr[key], origin="lower", extent=(0, 360, -90, 90), aspect="auto",
                                     cmap=cmap, vmin=lim[0], vmax=lim[1])
            ax[row, col].grid(False)
            ax[row, col].set_title(label + (", spacing" if row == 0 else ", realised over design"),
                                   loc="left")
            fig.colorbar(im, ax=ax[row, col], label=text)
    for a in ax[1]:
        a.set_xlabel("longitude (degrees)")
    for a in ax[:, 0]:
        a.set_ylabel("latitude (degrees)")
    suptitle(fig, "Maps of cell spacing (mean of the cells in each 0.5$^\\circ$ box) for the 60-15 km meshes")
    save(fig, out, "maps.png")


def fig_angles(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    allm = list(zip(meshes, colors(len(meshes)))) + [(ncar, "k")]
    for (name, label, fine, sc, arr), c in allm:
        ls = "--" if name == "ncar" else "-"
        b = centres(arr["angle_bins"])
        ax[0].plot(b, arr["angle_hist"] / arr["angle_hist"].sum() / 0.25, ls, color=c, label=label)
        ax[1].plot(b, np.cumsum(arr["angle_max_hist"]) / arr["angle_max_hist"].sum(), ls, color=c, label=label)
    ax[0].axvline(90, color="0.4", lw=0.8)
    ax[1].axvline(90, color="0.4", lw=0.8)
    ax[0].set_yscale("log")
    ax[0].set_ylim(1e-6, 1)
    ax[0].set_xlim(30, 100)
    ax[1].set_xlim(60, 100)
    ax[0].set_xlabel("triangle angle (degrees)")
    ax[1].set_xlabel("largest angle of the triangle (degrees)")
    ax[0].set_ylabel("probability density (per degree)")
    ax[1].set_ylabel("share of triangles below the angle")
    ax[0].set_title("All angles of the Delaunay triangles", loc="left")
    ax[1].set_title("Largest angle, cumulative", loc="left")
    ax[0].legend(frameon=False, loc="upper right", fontsize=7)
    suptitle(fig, "Triangle angles of the Delaunay dual, grey line at 90$^\\circ$ (obtuse above)")
    save(fig, out, "angles.png")


def fig_ratio(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    allm = list(zip(meshes, colors(len(meshes)))) + [(ncar, "k")]
    for (name, label, fine, sc, arr), c in allm:
        ls = "--" if name == "ncar" else "-"
        ax[0].plot(centres(arr["ratio_bins"]), arr["ratio_hist"] / arr["ratio_hist"].sum(), ls, color=c, label=label)
        ax[1].plot(centres(arr["dev_bins"]) * 100, arr["dev_hist"] / arr["dev_hist"].sum() / 0.5, ls, color=c,
                   label=label)
    ax[0].set_yscale("log")
    ax[1].set_yscale("log")
    ax[1].set_xlim(-15, 15)
    ax[1].set_ylim(1e-6, 2)
    ax[0].set_xlabel("larger over smaller spacing of the two cells of an edge")
    ax[0].set_ylabel("share of edges per bin of 0.0025")
    ax[1].set_xlabel("realised spacing over design, minus 1 (%)")
    ax[1].set_ylabel("share of cells (per percent)")
    ax[0].set_title("Neighbouring cell spacing ratio", loc="left")
    ax[1].set_title("Deviation from the design spacing", loc="left")
    ax[0].legend(frameon=False)
    suptitle(fig, "Spacing of neighbouring cells and deviation from the design spacing")
    save(fig, out, "ratio.png")


def fig_counts(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    fine = np.array([m[2] for m in meshes])
    n = np.array([m[3]["nCells"] for m in meshes])
    ax[0].loglog(fine, n, "o-", color="C0", label="JIGSAW meshes")
    ax[0].loglog([NCAR_FINE], [ncar[3]["nCells"]], "k*", ms=9, label=ncar[1])
    ax[0].loglog(fine, n[np.argmin(abs(fine - NCAR_FINE))] * (NCAR_FINE / fine) ** 2, ":", color="0.4",
                 label="order $-2$ in the fine spacing")
    ax[0].set_xlabel("fine spacing, tropics (km)")
    ax[0].set_ylabel("number of cells")
    ax[0].set_title("Cell count of the hierarchy", loc="left")
    ax[0].legend(frameon=False)
    for (name, label, f, sc, arr), c in zip(meshes, colors(len(meshes))):
        ax[1].plot(f * np.ones(1), [sc["angle_max"]], "o", color=c, label=label)
    ax[1].axhline(ncar[3]["angle_max"], color="k", ls="--", label=ncar[1] + " (largest angle)")
    ax[1].axhline(90, color="0.4", lw=0.8)
    ax[1].set_xscale("log")
    for a in ax:
        a.set_xticks(fine)
        a.set_xticklabels(["%g" % f for f in fine])
        a.minorticks_off()
    ax[1].set_xlabel("fine spacing, tropics (km)")
    ax[1].set_ylabel("largest triangle angle (degrees)")
    ax[1].set_title("Largest triangle angle of each mesh", loc="left")
    ax[1].legend(frameon=False, fontsize=7)
    suptitle(fig, "Cell count and largest triangle angle of the hierarchy")
    save(fig, out, "counts.png")


def fig_eps(meshes, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 3.0), constrained_layout=True)
    lat = centres(ncar[4]["lat_bins"])
    allm = list(zip(meshes, colors(len(meshes)))) + [(ncar, "k")]
    for (name, label, fine, sc, arr), c in allm:
        ls = "--" if name == "ncar" else "-"
        ax[0].plot(lat, arr["eps_lat"][:, 0], ls, color=c, label=label)
        sp = centres(arr["eps_spacing_bins"])
        ok = arr["eps_vs_spacing"][:, 0] > 0
        ax[1].plot(sp[ok], arr["eps_vs_spacing"][ok, 1], ls, color=c, label=label)
    ax[0].set_yscale("log")
    ax[0].set_xlabel("latitude (degrees)")
    ax[0].set_ylabel("rms of $\\epsilon_e$ per 1$^\\circ$ band")
    ax[0].set_title("Edge-point offset against latitude", loc="left")
    ax[1].set_xscale("log")
    ax[1].set_yscale("log")
    ax[1].set_xlabel("edge length over fine spacing")
    ax[1].set_ylabel("rms of $\\epsilon_e$")
    ax[1].set_title("Edge-point offset against local resolution", loc="left")
    ax[0].set_ylim(1e-3, 1.0)
    ax[0].legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
    ax[1].set_xticks([1, 2, 3, 4])
    ax[1].set_xticklabels(["1", "2", "3", "4"])
    ax[1].minorticks_off()
    suptitle(fig, "Edge-point offset $\\epsilon_e = |x_t - x_m| / d_v$ (cell-arc midpoint to Voronoi-edge midpoint)")
    save(fig, out, "edge_point.png")


def fig_band(families, ncar, out):
    fig, ax = plt.subplots(1, 2, figsize=(WIDTH, 4.4), constrained_layout=True)
    rows = [(0, "design $\\max|dh/ds|$", lambda b: b["design_grad_max"], "o"),
            (0, "neighbour ratio $-1$, mean", lambda b: b["neighbour_ratio_minus_1_mean"], "s"),
            (0, "neighbour ratio $-1$, 99th percentile", lambda b: b["neighbour_ratio_minus_1_p99"], "^"),
            (1, "rms of $\\epsilon_e$", lambda b: b["eps_rms"], "o"),
            (1, "share of non-hexagonal cells", lambda b: b["non_hexagon_share"], "s"),
            (1, "std of cell area over hexagon area", lambda b: b["area_over_hexagon_std"], "^"),
            (1, "mean largest angle $-60^\\circ$ (rad)", lambda b: np.radians(b["max_angle_minus_60_mean"]), "d")]
    for k, (col, text, f, mk) in enumerate(rows):
        c = "C%d" % k
        for meshes, ls, _ in families:
            fine = np.array([m[2] for m in meshes])
            o = np.argsort(fine)
            ax[col].loglog(fine[o], np.array([f(m[3]["band"]) for m in meshes])[o], mk + ls, color=c,
                           label=text if ls == "-" else None)
        ax[col].loglog([NCAR_FINE], [f(ncar[3]["band"])], mk, mfc="none", mec="k", ms=8)
    ax[0].loglog([], [], "k-", label="fixed width in km (solid)")
    ax[0].loglog([], [], "k--", label="width scaled with spacing (dashed)")
    ax[0].loglog([], [], "ko", mfc="none", label="NCAR 60-15 km")
    allfine = np.unique([m[2] for meshes, _, _ in families for m in meshes])
    for a in ax:
        a.set_xticks(allfine)
        a.set_xticklabels(["%g" % f for f in allfine])
        a.minorticks_off()
        a.set_xlabel("fine spacing, tropics (km)")
    ax[0].set_ylabel("grading per cell")
    ax[1].set_ylabel("cell distortion")
    ax[0].set_title("Grading in the transition band", loc="left")
    ax[1].set_title("Distortion in the transition band", loc="left")
    for a in ax:
        a.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    fig.suptitle("Transition band of the two families of meshes, with the NCAR 60-15 km mesh")
    save(fig, out, "band.png")


if __name__ == "__main__":
    folder, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    loaded = {}
    for fam, (_, title, prefix) in FAMILIES.items():
        meshes, ncar = load(folder, fam)
        if not meshes:
            continue
        loaded[fam] = meshes
        FAMILY, PREFIX = (title, prefix) if prefix else ("", "")
        for f in (fig_profile, fig_gradient, fig_angles, fig_ratio, fig_counts, fig_eps):
            f(meshes, ncar, out)
        if fam == "fixed":
            fig_maps(meshes, ncar, out)
    FAMILY, PREFIX = "", ""
    fig_band([(loaded[f], "-" if f == "fixed" else "--", f) for f in loaded], ncar, out)
