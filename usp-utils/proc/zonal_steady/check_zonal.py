"""Errors of the steady zonal flow runs under the roots of run_zonal.sh.

Writes <first root>/errors.csv, one line per run, output time and field, with the
l2 (weighted rms) and maximum errors of u (normal velocity at edges), w, theta,
rho, pressure and the surface pressure against two references:
  init   the initial state of the run (the discrete steady state), and
  exact  the analytic solution sampled as init case 11 samples it (u: mean
         normal velocity over the dual edge, cell fields: point values at the
         cell centre and the layer mid height).
Prints, per initial state, the residual of the discrete hydrostatic balance and
the difference between u and the point normal velocity at the edge, and per
case, configuration and level count the errors at one time against resolution
with the observed orders between successive meshes.
With --rate the table gives the errors divided by the elapsed time (per second),
e.g. the initial tendency after one short step (run_zonal.sh step=<s>).
Usage: bash usp-utils/install/container/run.sh python3 check_zonal.py <root> [<root> ...] [--day D] [--rate]
"""
import argparse
import glob
import math
import os

import netCDF4
import numpy as np

# constants of MPAS (mpas_constants.F) and of init case 11
G, RGAS, OMEGA = 9.80616, 287.0, 7.29212e-5
CP = 3.5 * RGAS
P0 = 1.0e5
T0, P_EQ, PERIOD = 300.0, 1.0e5, 12 * 86400.0
FIELDS = ["u", "w", "theta", "rho", "pressure", "ps"]

ap = argparse.ArgumentParser()
ap.add_argument("roots", nargs="+")
ap.add_argument("--day", type=float, help="time of the convergence table (default: the last common output)")
ap.add_argument("--rate", action="store_true", help="errors divided by the elapsed time in the table")
args = ap.parse_args()


def dx_km(mesh):
    n = int(mesh.split(".")[1].split("-")[0])
    return 480 * math.sqrt(2560 / (n - 2))


class Init:
    """Geometry, weights and exact state of one init.nc."""

    def __init__(self, path):
        d = netCDF4.Dataset(path)

        def g(v):
            x = np.ma.getdata(d[v][:])
            return x[0] if d[v].dimensions[0] == "Time" else x

        a = d.sphere_radius
        self.zgrid = g("zgrid")
        zmid = 0.5 * (self.zgrid[:, 1:] + self.zgrid[:, :-1])
        dz = self.zgrid[:, 1:] - self.zgrid[:, :-1]
        area = g("areaCell")
        self.wc = area[:, None] * dz
        dze = 0.5 * (dz[g("cellsOnEdge")[:, 0] - 1] + dz[g("cellsOnEdge")[:, 1] - 1])
        self.we = (0.5 * g("dcEdge") * g("dvEdge"))[:, None] * dze
        self.ww = area[:, None] * (zmid[:, 1:] - zmid[:, :-1])
        self.rdzw, self.rdzu = g("rdzw"), g("rdzu")
        self.fzm, self.fzp, self.zz = g("fzm"), g("fzp"), g("zz")
        u0 = 2 * math.pi * a / PERIOD
        b = (a * OMEGA * u0 + 0.5 * u0 ** 2) / (RGAS * T0)
        lat_v = g("latVertex")
        v1, v2 = (g("verticesOnEdge") - 1).T
        nlev = dz.shape[1]
        ue = u0 * a * (np.sin(lat_v[v2]) - np.sin(lat_v[v1])) / g("dvEdge")
        s2 = np.sin(g("latCell"))[:, None] ** 2
        p = P_EQ * np.exp(-b * s2 - G * zmid / (RGAS * T0))
        self.exact = {
            "u": np.repeat(ue[:, None], nlev, axis=1),
            "w": np.zeros_like(self.ww[:, :1].repeat(nlev + 1, axis=1)),
            "theta": T0 * (P0 / p) ** (RGAS / CP),
            "rho": p / (RGAS * T0),
            "pressure": p,
            "ps": P_EQ * np.exp(-b * s2[:, 0]),
        }
        upoint = u0 * np.cos(g("latEdge")) * np.cos(g("angleEdge"))
        self.u_point = np.max(np.abs(ue - upoint)) / u0
        self.u_init = np.max(np.abs(g("u") - self.exact["u"])) / u0
        # residual of the solver's vertical balance, rdzu dp'/dz + g (fzm rho' + fzp rho'), on the levels
        gamma = CP / (CP - RGAS)
        eos = lambda rho, theta: P0 * (RGAS * rho * theta / P0) ** gamma
        rb = g("rho_base")
        pp = eos(g("rho"), g("theta")) - eos(rb * self.zz, g("theta_base"))
        rr = g("rho") / self.zz - rb
        res = self.rdzu[1:] * (pp[:, 1:] - pp[:, :-1]) + G * (self.fzm[1:] * rr[:, 1:] + self.fzp[1:] * rr[:, :-1])
        self.balance = np.max(np.abs(res)) / np.max(np.abs(G * rr))
        d.close()

    def ps(self, pressure, rho):
        """Surface pressure from the lowest two layers, as decouple_variables of init_atmosphere."""
        rzz = rho / self.zz
        return pressure[:, 0] + 0.5 * G / self.rdzw[0] * (1.25 * rzz[:, 0] - 0.25 * rzz[:, 1])

    def weight(self, f):
        return {"u": self.we, "w": self.ww}.get(f, self.wc)


def state(path, ini):
    d = netCDF4.Dataset(path)
    s = {f: d[f][0].data for f in ["u", "w", "theta", "rho", "pressure"]}
    d.close()
    s["ps"] = ini.ps(s["pressure"], s["rho"])
    s["w"] = s["w"][:, 1:-1]
    return s


def norms(e, w):
    if e.ndim == 1:
        w = w[:, 0]
    return math.sqrt(np.sum(w * e ** 2) / np.sum(w)), float(np.max(np.abs(e)))


runs = []
for root in args.roots:
    runs += sorted(p for p in glob.glob(os.path.join(root, "*", "*_L*", "*_np*")) if os.path.isfile(os.path.join(p, "RUN_INFO")))
inits, rows = {}, []
for r in runs:
    files = sorted(glob.glob(os.path.join(r, "history.*.nc")))
    if not files:
        continue
    ipath = os.path.realpath(os.path.join(r, "init.nc"))
    if ipath not in inits:
        inits[ipath] = Init(ipath)
    ini = inits[ipath]
    ini.exact_w = ini.exact["w"][:, 1:-1]
    case_dir, run_dir = r.split(os.sep)[-2:]
    mesh = r.split(os.sep)[-3]
    case, levels = case_dir.rsplit("_L", 1)
    config, ranks = run_dir.rsplit("_np", 1)
    first = state(files[0], ini)
    for fpath in files:
        d = netCDF4.Dataset(fpath)
        day = float(d["xtime"][0].tobytes().decode().strip()[8:10]) - 1
        hms = d["xtime"][0].tobytes().decode().strip()[11:19].split(":")
        day += (int(hms[0]) * 3600 + int(hms[1]) * 60 + int(hms[2])) / 86400
        d.close()
        s = first if fpath == files[0] else state(fpath, ini)
        for f in FIELDS:
            ex = ini.exact_w if f == "w" else ini.exact[f]
            for ref, val in (("init", first[f]), ("exact", ex)):
                l2, linf = norms(s[f] - val, ini.weight(f) if f != "w" else ini.ww)
                rows.append((os.path.relpath(r, os.path.dirname(os.path.dirname(os.path.dirname(r)))), mesh,
                             dx_km(mesh), case, int(levels), config, int(ranks), day, f, ref, l2, linf))

out = os.path.join(args.roots[0], "errors.csv")
with open(out, "w") as fh:
    fh.write("run,mesh,dx_km,case,levels,config,ranks,day,field,ref,l2,linf\n")
    for row in rows:
        fh.write(",".join(f"{x:.6e}" if isinstance(x, float) else str(x) for x in row) + "\n")
print(f"{len(rows)} lines in {out}\n")

print("initial states: residual of the vertical balance (relative to max |g rho'|), u against the")
print("exact mean over the dual edge and against the point normal velocity at the edge (relative to u0)")
for p, ini in inits.items():
    print(f"  {os.path.relpath(p, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(p))))):45s}"
          f" balance {ini.balance:.1e}  u-exact {ini.u_init:.1e}  mean-point {ini.u_point:.1e}")

# errors against resolution at one time, per case, grid family, configuration and level count
groups = {}
for row in rows:
    grid = "NCAR grids" if row[1].endswith("-ncar") else "regenerated meshes"
    groups.setdefault((row[3], row[5], row[4], grid, row[9]), []).append(row)
for key in sorted(groups):
    g = groups[key]
    days = sorted({row[7] for row in g})
    meshes = sorted({row[1] for row in g}, key=dx_km, reverse=True)
    common = [t for t in days if all(any(r[1] == m and r[7] == t for r in g) for m in meshes)]
    day = args.day if args.day is not None else (common[-1] if common else days[-1])
    scale = 1 / (day * 86400) if args.rate and day > 0 else 1
    print(f"\n{key[0]} L{key[2]} {key[1]} on {key[3]}, against {key[4]}, day {day:g}: l2 / max"
          f"{' per second' if scale != 1 else ''}, observed orders")
    print(f"  {'mesh':12s}{'dx':>6s} " + "".join(f"{f:>22s}" for f in FIELDS))
    prev = None
    for m in meshes:
        e = {}
        for f in FIELDS:
            hit = [r for r in g if r[1] == m and r[8] == f and abs(r[7] - day) < 1e-6]
            e[f] = (hit[0][10] * scale, hit[0][11] * scale) if hit else None
        line = f"  {m:12s}{dx_km(m):6.0f} " + "".join(
            f"{e[f][0]:11.2e}{e[f][1]:11.2e}" if e[f] else f"{'':22s}" for f in FIELDS)
        print(line)
        if prev and prev[1] is not None:
            ratio = math.log(prev[0] / dx_km(m))
            orders = []
            for f in FIELDS:
                a, b = prev[1].get(f), e[f]
                if a and b and min(a + b) > 0:
                    orders.append(f"{math.log(a[0] / b[0]) / ratio:11.2f}{math.log(a[1] / b[1]) / ratio:11.2f}")
                else:
                    orders.append(f"{'':22s}")
            print(f"  {'order':18s} " + "".join(orders))
        prev = (dx_km(m), e)
