#!/usr/bin/env python3
"""
gfs_sst_to_intermediate.py — extract SST / sea-ice / land-sea mask from a GFS
GRIB2 file (the same file download_gfs.py already fetches for the atmosphere)
and write a WPS intermediate `SST:YYYY-MM-DD_HH` file for MPAS SST/sea-ice
updates. This is the operational counterpart of oisst_to_intermediate.py.

The three fields MPAS expects for an SST update come from the GFS surface
records already in the GRIB:
    TMP:surface  -> SST     (skin temperature; over water this is SST, and
                             init_atmosphere masks land via LANDSEA)
    ICEC:surface -> SEAICE  (sea-ice fraction)
    LAND:surface -> LANDSEA (land-sea mask, 1 = land, 0 = water)

Feed the resulting `SST:` files to init_atmosphere with config_init_case=8
(see the README "SST / sea-ice update").

Run inside the conda env that has cfgrib + pywinter:
    conda run -n cgfd-usp-mpas python gfs_sst_to_intermediate.py --grib <file.f000>
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import pywinter.winter as pw


def _open(grib, **keys):
    return xr.open_dataset(
        grib, engine="cfgrib",
        backend_kwargs={"filter_by_keys": keys, "indexpath": ""},
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="GFS GRIB -> WPS intermediate SST: file.")
    ap.add_argument("--grib", required=True, help="GFS GRIB2 file (e.g. *.f000)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: the GRIB's directory)")
    ap.add_argument("--prefix", default="SST", help="Intermediate prefix (config_sfc_prefix)")
    args = ap.parse_args()

    grib = Path(args.grib)
    if not grib.exists():
        print(f"[ERROR] not found: {grib}", file=sys.stderr)
        return 1
    outdir = Path(args.outdir) if args.outdir else grib.parent
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading surface fields from {grib}")
    sfc = _open(grib, typeOfLevel="surface")

    lat = sfc.latitude.values
    lon = sfc.longitude.values
    flip = lat[0] > lat[-1]
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    geo = pw.Geo0(float(min(lat)), float(min(lon)), dlat, dlon)

    def arr2d(da):
        a = np.asarray(da.values, dtype="float32")
        return a[::-1, :] if flip else a

    # GFS surface shortNames: t (skin temp), siconc (sea ice), lsm (land mask)
    mapping = {"t": "SST", "siconc": "SEAICE", "lsm": "LANDSEA"}
    variables, added = [], set()
    for sn, name in mapping.items():
        if sn in sfc:
            variables.append(pw.V2d(name, arr2d(sfc[sn])))
            added.add(name)
        else:
            print(f"[WARN] surface field missing: {sn} (-> {name})", file=sys.stderr)
    if "SST" not in added:
        print("[ERROR] no surface temperature (SST) in the GRIB — cannot build SST file.",
              file=sys.stderr)
        return 1

    vt = pd.to_datetime(np.atleast_1d(sfc.valid_time.values)[0])
    date_tag = vt.strftime("%Y-%m-%d_%H")

    print(f"[INFO] Writing {len(variables)} fields -> {outdir}/{args.prefix}:{date_tag}")
    pw.cinter(args.prefix, date_tag, geo, variables, str(outdir) + "/")
    out = outdir / f"{args.prefix}:{date_tag}"
    if out.exists():
        print(f"[OK] {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
        print(f"[INFO] Next: run init_atmosphere config_init_case=8 with "
              f"config_sfc_prefix='{args.prefix}' (see README 'SST / sea-ice update').")
        return 0
    print(f"[ERROR] expected output not found: {out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
