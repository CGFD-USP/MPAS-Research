#!/usr/bin/env python3
"""
oisst_clim_to_intermediate.py — build MPAS SST/sea-ice update files from the
NOAA OISST daily *climatology* (long-term mean, 1991-2020), for use as a
climatological lower boundary in forecasts / idealized runs where there is no
observed SST for the target dates (e.g. a forecast into the future, or a run
representing a "typical" month).

For each target date it picks the matching day-of-year from the climatology and
writes an `SST:YYYY-MM-DD_HH` intermediate (fields SST, SEAICE, LANDSEA) tagged
with that target date — exactly like the observed pipeline, so the rest of the
SST-update workflow (init_atmosphere config_init_case=8) is identical.

The 0.25° daily climatology is read on demand over OPeNDAP (only the needed
day-of-year slices are fetched, a few MB each), so there is no multi-GB download.
Source: NOAA PSL (https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html).

Run inside the conda env that has xarray (with OPeNDAP) + pywinter:
    conda run -n cgfd-usp-mpas python oisst_clim_to_intermediate.py \
        --start 2026-07-01 --end 2026-07-31 [--hour 00] [--outdir <dir>]
"""

import argparse
import calendar
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr
import pywinter.winter as pw

PSL = "https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres"
SST_LTM = f"{PSL}/sst.day.mean.ltm.1991-2020.nc"
ICE_LTM = f"{PSL}/icec.day.mean.ltm.1991-2020.nc"
LAND_SST_FILL_K = 273.15


def clim_index(d) -> int:
    """0-based index into a 365-day (non-leap) day-of-year climatology.
    Feb 29 maps to Feb 28; later leap-year days are shifted back by one."""
    doy = d.timetuple().tm_yday
    if calendar.isleap(d.year) and doy >= 60:
        doy = 59 if doy == 60 else doy - 1
    return doy - 1


def main() -> int:
    ap = argparse.ArgumentParser(description="OISST daily climatology -> WPS SST: files.")
    ap.add_argument("--start", required=True, help="First target date, YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="Last target date (default: = start)")
    ap.add_argument("--hour", default="00", help="Hour tag HH for the daily field (default 00)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: $MPAS_ROOT/met_data/oisst_clim)")
    ap.add_argument("--prefix", default="SST", help="Intermediate prefix (config_sfc_prefix)")
    ap.add_argument("--sst-url", default=SST_LTM, help="Override SST climatology URL/path")
    ap.add_argument("--ice-url", default=ICE_LTM, help="Override sea-ice climatology URL/path")
    args = ap.parse_args()

    try:
        d0 = datetime.strptime(args.start, "%Y-%m-%d").date()
        d1 = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else d0
    except ValueError:
        print("[ERROR] dates must be YYYY-MM-DD", file=sys.stderr)
        return 2
    if d1 < d0:
        print("[ERROR] --end is before --start", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[3]
    outdir = Path(args.outdir) if args.outdir else repo_root / "met_data" / "oisst_clim"
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Opening OISST climatology (OPeNDAP): {args.sst_url}")
    try:
        sst_ds = xr.open_dataset(args.sst_url, decode_times=False)
        ice_ds = xr.open_dataset(args.ice_url, decode_times=False)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] could not open climatology: {e}", file=sys.stderr)
        return 1
    sst_var = "sst" if "sst" in sst_ds else list(sst_ds.data_vars)[0]
    ice_var = "icec" if "icec" in ice_ds else list(ice_ds.data_vars)[0]

    lat = sst_ds["lat"].values
    lon = sst_ds["lon"].values
    flip = lat[0] > lat[-1]
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    geo = pw.Geo0(float(min(lat)), float(min(lon)), dlat, dlon)

    def arr2d(a):
        a = np.asarray(a, dtype="float32")
        return a[::-1, :] if flip else a

    n, d = 0, d0
    while d <= d1:
        idx = clim_index(d)
        sst_c = np.asarray(sst_ds[sst_var].isel(time=idx).values, dtype="float64")
        ice_c = np.asarray(ice_ds[ice_var].isel(time=idx).values, dtype="float64")
        land = ~np.isfinite(sst_c)
        sst_k = np.where(land, LAND_SST_FILL_K, sst_c + 273.15)
        seaice = np.nan_to_num(ice_c, nan=0.0)
        landsea = land.astype("float32")
        variables = [
            pw.V2d("SST", arr2d(sst_k)),
            pw.V2d("SEAICE", arr2d(seaice)),
            pw.V2d("LANDSEA", arr2d(landsea)),
        ]
        date_tag = f"{d.isoformat()}_{args.hour.zfill(2)}"
        pw.cinter(args.prefix, date_tag, geo, variables, str(outdir) + "/")
        out = outdir / f"{args.prefix}:{date_tag}"
        if out.exists():
            print(f"[OK] {out.name} (clim day-of-year idx {idx + 1})")
            n += 1
        else:
            print(f"[ERROR] expected output not found: {out}", file=sys.stderr)
        d += timedelta(days=1)

    print(f"[OK] wrote {n} climatological {args.prefix}: file(s) -> {outdir}")
    print(f"[INFO] Next: run init_atmosphere config_init_case=8 with "
          f"config_sfc_prefix='{args.prefix}' (see README 'SST / sea-ice update').")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
