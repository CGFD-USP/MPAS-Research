#!/usr/bin/env python3
"""
download_era5.py — fetch ERA5 reanalysis fields needed to initialize MPAS, for
dates the GFS archive does not cover (GFS 0.25 deg only exists from 2015-01-15;
ERA5 goes back to 1940).

Downloads two GRIB files via the CDS API (cdsapi):
  - pressure levels (reanalysis-era5-pressure-levels): z, t, u, v, r
  - single levels   (reanalysis-era5-single-levels):   sp, msl, skt, z (orog),
                     lsm, siconc, sd (snow), stl1-4 (soil T), swvl1-4 (soil moist)
They are then turned into the WPS intermediate format by era5_to_intermediate.py
(consumed by init_atmosphere with config_met_prefix='ERA5', matching the ERA5: prefix).

Requirements (in the cgfd-usp-mpas env):
  - cdsapi (pip)
  - a CDS account + ~/.cdsapirc with your API key
    (https://cds.climate.copernicus.eu/how-to-api). Never hard-code the key.

Usage:
    python download_era5.py --date 2014-09-10 --time 00 [--area N W S E] [--outdir <dir>]

Note: ERA5 is a reanalysis (analysis only, hourly) — there is no forecast hour.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Fields MPAS needs (CDS variable names) -----------------------------------
# Pressure-level fields (-> 3D intermediate). NOTE: ERA5 'geopotential' is in
# m^2/s^2; the converter divides by g0 to get geopotential height (GHT, m).
PL_VARIABLES = [
    "geopotential",            # z   -> GHT (after /g0)
    "temperature",             # t   -> TT
    "u_component_of_wind",     # u   -> UU
    "v_component_of_wind",     # v   -> VV
    "relative_humidity",       # r   -> RH
]

# Single-level fields (-> 2D intermediate).
SL_VARIABLES = [
    "surface_pressure",            # sp     -> PSFC
    "mean_sea_level_pressure",     # msl    -> PMSL
    "skin_temperature",            # skt    -> SKINTEMP
    "geopotential",                # z(sfc) -> SOILHGT (after /g0)
    "land_sea_mask",               # lsm    -> LANDSEA
    "sea_ice_cover",               # siconc -> SEAICE
    "snow_depth",                  # sd     -> SNOW (m w.e.; converter -> kg m-2)
    "soil_temperature_level_1",    # stl1   -> ST000007
    "soil_temperature_level_2",    # stl2   -> ST007028
    "soil_temperature_level_3",    # stl3   -> ST028100
    "soil_temperature_level_4",    # stl4   -> ST100289
    "volumetric_soil_water_layer_1",  # swvl1 -> SM000007
    "volumetric_soil_water_layer_2",  # swvl2 -> SM007028
    "volumetric_soil_water_layer_3",  # swvl3 -> SM028100
    "volumetric_soil_water_layer_4",  # swvl4 -> SM100289
]

# Full ERA5 isobaric set (hPa); like the GFS path, includes the upper levels so a
# 30 km model top has data to interpolate from.
PRESSURE_LEVELS = [
    1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 700, 650, 600, 550,
    500, 450, 400, 350, 300, 250, 225, 200, 175, 150, 125, 100, 70, 50, 30, 20,
    10, 7, 5, 3, 2, 1,
]


def _retrieve(client, dataset, request, target):
    print(f"[INFO] CDS retrieve {dataset} -> {target}")
    client.retrieve(dataset, request, str(target))


def main() -> int:
    ap = argparse.ArgumentParser(description="Download ERA5 fields for MPAS init.")
    ap.add_argument("--date", required=True, help="Analysis date, YYYY-MM-DD (UTC)")
    ap.add_argument("--time", default="00", help="Analysis hour HH (UTC), e.g. 00")
    ap.add_argument("--area", nargs=4, type=float, metavar=("N", "W", "S", "E"),
                    default=None, help="Optional bounding box (default: global)")
    ap.add_argument("--outdir", default=None,
                    help="Output dir (default: $MPAS_ROOT/met_data/era5/<date><HH>)")
    args = ap.parse_args()

    try:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print("[ERROR] --date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    hh = args.time.zfill(2)

    try:
        import cdsapi
    except ImportError:
        print("[ERROR] cdsapi not installed. In the cgfd-usp-mpas env: pip install cdsapi, "
              "and set up ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api).",
              file=sys.stderr)
        return 1

    ymd = args.date.replace("-", "")
    repo_root = Path(__file__).resolve().parents[3]
    outdir = (Path(args.outdir) if args.outdir
              else repo_root / "met_data" / "era5" / f"{ymd}{hh}")
    outdir.mkdir(parents=True, exist_ok=True)

    common = {
        "product_type": "reanalysis",
        "year": [d.strftime("%Y")],
        "month": [d.strftime("%m")],
        "day": [d.strftime("%d")],
        "time": [f"{hh}:00"],
        "data_format": "grib",          # older cdsapi: use "format" instead
        "download_format": "unarchived",
    }
    if args.area:
        common["area"] = [args.area[0], args.area[1], args.area[2], args.area[3]]

    pl_file = outdir / f"era5_pl_{ymd}{hh}.grib"
    sl_file = outdir / f"era5_sl_{ymd}{hh}.grib"

    try:
        client = cdsapi.Client()
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] cdsapi client init failed (missing ~/.cdsapirc?): {e}",
              file=sys.stderr)
        return 1

    try:
        if not (pl_file.exists() and pl_file.stat().st_size > 0):
            _retrieve(client, "reanalysis-era5-pressure-levels",
                      {**common, "variable": PL_VARIABLES,
                       "pressure_level": [str(p) for p in PRESSURE_LEVELS]}, pl_file)
        else:
            print(f"[OK] {pl_file.name} already present — skipping")
        if not (sl_file.exists() and sl_file.stat().st_size > 0):
            _retrieve(client, "reanalysis-era5-single-levels",
                      {**common, "variable": SL_VARIABLES}, sl_file)
        else:
            print(f"[OK] {sl_file.name} already present — skipping")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] CDS retrieve failed: {e}", file=sys.stderr)
        return 1

    # --- Provenance ----------------------------------------------------------
    meta = {
        "dataset": "ERA5",
        "products": ["reanalysis-era5-pressure-levels",
                     "reanalysis-era5-single-levels"],
        "source": "Copernicus CDS (cdsapi)",
        "valid_time": f"{args.date} {hh}:00 UTC",
        "pressure_variables": PL_VARIABLES,
        "single_variables": SL_VARIABLES,
        "pressure_levels_hpa": PRESSURE_LEVELS,
        "area": common.get("area", "global"),
        "files": [str(pl_file), str(sl_file)],
        "download_date": datetime.now(timezone.utc).isoformat(),
    }
    (outdir / f"era5_{ymd}{hh}.provenance.json").write_text(json.dumps(meta, indent=2))
    print(f"[OK] ERA5 files in {outdir}")
    print(f"[INFO] Next: python era5_to_intermediate.py "
          f"--pl {pl_file} --sl {sl_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
