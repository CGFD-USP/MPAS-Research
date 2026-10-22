#!/usr/bin/env python
"""Markdown table of the quality and log json files of the meshes under the given folders.

  python summarize_meshes.py <folder or mesh folder>... [--full]

A mesh folder holds <name>.quality.json (check_mesh_quality.py) and <name>.log.json
(create_tropical_refined_grid.py), written by the grid scripts.
"""
import argparse
import glob
import json
import os


def rows(paths, full=False):
    nan = float("nan")
    for p in paths:
        for q in sorted(glob.glob(os.path.join(p, "*", "*.quality.json")) + glob.glob(os.path.join(p, "*.quality.json"))):
            s = json.load(open(q))
            lg = q.replace(".quality.json", ".log.json")
            lg = json.load(open(lg)) if os.path.exists(lg) else {}
            e, nec = s["edge_point"], s["nEdgesOnCell"]
            row = {"mesh": os.path.basename(q)[:-len(".quality.json")], "cells": s["nCells"], "time_s": lg.get("jigsaw_s", nan)}
            if full:
                row.update({"eps_rms": e["eps_rms"], "eps_rms_band": e["eps_rms_in_transition"],
                            "eps_rms_outside": e["eps_rms_outside_transition"], "eps_max": e["eps_max"]})
            else:
                row.update({"eps_max": e["eps_max"], "eps_rms": e["eps_rms"]})
            row.update({"eps>0.01 (%)": 100 * e["eps_gt_0.01_share"], "non-hex (%)": 100 * (1 - nec.get("6", 0) / s["nCells"]),
                        "max angle": s["angle_max"]})
            if full:
                row.update({"min angle": s["angle_min"], "centroid offset rms": s.get("centroid_offset", {}).get("rms", nan),
                            "spacing/design rms": s["spacing_minus_design"]["rms"]})
            row.update({"obtuse": s["obtuse"], "max ratio": s["neighbour_ratio"]["max"], "ordering Q": s["ordering"]["Q"]})
            yield row


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+")
    p.add_argument("--full", action="store_true", help="more columns: eps in and outside the band, minimum angle, "
                   "generator-to-centroid offset, spacing against design")
    a = p.parse_args()
    r = list(rows(a.paths, a.full))
    keys = list(r[0])
    print("| " + " | ".join(keys) + " |\n|" + "---|" * len(keys))
    for x in r:
        print("| " + " | ".join(x[k] if isinstance(x[k], str) else ("%d" % x[k] if isinstance(x[k], int) else "%.4g" % x[k]) for k in keys) + " |")
