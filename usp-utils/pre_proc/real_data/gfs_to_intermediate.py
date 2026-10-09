#!/usr/bin/env python3
"""
gfs_to_intermediate.py — convert a GFS GRIB2 file (from download_gfs.py) into a
WPS intermediate-format file (e.g. GFS:2024-09-10_00) that MPAS init_atmosphere
reads for real-data initialization (config_met_prefix='GFS').

Uses cfgrib (to read the GRIB) and pywinter (to write the WPS intermediate
format) — no need to build WPS/ungrib.

Run inside the conda env that has cfgrib + pywinter:
    conda run -n cgfd-usp-mpas python gfs_to_intermediate.py --grib <file.f000>
                                       [--outdir <dir>]

The GFS grid is global regular lat/lon, stored N->S; the latitude axis is
flipped to S->N so the intermediate file starts at the SW corner, as WPS expects.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import pywinter.winter as pw

# 3D isobaric fields: GRIB shortName -> intermediate name
ISOBARIC = {"gh": "GHT", "t": "TT", "u": "UU", "v": "VV", "r": "RH"}
# 2D surface fields (typeOfLevel='surface'): shortName -> intermediate name
SURFACE = {"sp": "PSFC", "orog": "SOILHGT", "t": "SKINTEMP",
           "sdwe": "SNOW", "lsm": "LANDSEA", "siconc": "SEAICE"}
# Soil layers (depthBelowLandLayer tops, m) -> WPS depth tag (top-bottom, cm)
SOIL_TAGS = ["000010", "010040", "040100", "100200"]


def _open(grib, **keys):
    return xr.open_dataset(
        grib, engine="cfgrib",
        backend_kwargs={"filter_by_keys": keys, "indexpath": ""},
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="GFS GRIB -> WPS intermediate (pywinter).")
    ap.add_argument("--grib", required=True, help="GFS GRIB2 file (e.g. *.f000)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir for the intermediate file "
                         "(default: the GRIB's directory)")
    ap.add_argument("--prefix", default="GFS", help="Intermediate prefix (config_met_prefix)")
    args = ap.parse_args()

    grib = Path(args.grib)
    if not grib.exists():
        print(f"[ERROR] not found: {grib}", file=sys.stderr)
        return 1
    outdir = Path(args.outdir) if args.outdir else grib.parent
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading {grib}")
    iso = _open(grib, typeOfLevel="isobaricInhPa")
    sfc = _open(grib, typeOfLevel="surface")
    msl = _open(grib, typeOfLevel="meanSea")
    soil = _open(grib, typeOfLevel="depthBelowLandLayer")

    # Grid geometry (flip latitude to ascending = S->N, SW-corner start)
    lat = iso.latitude.values
    lon = iso.longitude.values
    flip = lat[0] > lat[-1]
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    geo = pw.Geo0(float(min(lat)), float(min(lon)), dlat, dlon)

    def arr2d(da):
        a = np.asarray(da.values, dtype="float32")
        return a[::-1, :] if flip else a

    def arr3d(da):
        a = np.asarray(da.values, dtype="float32")
        return a[:, ::-1, :] if flip else a

    variables = []

    # --- 3D isobaric ---
    plevs_hpa = np.asarray(iso.isobaricInhPa.values, dtype="float32")  # hPa
    plevs = plevs_hpa * 100.0  # WPS intermediate / pywinter V3dp expect pressure in Pa
    print(f"[INFO] {plevs.size} isobaric levels ({int(plevs_hpa.max())}..{int(plevs_hpa.min())} hPa)"
          f" -> set config_nfglevels = {plevs.size + 1}")
    for sn, name in ISOBARIC.items():
        if sn in iso:
            variables.append(pw.V3dp(name, arr3d(iso[sn]), plevs))
        else:
            print(f"[WARN] isobaric field missing: {sn}")

    # --- 2D surface + mean sea level ---
    for sn, name in SURFACE.items():
        if sn in sfc:
            variables.append(pw.V2d(name, arr2d(sfc[sn])))
        else:
            print(f"[WARN] surface field missing: {sn}")
    if "prmsl" in msl:
        variables.append(pw.V2d("PMSL", arr2d(msl["prmsl"])))

    # --- Soil layers (pywinter Vsl: name 'ST'/'SM' + numeric-string level tags
    #     -> intermediate fields ST000010, SM000010, ...) ---
    if "st" in soil:
        variables.append(pw.Vsl("ST", arr3d(soil["st"]), SOIL_TAGS))
    if "soilw" in soil:
        variables.append(pw.Vsl("SM", arr3d(soil["soilw"]), SOIL_TAGS))

    # Date tag (YYYY-MM-DD_HH) from the analysis valid time
    vt = pd.to_datetime(np.atleast_1d(iso.valid_time.values)[0])
    date_tag = vt.strftime("%Y-%m-%d_%H")

    print(f"[INFO] Writing {len(variables)} fields -> {outdir}/{args.prefix}:{date_tag}")
    pw.cinter(args.prefix, date_tag, geo, variables, str(outdir) + "/")

    out = outdir / f"{args.prefix}:{date_tag}"
    if out.exists():
        print(f"[OK] {out} ({out.stat().st_size/1e6:.1f} MB)")
        print(f"[INFO] Link it in the run dir and set config_met_prefix='{args.prefix}', "
              f"config_start_time='{date_tag}:00:00'")
        return 0
    print(f"[ERROR] expected output not found: {out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
