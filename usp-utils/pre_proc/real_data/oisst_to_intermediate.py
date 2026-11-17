#!/usr/bin/env python3
"""
oisst_to_intermediate.py — convert NOAA OISST v2.1 daily NetCDF (from
download_oisst.py) into WPS intermediate `SST:YYYY-MM-DD_HH` files for MPAS
SST/sea-ice updates.

Each daily OISST file becomes one intermediate file with the three 2D fields
MPAS expects for an SST update (SST, SEAICE, LANDSEA). Feed the resulting
`SST:` files to init_atmosphere with config_init_case=8 (see the README
"SST / sea-ice update").

Run inside the conda env that has xarray + pywinter:
    conda run -n cgfd-usp-mpas python oisst_to_intermediate.py --indir <dir> \
        [--start YYYY-MM-DD --end YYYY-MM-DD] [--hour 00]

OISST specifics handled here:
- sst is in degC -> converted to Kelvin (+273.15); land (missing sst) is filled
  with a constant and masked by LANDSEA.
- ice is a 0-1 fraction -> SEAICE.
- LANDSEA is derived from the sst mask (1 = land, 0 = water), as OISST has no
  separate mask variable in the daily file.
- The grid is global 0.25 deg; latitude is flipped to ascending (S->N) if needed.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr
import pywinter.winter as pw

LAND_SST_FILL_K = 273.15  # finite filler over land; ignored via LANDSEA


def _date_from_name(p: Path):
    """Parse YYYYMMDD out of oisst-avhrr-v02r01.YYYYMMDD[...].nc."""
    digits = "".join(c for c in p.stem.split(".")[-1] if c.isdigit())[:8]
    return datetime.strptime(digits, "%Y%m%d").date()


def convert_one(path: Path, outdir: Path, prefix: str, hour: str) -> bool:
    ds = xr.open_dataset(path)
    sst = ds["sst"].isel(time=0, zlev=0)        # degC, NaN over land
    ice = ds["ice"].isel(time=0, zlev=0)        # fraction, NaN over land
    lat = sst["lat"].values
    lon = sst["lon"].values
    flip = lat[0] > lat[-1]
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    geo = pw.Geo0(float(min(lat)), float(min(lon)), dlat, dlon)

    def arr2d(a):
        a = np.asarray(a, dtype="float32")
        return a[::-1, :] if flip else a

    sst_v = sst.values
    land = ~np.isfinite(sst_v)                  # land where sst is missing
    sst_k = np.where(land, LAND_SST_FILL_K, sst_v + 273.15)
    seaice = np.nan_to_num(ice.values, nan=0.0)
    landsea = land.astype("float32")            # 1 = land, 0 = water

    variables = [
        pw.V2d("SST", arr2d(sst_k)),
        pw.V2d("SEAICE", arr2d(seaice)),
        pw.V2d("LANDSEA", arr2d(landsea)),
    ]
    date_tag = f"{_date_from_name(path).isoformat()}_{hour}"
    pw.cinter(prefix, date_tag, geo, variables, str(outdir) + "/")
    out = outdir / f"{prefix}:{date_tag}"
    if out.exists():
        print(f"[OK] {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
        return True
    print(f"[ERROR] expected output not found: {out}", file=sys.stderr)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="OISST NetCDF -> WPS intermediate SST: files.")
    ap.add_argument("--indir", required=True, help="Directory with oisst-*.nc files")
    ap.add_argument("--start", default=None, help="First date YYYY-MM-DD (default: all files)")
    ap.add_argument("--end", default=None, help="Last date YYYY-MM-DD")
    ap.add_argument("--outdir", default=None, help="Output dir (default: --indir)")
    ap.add_argument("--hour", default="00", help="Hour tag HH for the daily field (default 00)")
    ap.add_argument("--prefix", default="SST", help="Intermediate prefix (config_sfc_prefix)")
    args = ap.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir) if args.outdir else indir
    outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(indir.glob("oisst-avhrr-v02r01.*.nc"))
    if args.start:
        d0 = datetime.strptime(args.start, "%Y-%m-%d").date()
        d1 = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else d0
        files = [f for f in files if d0 <= _date_from_name(f) <= d1]
    if not files:
        print(f"[ERROR] no OISST files found in {indir} for the requested range",
              file=sys.stderr)
        return 1

    n = 0
    for f in files:
        print(f"[INFO] {f.name}")
        if convert_one(f, outdir, args.prefix, args.hour.zfill(2)):
            n += 1
    print(f"[OK] wrote {n} {args.prefix}: intermediate file(s) -> {outdir}")
    print(f"[INFO] Next: run init_atmosphere config_init_case=8 with "
          f"config_sfc_prefix='{args.prefix}' (see README 'SST / sea-ice update').")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
