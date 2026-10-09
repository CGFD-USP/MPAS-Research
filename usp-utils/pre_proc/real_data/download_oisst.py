#!/usr/bin/env python3
"""
download_oisst.py — fetch NOAA OISST v2.1 (AVHRR) daily 0.25 deg SST + sea-ice
NetCDF from NCEI, for building MPAS SST/sea-ice update files.

OISST is the daily 0.25 deg optimum-interpolation SST analysis (Sep 1981 ->
present); it is the recommended lower-boundary SST for the scientific /
downscaling pipeline (ERA5 atmosphere + OISST SST). The downloaded files are
turned into WPS intermediate `SST:` files by oisst_to_intermediate.py, then fed
to init_atmosphere config_init_case=8 (see the README "SST / sea-ice update").

Each daily file (oisst-avhrr-v02r01.YYYYMMDD.nc) holds: sst (degC), ice
(fraction), anom, err on a 1440x720 global 0.25 deg grid. Files in the last
~2 weeks are served with a `_preliminary` suffix; this script falls back to it.

Usage:
    python download_oisst.py --start 2014-09-01 [--end 2014-09-15] [--outdir <dir>]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OISST_BASE = ("https://www.ncei.noaa.gov/data/"
              "sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr")
OISST_START = date(1981, 9, 1)
_UA = {"User-Agent": "MPAS-Research/usp-utils (research)"}


def _urls(d: date):
    ym = d.strftime("%Y%m")
    ymd = d.strftime("%Y%m%d")
    final = f"{OISST_BASE}/{ym}/oisst-avhrr-v02r01.{ymd}.nc"
    prelim = f"{OISST_BASE}/{ym}/oisst-avhrr-v02r01.{ymd}_preliminary.nc"
    return final, prelim


def _fetch_to(url, dest) -> bool:
    """Stream url to dest. Return True on success, False on 404."""
    import shutil
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Download OISST v2.1 daily SST for MPAS SST update.")
    ap.add_argument("--start", required=True, help="First date, YYYY-MM-DD (UTC)")
    ap.add_argument("--end", default=None, help="Last date, YYYY-MM-DD (default: = start)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: $MPAS_ROOT/met_data/oisst)")
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
    if d0 < OISST_START:
        print(f"[ERROR] OISST v2.1 starts {OISST_START.isoformat()}.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[3]
    outdir = Path(args.outdir) if args.outdir else repo_root / "met_data" / "oisst"
    outdir.mkdir(parents=True, exist_ok=True)

    files, d = [], d0
    while d <= d1:
        final, prelim = _urls(d)
        name = Path(final).name
        dest = outdir / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[OK] {name} already present — skipping")
            files.append(str(dest))
            d += timedelta(days=1)
            continue
        print(f"[INFO] {d.isoformat()} -> {dest}")
        try:
            if _fetch_to(final, dest):
                files.append(str(dest))
            else:
                # fall back to the preliminary file (recent dates)
                pdest = outdir / Path(prelim).name
                if _fetch_to(prelim, pdest):
                    print(f"[INFO]   using preliminary file for {d.isoformat()}")
                    files.append(str(pdest))
                else:
                    print(f"[WARN]   no OISST file for {d.isoformat()} (final or preliminary)",
                          file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] download failed for {d.isoformat()}: {e}", file=sys.stderr)
            return 1
        d += timedelta(days=1)

    if not files:
        print("[ERROR] no files downloaded", file=sys.stderr)
        return 1

    meta = {
        "dataset": "OISST",
        "product": "NOAA OI SST v2.1 (AVHRR), daily 0.25 deg",
        "source": "NCEI",
        "base_url": OISST_BASE,
        "period": {"start": d0.isoformat(), "end": d1.isoformat()},
        "variables_used": ["sst (degC)", "ice (fraction)"],
        "files": files,
        "download_date": datetime.now(timezone.utc).isoformat(),
    }
    (outdir / f"oisst_{d0.strftime('%Y%m%d')}_{d1.strftime('%Y%m%d')}.provenance.json"
     ).write_text(json.dumps(meta, indent=2))
    print(f"[OK] {len(files)} OISST file(s) in {outdir}")
    print(f"[INFO] Next: python oisst_to_intermediate.py --indir {outdir} "
          f"--start {d0.isoformat()} --end {d1.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
