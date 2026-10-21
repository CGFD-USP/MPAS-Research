#!/usr/bin/env python
"""Markdown table of the quality and log json files of the meshes under the given folders.

  python summarize_meshes.py <folder or mesh folder>... [--sort eps]

A mesh folder holds <name>.quality.json (check_mesh_quality.py) and <name>.log.json
(create_tropical_refined_grid.py), written by the grid scripts.
"""
import argparse
import glob
import json
import os


def rows(paths):
    for p in paths:
        for q in sorted(glob.glob(os.path.join(p, "*", "*.quality.json")) + glob.glob(os.path.join(p, "*.quality.json"))):
            s = json.load(open(q))
            lg = q.replace(".quality.json", ".log.json")
            lg = json.load(open(lg)) if os.path.exists(lg) else {}
            e, nec = s["edge_point"], s["nEdgesOnCell"]
            yield {"mesh": q.split(os.sep)[-2], "cells": s["nCells"], "time_s": lg.get("jigsaw_s", float("nan")),
                   "eps_max": e["eps_max"], "eps_rms": e["eps_rms"], "eps>0.01 (%)": 100 * e["eps_gt_0.01_share"],
                   "non-hex (%)": 100 * (1 - nec.get("6", 0) / s["nCells"]), "max angle": s["angle_max"],
                   "obtuse": s["obtuse"], "max ratio": s["neighbour_ratio"]["max"],
                   "ordering Q": s["ordering"]["Q"]}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+")
    a = p.parse_args()
    r = list(rows(a.paths))
    keys = list(r[0])
    print("| " + " | ".join(keys) + " |\n|" + "---|" * len(keys))
    for x in r:
        print("| " + " | ".join(x[k] if isinstance(x[k], str) else ("%d" % x[k] if isinstance(x[k], int) else "%.4g" % x[k]) for k in keys) + " |")
