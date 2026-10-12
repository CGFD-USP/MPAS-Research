"""Summary of the baroclinic wave runs under a root of run_jw.sh: status, cost,
whether the custom operators were read, ranges of the final state, and
differences of cell fields (area-weighted l2, relative to the reference norm)
against the reference run of each comparison.
Usage: bash usp-utils/install/container/run.sh python3 check_runs.py <root>
"""
import glob
import os
import re
import sys

import netCDF4
import numpy as np

root = sys.argv[1]


def info(rdir):
    lines = open(os.path.join(rdir, "RUN_INFO")).read().splitlines()
    return {l[:11].strip(): l[11:].strip() for l in lines}


def final(rdir, prefix):
    files = sorted(glob.glob(os.path.join(rdir, prefix + ".*.nc")))
    return netCDF4.Dataset(files[-1]) if files else None


def sfc_pressure(h, zgrid):
    """Surface pressure from the two lowest levels, as the MPAS physics interface computes it."""
    p, rho = h["pressure"][0], h["rho"][0]
    dz1, dz2 = zgrid[:, 1] - zgrid[:, 0], zgrid[:, 2] - zgrid[:, 1]
    rho1, rho2 = rho[:, 0], rho[:, 1]
    return p[:, 0] + 0.5 * 9.80616 * dz1 * (rho1 - 0.5 * (rho2 - rho1) * dz1 / (dz1 + dz2))


def field(h, v, init):
    return sfc_pressure(h, init["zgrid"][:]) if v == "ps" else h[v][0]


def mesh(run_dir):
    """init.nc of a run, opened once."""
    path = os.path.join(os.path.dirname(run_dir), "init", "init.nc")
    if path not in inits:
        inits[path] = netCDF4.Dataset(path)
    return inits[path]


def l2(a, b, area):
    """Area-weighted l2 norm of a - b over the l2 norm of b, columns summed over levels."""
    w = area.reshape((-1,) + (1,) * (a.ndim - 1))
    return np.sqrt(np.sum(w * (a - b) ** 2) / np.sum(w * b ** 2))


runs = sorted(glob.glob(os.path.join(root, "*", "*_L*", "*_np*")))
runs = [r for r in runs if os.path.isfile(os.path.join(r, "RUN_INFO"))]
inits = {}
print(f"{'run':52s} {'status':6s} {'wall':>5s} {'us/pt':>6s} {'ops':4s} {'warn':>4s} "
      f"{'max|u|':>7s} {'ps min':>8s} {'ps max':>8s} {'max|vor850|':>11s}")
for r in runs:
    name = os.path.relpath(r, root)
    i = info(r)
    status, wall = i.get("status", "missing"), i.get("wall", "0 s").split()[0]
    log = open(os.path.join(r, "log.atmosphere.0000.out")).read()
    read_ops = "reading dimensions from stream 'custom_operators'" in log
    wants_ops = i["operators"] != "none"
    ops = ("yes" if read_ops else "no") + ("" if read_ops == wants_ops else "!")
    warn = re.search(r"Warning messages =\s+(\d+)", log)
    timer = re.search(r"\d+\s+time integration\s+([\d.]+)\s+(\d+)", log)
    h, d = final(r, "history"), final(r, "diag")
    if status != "ok" or h is None:
        print(f"{name:52s} {status:6s} {wall:>5s}")
        continue
    ncells, nlev = h.dimensions["nCells"].size, h.dimensions["nVertLevels"].size
    ranks = int(name.rsplit("_np", 1)[1])
    cost = float(timer.group(1)) / int(timer.group(2)) * ranks / (ncells * nlev) * 1e6
    finite = all(np.all(np.isfinite(h[v][:])) for v in h.variables if h[v].dtype.kind == "f")
    u = np.hypot(h["uReconstructZonal"][:], h["uReconstructMeridional"][:])
    ps = sfc_pressure(h, mesh(r)["zgrid"][:])
    vor = np.abs(d["vorticity_850hPa"][:]).max() if d is not None else np.nan
    print(f"{name:52s} {status if finite else 'nan':6s} {wall:>5s} {cost:6.2f} {ops:4s} "
          f"{warn.group(1) if warn else '?':>4s} {np.abs(u).max():7.3f} {ps.min():8.1f} "
          f"{ps.max():8.1f} {vor:11.3e}")

# comparisons: (run, reference) pairs present under the root
pairs = []
for r in runs:
    case_dir, run = os.path.split(r)
    config, ranks = run.rsplit("_np", 1)
    mesh_dir, case = os.path.split(case_dir)
    if config != "trsk":
        pairs.append((r, os.path.join(case_dir, f"trsk_np{ranks}")))
    if ranks == "1":
        pairs.append((r, os.path.join(case_dir, f"{config}_np" + "*")))
    if mesh_dir.endswith("-ncar"):
        pairs.append((r, os.path.join(mesh_dir[: -len("-ncar")], case, run)))
print(f"\n{'run':52s} {'reference':40s} {'l2 ps':>9s} {'l2 uZonal':>9s} {'l2 theta':>9s}")
for r, ref in pairs:
    refs = [x for x in glob.glob(ref) if x != r and os.path.isfile(os.path.join(x, "RUN_INFO"))]
    if not refs:
        continue
    ref = refs[0]
    a, b = final(r, "history"), final(ref, "history")
    if a is None or b is None:
        continue
    ia, ib = mesh(r), mesh(ref)
    e = [l2(field(a, v, ia), field(b, v, ib), ib["areaCell"][:]) for v in ("ps", "uReconstructZonal", "theta")]
    print(f"{os.path.relpath(r, root):52s} {os.path.relpath(ref, root):40s} "
          + " ".join(f"{x:9.2e}" for x in e))

# steady state: departure of the final state from the initial one
steady = [r for r in runs if "/steady_L" in r]
if steady:
    print(f"\n{'steady run':52s} {'l2 ps-ps0':>9s} {'l2 uZ-uZ0':>9s}")
for r in steady:
    a = final(r, "history")
    files = sorted(glob.glob(os.path.join(r, "history.*.nc")))
    b = netCDF4.Dataset(files[0])
    i = mesh(r)
    print(f"{os.path.relpath(r, root):52s} "
          + " ".join(f"{l2(field(a, v, i), field(b, v, i), i['areaCell'][:]):9.2e}" for v in ("ps", "uReconstructZonal")))
