#!/usr/bin/env python3
"""
download_gfs.py — fetch NCEP GFS (0.25 deg) fields needed to initialize MPAS.

Downloads only the variables/levels MPAS init_atmosphere needs (when the source
supports subsetting) and logs provenance. The downloaded GRIB2 is later turned
into the WPS intermediate format (consumed by init_atmosphere with
config_met_prefix='GFS') by gfs_to_intermediate.py.

Sources (--source) and their temporal coverage — GFS 0.25 deg:
  aws    : AWS Open Data (noaa-gfs-bdp-pds), byte-range subset via the .idx.
           No rate limit. Covers 2021-03-23 -> present (this script's
           gfs.YYYYMMDD/HH/atmos/ layout). DEFAULT.
  nomads : NOMADS grib_filter subset. Keeps only the most recent ~10 days; can
           hit 'Over Rate Limit'.
  rda    : NCAR RDA ds084.1 historical archive. Covers 2015-01-15 -> present
           (the earliest GFS 0.25 deg). Full files (no subset); may need a free
           RDA account (set RDA_API_TOKEN).

There is no GFS 0.25 deg before 2015-01-15. For older cases use a reanalysis
(see download_era5.py — ERA5 goes back to 1940). Out-of-range dates fail fast
with a message stating the limit.

Usage:
    python download_gfs.py --date 2024-09-10 --cycle 00 [--fhour 0]
                           [--res 0p25] [--source aws|nomads|rda] [--outdir <dir>]

Notes:
- GFS analysis = forecast hour 0 (default). For a forecast lead time, set --fhour.
"""

import argparse
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

# --- Temporal coverage of each source (GFS 0.25 deg) --------------------------
# AWS has this script's gfs.*/atmos/ layout from 2021-03-23 on; NCAR RDA ds084.1
# is the GFS 0.25 deg historical archive from 2015-01-15 (nothing earlier exists
# at 0.25 deg); NOMADS keeps only the most recent ~10 days.
AWS_START = date(2021, 3, 23)
RDA_START = date(2015, 1, 15)
NOMADS_DAYS = 10

# --- Fields MPAS needs from GFS (NOMADS grib_filter variable names) -----------
# 3D (on isobaric levels) + 2D surface / soil fields.
VARIABLES = [
    "HGT",    # geopotential height (-> GHT) ; also surface terrain
    "TMP",    # temperature (-> TT) ; also skin/2 m
    "UGRD",   # u-wind (-> UU) ; also 10 m
    "VGRD",   # v-wind (-> VV) ; also 10 m
    "RH",     # relative humidity (-> RH)
    "PRMSL",  # mean sea level pressure (-> PMSL)
    "PRES",   # surface pressure (-> PSFC)
    "LAND",   # land-sea mask (-> LANDSEA)
    "ICEC",   # sea-ice cover (-> SEAICE)
    "WEASD",  # water-equivalent snow depth (-> SNOW)
    "TSOIL",  # soil temperature (-> ST<layer>)
    "SOILW",  # volumetric soil moisture (-> SM<layer>)
]

# Full GFS isobaric set (hPa) for the 3D fields. Includes the upper levels
# (down to 1 hPa, ~48 km) so a 30 km model top has data to interpolate from.
# Levels absent from a given product are simply not returned; the converter
# reports the actual count to set config_nfglevels.
PRESSURE_LEVELS = [
    1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500,
    450, 400, 350, 300, 250, 200, 150, 100, 70, 50, 40, 30, 20, 15, 10,
    7, 5, 3, 2, 1,
]

# Non-isobaric levels (grib_filter checkbox names).
SURFACE_LEVELS = [
    "surface",
    "mean_sea_level",
    "2_m_above_ground",
    "10_m_above_ground",
    "0-0.1_m_below_ground",
    "0.1-0.4_m_below_ground",
    "0.4-1_m_below_ground",
    "1-2_m_below_ground",
]

NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin"
_UA = {"User-Agent": "MPAS-Research/usp-utils (research)"}


# Minimal field set for an SST/sea-ice update file (--fields sst): just the
# surface SST proxy + sea-ice + land mask.
SST_VARIABLES = ["TMP", "ICEC", "LAND"]
SST_SURFACE_LEVELS = ["surface"]


def build_filter_url(date: str, cycle: str, fhour: int, res: str,
                     fields: str = "full") -> tuple[str, str]:
    """Return (url, grib_filename) for the NOMADS grib_filter request."""
    ymd = date.replace("-", "")
    res_tag = {"0p25": "0p25", "0p50": "0p50", "1p00": "1p00"}[res]
    grib_name = f"gfs.t{cycle}z.pgrb2.{res_tag}.f{fhour:03d}"
    sst_only = fields == "sst"
    varis = SST_VARIABLES if sst_only else VARIABLES
    plevs = [] if sst_only else PRESSURE_LEVELS
    slevs = SST_SURFACE_LEVELS if sst_only else SURFACE_LEVELS
    params = [
        ("dir", f"/gfs.{ymd}/{cycle}/atmos"),
        ("file", grib_name),
    ]
    for v in varis:
        params.append((f"var_{v}", "on"))
    for p in plevs:
        params.append((f"lev_{p}_mb", "on"))
    for lv in slevs:
        params.append((f"lev_{lv}", "on"))
    url = f"{NOMADS}/filter_gfs_{res_tag}.pl?" + urllib.parse.urlencode(params)
    return url, grib_name


# --- AWS S3 source (no rate limit; byte-range subset via the .idx file) -------
AWS_BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
_IDX_3D = {"HGT", "TMP", "UGRD", "VGRD", "RH"}                  # all 'X mb' levels
_IDX_2D = {("PRMSL", "mean sea level"), ("PRES", "surface"), ("HGT", "surface"),
           ("TMP", "surface"), ("LAND", "surface"), ("ICEC", "surface"),
           ("WEASD", "surface")}
_IDX_SOIL = {"TSOIL", "SOILW"}                                  # any 'below ground'
# Surface messages for an SST/sea-ice update file (--fields sst)
_IDX_SST = {("TMP", "surface"), ("ICEC", "surface"), ("LAND", "surface")}


def _aws_urls(date, cycle, fhour, res):
    ymd = date.replace("-", "")
    base = f"{AWS_BUCKET}/gfs.{ymd}/{cycle}/atmos"
    name = f"gfs.t{cycle}z.pgrb2.{res}.f{fhour:03d}"
    return f"{base}/{name}", f"{base}/{name}.idx", name


def _get(url, rng=None, timeout=300):
    headers = dict(_UA)
    if rng:
        headers["Range"] = rng
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                timeout=timeout) as r:
        return r.read()


def fetch_aws(date, cycle, fhour, res, fields="full"):
    """Download only the MPAS-needed GFS messages from AWS S3 via the .idx
    (HTTP byte-range). Returns (grib_bytes, name). No rate limit.
    fields='sst' fetches only the surface SST/sea-ice/land messages."""
    grib_url, idx_url, name = _aws_urls(date, cycle, fhour, res)
    lines = [ln for ln in _get(idx_url, timeout=120).decode("utf-8", "replace").splitlines()
             if ln.strip()]
    starts = [int(ln.split(":")[1]) for ln in lines]
    sst_only = fields == "sst"
    sel = []
    for i, ln in enumerate(lines):
        p = ln.split(":")
        var, lev = p[3], p[4]
        if sst_only:
            keep = (var, lev) in _IDX_SST
        else:
            keep = ((var in _IDX_3D and lev.endswith("mb")) or ((var, lev) in _IDX_2D)
                    or (var in _IDX_SOIL and "below ground" in lev))
        if keep:
            sel.append((starts[i], starts[i + 1] - 1 if i + 1 < len(starts) else None))
    if not sel:
        raise RuntimeError("no matching messages in .idx")
    sel.sort()
    merged = [list(sel[0])]
    for s, e in sel[1:]:
        if merged[-1][1] is not None and s == merged[-1][1] + 1:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    chunks = [_get(grib_url, rng=f"bytes={s}-{'' if e is None else e}") for s, e in merged]
    return b"".join(chunks), name


# --- NCAR RDA ds084.1 source (historical GFS 0.25 deg, 2015-01-15+) -----------
# Full GRIB2 files (no byte-range subset); the converter reads only the fields it
# needs. Direct download from data.rda.ucar.edu; some access may require a free
# RDA account (https://rda.ucar.edu) — set RDA_API_TOKEN to send a bearer token.
RDA_BASE = "https://data.rda.ucar.edu/ds084.1"


def _rda_url(date, cycle, fhour):
    ymd = date.replace("-", "")
    name = f"gfs.0p25.{ymd}{cycle}.f{fhour:03d}.grib2"
    return f"{RDA_BASE}/{ymd[:4]}/{ymd}/{name}", name


def fetch_rda_to(dest, date, cycle, fhour):
    """Stream a full GFS 0.25 deg file from NCAR RDA ds084.1 to dest.
    Returns (url, name). Tries anonymous access; set RDA_API_TOKEN if RDA
    requires authentication."""
    url, name = _rda_url(date, cycle, fhour)
    headers = dict(_UA)
    tok = os.environ.get("RDA_API_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=900) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return url, name


def check_coverage(source: str, d: date) -> str | None:
    """Return an error message if date `d` is outside `source`'s coverage, else None."""
    today = datetime.now(timezone.utc).date()
    if source == "aws" and d < AWS_START:
        return (f"AWS GFS archive (gfs.*/atmos/ layout) starts {AWS_START.isoformat()}. "
                f"For {RDA_START.isoformat()}..{AWS_START.isoformat()} use --source rda; "
                f"for older dates use a reanalysis (download_era5.py).")
    if source == "rda" and d < RDA_START:
        return (f"GFS 0.25 deg only exists from {RDA_START.isoformat()} (NCAR RDA ds084.1); "
                f"nothing earlier exists at 0.25 deg. For older dates use a reanalysis "
                f"(download_era5.py — ERA5 goes back to 1940).")
    if source == "nomads" and (today - d).days > NOMADS_DAYS:
        return (f"NOMADS keeps only ~{NOMADS_DAYS} days (requested {(today - d).days} days ago). "
                f"Use --source aws ({AWS_START.isoformat()}+) or rda ({RDA_START.isoformat()}+), "
                f"or a reanalysis (download_era5.py) for older dates.")
    return None


SRC_LABEL = {
    "aws": "AWS S3 (noaa-gfs-bdp-pds, idx byte-range)",
    "nomads": "NOMADS grib_filter",
    "rda": "NCAR RDA ds084.1 (full file)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Download GFS fields for MPAS init.")
    ap.add_argument("--date", required=True, help="Cycle date, YYYY-MM-DD (UTC)")
    ap.add_argument("--cycle", default="00", choices=["00", "06", "12", "18"])
    ap.add_argument("--fhour", type=int, default=0, help="Forecast hour (0 = analysis)")
    ap.add_argument("--res", default="0p25", choices=["0p25", "0p50", "1p00"])
    ap.add_argument("--source", default="aws", choices=["aws", "nomads", "rda"],
                    help="aws = S3 byte-range subset (2021-03-23+, no rate limit, default); "
                         "nomads = grib_filter (~last 10 days); "
                         "rda = NCAR RDA ds084.1 historical (2015-01-15+, full files)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: $MPAS_ROOT/met_data/gfs/<date><cycle>)")
    ap.add_argument("--fields", default="full", choices=["full", "sst"],
                    help="full = all fields MPAS needs (default); "
                         "sst = only surface SST/sea-ice/land (small download, for "
                         "SST update files via gfs_sst_to_intermediate.py)")
    args = ap.parse_args()

    # Validate the date and that the chosen source actually covers it.
    try:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print("[ERROR] --date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    cov_err = check_coverage(args.source, d)
    if cov_err:
        print(f"[ERROR] {cov_err}", file=sys.stderr)
        return 1
    if args.source == "rda" and args.res != "0p25":
        print("[ERROR] NCAR RDA ds084.1 is GFS 0.25 deg only; use --res 0p25.",
              file=sys.stderr)
        return 1

    ymd = args.date.replace("-", "")
    repo_root = Path(__file__).resolve().parents[3]
    outdir = Path(args.outdir) if args.outdir else repo_root / "met_data" / "gfs" / f"{ymd}{args.cycle}"
    outdir.mkdir(parents=True, exist_ok=True)

    if args.source == "aws":
        _, _, grib_name = _aws_urls(args.date, args.cycle, args.fhour, args.res)
        url = "AWS S3 byte-range (.idx)"
    elif args.source == "rda":
        url, grib_name = _rda_url(args.date, args.cycle, args.fhour)
        if args.fields == "sst":
            print("[INFO] RDA serves full files (no subset); downloading the whole "
                  "file and using only its SST/sea-ice/land fields.")
    else:
        url, grib_name = build_filter_url(args.date, args.cycle, args.fhour, args.res,
                                          fields=args.fields)
    # SST-only subsets get a distinct name so they never collide with a full
    # download in the same directory (subsettable sources only).
    if args.fields == "sst" and args.source in ("aws", "nomads"):
        grib_name += ".sst"
    dest = outdir / grib_name

    if dest.exists() and dest.stat().st_size > 0:
        print(f"[OK] {grib_name} already present — skipping ({dest})")
        return 0

    print(f"[INFO] Downloading {grib_name} from {args.source} -> {dest}")

    if args.source == "rda":
        # Full file, streamed to disk (no subset).
        try:
            url, grib_name = fetch_rda_to(dest, args.date, args.cycle, args.fhour)
        except urllib.error.HTTPError as e:
            dest.unlink(missing_ok=True)
            if e.code in (401, 403):
                print("[ERROR] RDA requires authentication. Create a free account at "
                      "https://rda.ucar.edu and set RDA_API_TOKEN.", file=sys.stderr)
            else:
                print(f"[ERROR] RDA download failed: HTTP {e.code} "
                      f"(date/cycle not in ds084.1?)", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            print(f"[ERROR] RDA download failed: {e}", file=sys.stderr)
            return 1
        with open(dest, "rb") as f:
            head = f.read(4)
        if head != b"GRIB":
            dest.unlink(missing_ok=True)
            print("[ERROR] RDA response is not GRIB (login/HTML page?). "
                  "Set RDA_API_TOKEN if the dataset needs authentication.", file=sys.stderr)
            return 1
        size_bytes = dest.stat().st_size
        print(f"[OK] {grib_name} ({size_bytes / 1e6:.1f} MB)")
    else:
        if args.source == "aws":
            try:
                data, _ = fetch_aws(args.date, args.cycle, args.fhour, args.res,
                                    fields=args.fields)
            except urllib.error.HTTPError as e:
                print(f"[ERROR] AWS download failed: HTTP {e.code} "
                      f"(date/cycle not available?)", file=sys.stderr)
                return 1
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] AWS download failed: {e}", file=sys.stderr)
                return 1
        else:
            # NOMADS grib_filter (descriptive User-Agent is good etiquette).
            req = urllib.request.Request(url, headers={
                "User-Agent": "MPAS-Research/usp-utils (research; NOMADS grib_filter)"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    data = r.read()
            except urllib.error.HTTPError as e:
                data = e.read() or b""
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] Download failed: {e}", file=sys.stderr)
                return 1

        # NOMADS returns an HTML body (often with a 302) instead of GRIB on errors.
        if data[:4] != b"GRIB":
            if b"Over Rate Limit" in data or b"abusive-user-block" in data:
                print("[ERROR] NOMADS rate limit reached ('Over Rate Limit'). This is a "
                      "temporary IP block from too many requests.", file=sys.stderr)
                print("        Wait ~1 hour and retry, and avoid rapid repeated downloads. "
                      "See https://www.weather.gov/abusive-user-block", file=sys.stderr)
            else:
                print("[ERROR] Response is not GRIB (bad date/cycle, or data not yet "
                      "available / purged from NOMADS).", file=sys.stderr)
                print("        First bytes:", data[:120], file=sys.stderr)
            return 1

        dest.write_bytes(data)
        size_bytes = len(data)
        print(f"[OK] {grib_name} ({size_bytes / 1e6:.1f} MB)")

    # --- Provenance ----------------------------------------------------------
    sst_only = args.fields == "sst"
    meta = {
        "dataset": "GFS",
        "product": f"pgrb2.{args.res}",
        "source": SRC_LABEL[args.source],
        "fields": args.fields,
        "cycle": f"{args.date} {args.cycle}:00 UTC",
        "forecast_hour": args.fhour,
        "variables": SST_VARIABLES if sst_only else VARIABLES,
        "pressure_levels_hpa": [] if sst_only else PRESSURE_LEVELS,
        "surface_levels": SST_SURFACE_LEVELS if sst_only else SURFACE_LEVELS,
        "subset": args.source != "rda",  # rda = full file
        "url": url,
        "file": str(dest),
        "size_bytes": size_bytes,
        "download_date": datetime.now(timezone.utc).isoformat(),
    }
    (outdir / f"{grib_name}.provenance.json").write_text(json.dumps(meta, indent=2))
    print(f"[INFO] Provenance written to {grib_name}.provenance.json")
    next_script = "gfs_sst_to_intermediate.py" if sst_only else "gfs_to_intermediate.py"
    print(f"[INFO] Next: python {next_script} --grib {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
