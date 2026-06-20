#!/usr/bin/env python3
"""
era5_to_intermediate.py — convert ERA5 GRIB files (from download_era5.py) into a
WPS intermediate-format file (e.g. GFS:2014-09-10_00) that MPAS init_atmosphere
reads for real-data initialization (config_met_prefix='GFS').

This is the ERA5 counterpart of gfs_to_intermediate.py (same pywinter output,
same intermediate field names), for dates the GFS archive does not cover.

Run inside the conda env that has cfgrib + pywinter:
    conda run -n cgfd-usp-mpas python era5_to_intermediate.py \
        --pl era5_pl_YYYYMMDDHH.grib --sl era5_sl_YYYYMMDDHH.grib

ERA5 specifics handled here:
- Geopotential (z, m^2/s^2) is divided by g0=9.80665 to get height (GHT/SOILHGT, m).
- Snow depth (sd, m of water equivalent) is scaled to kg m-2 (SNOW) by *1000.
- Pressure levels are written in Pa (WPS requirement; see the units note in README).
- Latitude is flipped to ascending (S->N), as WPS expects (SW-corner start).
- Soil layers use the ERA5 depths (0-7, 7-28, 28-100, 100-289 cm).

NOTE: this converter mirrors the validated GFS path but the ERA5 branch has not
yet been validated end-to-end here — verify the resulting init.nc with the
sanity check in the README before running the model.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import pywinter.winter as pw

G0 = 9.80665  # standard gravity (m s-2), for geopotential -> height

# 3D isobaric: cfgrib shortName -> (intermediate name, transform or None)
ISOBARIC = {
    "z": ("GHT", lambda a: a / G0),
    "t": ("TT", None),
    "u": ("UU", None),
    "v": ("VV", None),
    "r": ("RH", None),
}
# 2D surface (typeOfLevel='surface'): shortName -> (intermediate name, transform)
SURFACE = {
    "sp": ("PSFC", None),
    "skt": ("SKINTEMP", None),
    "z": ("SOILHGT", lambda a: a / G0),
    "lsm": ("LANDSEA", None),
    "siconc": ("SEAICE", None),
    "sd": ("SNOW", lambda a: a * 1000.0),  # m w.e. -> kg m-2
}
# Soil layers: ERA5 shortNames and the matching WPS depth tags (top-bottom, cm)
SOIL_T = ["stl1", "stl2", "stl3", "stl4"]
SOIL_M = ["swvl1", "swvl2", "swvl3", "swvl4"]
SOIL_TAGS = ["000007", "007028", "028100", "100289"]


def _open(path, **keys):
    return xr.open_dataset(
        path, engine="cfgrib",
        backend_kwargs={"filter_by_keys": keys, "indexpath": ""},
    )


def _open_var(path, sn, **keys):
    """Open a single variable by shortName; return the DataArray or None."""
    try:
        ds = _open(path, shortName=sn, **keys)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] could not read {sn}: {e}")
        return None
    return ds[sn] if sn in ds else None


def main() -> int:
    ap = argparse.ArgumentParser(description="ERA5 GRIB -> WPS intermediate (pywinter).")
    ap.add_argument("--pl", required=True, help="ERA5 pressure-level GRIB file")
    ap.add_argument("--sl", required=True, help="ERA5 single-level GRIB file")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: the --pl file's directory)")
    ap.add_argument("--prefix", default="GFS",
                    help="Intermediate prefix (config_met_prefix; keep 'GFS')")
    args = ap.parse_args()

    pl, sl = Path(args.pl), Path(args.sl)
    for f in (pl, sl):
        if not f.exists():
            print(f"[ERROR] not found: {f}", file=sys.stderr)
            return 1
    outdir = Path(args.outdir) if args.outdir else pl.parent
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading {pl} (pressure levels)")
    iso = _open(pl, typeOfLevel="isobaricInhPa")

    # Grid geometry (flip latitude to ascending = S->N, SW-corner start)
    lat = iso.latitude.values
    lon = iso.longitude.values
    flip = lat[0] > lat[-1]
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    geo = pw.Geo0(float(min(lat)), float(min(lon)), dlat, dlon)

    def arr2d(a):
        a = np.asarray(a, dtype="float32")
        return a[::-1, :] if flip else a

    def arr3d(a):
        a = np.asarray(a, dtype="float32")
        return a[:, ::-1, :] if flip else a

    variables = []

    # --- 3D isobaric ---
    plevs_hpa = np.asarray(iso.isobaricInhPa.values, dtype="float32")  # hPa
    plevs = plevs_hpa * 100.0  # WPS intermediate / pywinter V3dp expect Pa
    print(f"[INFO] {plevs.size} isobaric levels ({int(plevs_hpa.max())}..{int(plevs_hpa.min())} hPa)"
          f" -> set config_nfglevels = {plevs.size + 1}")
    for sn, (name, fn) in ISOBARIC.items():
        if sn in iso:
            a = arr3d(iso[sn].values)
            variables.append(pw.V3dp(name, fn(a) if fn else a, plevs))
        else:
            print(f"[WARN] isobaric field missing: {sn}")

    # --- 2D surface (open each var individually to avoid cfgrib hypercube clashes) ---
    print(f"[INFO] Reading {sl} (single levels)")
    for sn, (name, fn) in SURFACE.items():
        da = _open_var(sl, sn, typeOfLevel="surface")
        if da is not None:
            a = arr2d(da.values)
            variables.append(pw.V2d(name, fn(a) if fn else a))
        else:
            print(f"[WARN] surface field missing: {sn}")
    msl = _open_var(sl, "msl", typeOfLevel="meanSea")
    if msl is not None:
        variables.append(pw.V2d("PMSL", arr2d(msl.values)))
    else:
        print("[WARN] surface field missing: msl")

    # --- Soil layers (stack the 4 ERA5 layers; pywinter Vsl -> ST/SM<tag>) ---
    st = [_open_var(sl, s, typeOfLevel="depthBelowLandLayer") for s in SOIL_T]
    sm = [_open_var(sl, s, typeOfLevel="depthBelowLandLayer") for s in SOIL_M]
    if all(x is not None for x in st):
        variables.append(pw.Vsl("ST", np.stack([arr2d(x.values) for x in st]), SOIL_TAGS))
    else:
        print("[WARN] soil temperature layers incomplete — skipping ST")
    if all(x is not None for x in sm):
        variables.append(pw.Vsl("SM", np.stack([arr2d(x.values) for x in sm]), SOIL_TAGS))
    else:
        print("[WARN] soil moisture layers incomplete — skipping SM")

    # Date tag (YYYY-MM-DD_HH) from the analysis valid time
    t = iso.valid_time.values if "valid_time" in iso else iso.time.values
    vt = pd.to_datetime(np.atleast_1d(t)[0])
    date_tag = vt.strftime("%Y-%m-%d_%H")

    print(f"[INFO] Writing {len(variables)} fields -> {outdir}/{args.prefix}:{date_tag}")
    pw.cinter(args.prefix, date_tag, geo, variables, str(outdir) + "/")

    out = outdir / f"{args.prefix}:{date_tag}"
    if out.exists():
        print(f"[OK] {out} ({out.stat().st_size / 1e6:.1f} MB)")
        print(f"[INFO] Link it in the run dir and set config_met_prefix='{args.prefix}', "
              f"config_start_time='{date_tag}:00:00'")
        print("[INFO] Verify the init.nc with the sanity check in the README before "
              "running the model.")
        return 0
    print(f"[ERROR] expected output not found: {out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
