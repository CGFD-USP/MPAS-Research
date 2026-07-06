#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vertical cross-section (transect) plots on the native MPAS grid — no regridding.

Sample the model cells nearest to a transect line and draw them against the
model's native vertical coordinate (``zgrid`` interfaces, in metres MSL), with
the terrain (``ter``) filled underneath. Two complementary uses:

  (a) --levels-only : show the vertical LEVEL STRUCTURE (zgrid interfaces) plus
      the terrain along the transect, without needing any field. Good for
      "seeing the levels" of a mesh.

  (b) -v <field>    : COLOR a 3D field (theta, qv, pressure, rho, wind, ...)
      along the transect, with height (m) on the vertical axis and the terrain
      filled at the bottom.

The transect is defined either by two end points (--start / --end) or by a line
of constant latitude (--lat) or constant longitude (--lon). Cells are picked by
nearest-neighbour (haversine) along densely sampled points, consecutive
duplicates are collapsed, and columns are placed at their accumulated
great-circle distance along the line.

The vertical grid, terrain and mesh coordinates come from a static/init/grid
file. Pass it with -gf if the plotted file itself does not carry ``zgrid``/
``ter`` (e.g. history files).

Usage examples
--------------
  # List 3D (nVertLevels) variables available to color
  python mpas_cross_section.py -f meqbr_05km.init.nc -gf meqbr_05km.init.nc

  # Just look at the vertical levels + terrain along a 2-point transect
  python mpas_cross_section.py -f meqbr_05km.init.nc -gf meqbr_05km.init.nc \
      --levels-only --start "-30,-50" --end "-20,-40" -o levels.png

  # Color potential temperature along a constant-latitude transect
  python mpas_cross_section.py -f meqbr_05km.init.nc -gf meqbr_05km.init.nc \
      -v theta --lat -25 -o theta_xsec.png

  # Same, but with the vertical axis as level index and capped at 15 km
  python mpas_cross_section.py -f meqbr_05km.init.nc -gf meqbr_05km.init.nc \
      -v qv --lon -45 --by-index -o qv_xsec.png

Reuses the shared building blocks from ``mpas_viz.py`` (file opening, derived
mesh coordinates, color-scale helpers, colorbar, grid-file resolution and the
argparse conventions) so behaviour stays consistent across the toolset.

Author: Danilo Couto de Souza (2026).
"""

import os
import sys
import argparse

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

# Reuse the shared plotting/mesh helpers from the sibling mpas_viz module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpas_viz  # noqa: E402
from mpas_viz import (  # noqa: E402
    open_mpas_file,
    set_plot_kwargs,
    add_colorbar,
    _render_table,
    _decode_xtime,
    _yn,
)

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Variable listing (3D fields only)
# ---------------------------------------------------------------------------
def list_3d_variables(ds):
    """Names of fields defined on (nCells, nVertLevels) — colorable in a xsec."""
    out = []
    for v in ds.data_vars:
        dims = ds[v].dims
        if 'nCells' in dims and 'nVertLevels' in dims:
            out.append(str(v))
    return sorted(out)


def format_3d_variables_table(ds):
    """Aligned table of colorable 3D variables (reuses mpas_viz._render_table)."""
    variables = list_3d_variables(ds)
    if not variables:
        return ("No 3D variables (with both 'nCells' and 'nVertLevels' "
                "dimensions) were found in this file.")

    MAX_LONGNAME = 45
    rows = []
    for v in variables:
        attrs = ds[v].attrs
        long_name = str(attrs.get('long_name', '') or '-')
        if len(long_name) > MAX_LONGNAME:
            long_name = long_name[:MAX_LONGNAME - 1] + '…'
        units = str(attrs.get('units', '') or '-')
        has_time = 'yes' if 'Time' in ds[v].dims else 'no'
        rows.append([v, long_name, units, has_time])

    headers = ['Variable', 'Long name', 'Units', 'Time']
    return _render_table(f"Colorable 3D variables ({len(rows)})", headers, rows,
                         footer="Pick one with: -v/--var <Variable>")


# ---------------------------------------------------------------------------
# Vertical-grid resolution (zgrid + ter)
# ---------------------------------------------------------------------------
def resolve_vertical_grid(ds, gridfile):
    """Return a dataset carrying the vertical grid (``zgrid``) and terrain (``ter``).

    Looks in ``ds`` first, then in ``-gf/--gridfile``. Unlike the mesh
    connectivity, ``zgrid`` (the native height coordinate) is produced by
    ``init_atmosphere`` and lives ONLY in ``*.init.nc`` — ``*.static.nc`` carries
    ``ter`` but not ``zgrid``, and ``*.grid.nc`` carries neither. The error
    messages point users there.
    """
    need = ['zgrid', 'ter']

    def _missing(d):
        return [v for v in need if v not in d]

    if not _missing(ds):
        return ds

    if gridfile is None:
        raise SystemExit(
            "\nERROR: the vertical grid is missing "
            f"({', '.join(_missing(ds))} not found in this file).\n"
            "       'zgrid' (native height coordinate) is written by "
            "init_atmosphere and lives ONLY in *.init.nc.\n"
            "       Pass one with -gf/--gridfile, e.g.:  -gf <mesh>.init.nc\n"
            "       (*.static.nc has 'ter' but NOT 'zgrid'; *.grid.nc has "
            "neither.)")

    if not os.path.exists(gridfile):
        raise SystemExit(
            f"\nERROR: grid file passed with -gf/--gridfile does not exist:\n"
            f"           {gridfile}")

    try:
        ds_grid = open_mpas_file(gridfile)
    except Exception as err:
        raise SystemExit(
            f"\nERROR: could not open the grid file '{gridfile}' as a "
            f"NetCDF dataset:\n           {err}")

    miss = _missing(ds_grid)
    if miss:
        hint = ""
        if 'zgrid' in miss:
            hint = ("\n       'zgrid' lives only in *.init.nc — a *.static.nc / "
                    "*.grid.nc will not work here.")
        raise SystemExit(
            f"\nERROR: the grid file '{gridfile}' is missing "
            f"{', '.join(miss)} needed for a vertical cross-section.{hint}")

    return ds_grid


# ---------------------------------------------------------------------------
# Transect geometry and nearest-cell sampling
# ---------------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (km) between points in degrees (vectorized)."""
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlon = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = (np.sin(dlat / 2.0) ** 2
         + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def _parse_point(text, name):
    """Parse a 'lat,lon' CLI string into (lat, lon) floats."""
    try:
        lat, lon = (float(x) for x in text.split(','))
    except Exception:
        raise SystemExit(
            f"\nERROR: --{name} must be 'lat,lon' (e.g. --{name} \"-30,-50\"), "
            f"got '{text}'.")
    return lat, lon


def resolve_endpoints(start, end, lat, lon, lat_cell, lon_cell):
    """Turn the CLI transect options into (lat0, lon0, lat1, lon1).

    Constant-lat/lon lines span the mesh's own coordinate bounds so the
    transect covers the full domain at that latitude/longitude.
    """
    modes = [start is not None or end is not None, lat is not None,
             lon is not None]
    if sum(bool(m) for m in modes) != 1:
        raise SystemExit(
            "\nERROR: define the transect with exactly one of:\n"
            "         --start \"lat,lon\" --end \"lat,lon\"   (two points)\n"
            "         --lat <value>                          (constant latitude)\n"
            "         --lon <value>                          (constant longitude)")

    if lat is not None:
        return lat, float(np.min(lon_cell)), lat, float(np.max(lon_cell))
    if lon is not None:
        return float(np.min(lat_cell)), lon, float(np.max(lat_cell)), lon

    if start is None or end is None:
        raise SystemExit("\nERROR: two-point transect needs both --start and --end.")
    lat0, lon0 = _parse_point(start, 'start')
    lat1, lon1 = _parse_point(end, 'end')
    return lat0, lon0, lat1, lon1


def sample_transect(lat0, lon0, lat1, lon1, lat_cell, lon_cell, npoints,
                    max_snap_km=None):
    """Nearest-cell sampling along a straight lat/lon transect.

    Sample points whose nearest cell is farther than ``max_snap_km`` are treated
    as lying outside the (regional) mesh domain and dropped, so an off-domain
    transect does not silently snap onto a couple of boundary cells.

    Returns
    -------
    cells : ndarray[int]
        0-based cell indices along the transect (consecutive duplicates dropped).
    dist_km : ndarray[float]
        Accumulated great-circle distance (km) at each selected cell.
    n_outside : int
        Number of sample points dropped as outside the mesh domain.
    """
    # Dense, evenly spaced sample points along the (lat, lon) segment.
    plat = np.linspace(lat0, lat1, npoints)
    plon = np.linspace(lon0, lon1, npoints)

    picked = []
    n_outside = 0
    for la, lo in zip(plat, plon):
        d = _haversine_km(lat_cell, lon_cell, la, lo)
        j = int(np.argmin(d))
        if max_snap_km is not None and d[j] > max_snap_km:
            n_outside += 1
            continue
        picked.append(j)

    if not picked:
        raise SystemExit(
            "\nERROR: the transect lies entirely outside the mesh domain "
            f"(lat {lat_cell.min():.2f}..{lat_cell.max():.2f}, "
            f"lon {lon_cell.min():.2f}..{lon_cell.max():.2f}). "
            "Pick end points inside the domain.")

    # Collapse consecutive duplicates so each column is a distinct cell.
    cells = [picked[0]]
    for c in picked[1:]:
        if c != cells[-1]:
            cells.append(c)
    cells = np.asarray(cells, dtype=int)

    # Accumulated distance along the actual selected cell centers.
    dist_km = np.zeros(len(cells))
    if len(cells) > 1:
        seg = _haversine_km(lat_cell[cells[:-1]], lon_cell[cells[:-1]],
                            lat_cell[cells[1:]], lon_cell[cells[1:]])
        dist_km[1:] = np.cumsum(seg)
    return cells, dist_km, n_outside


# ---------------------------------------------------------------------------
# Cross-section assembly
# ---------------------------------------------------------------------------
def _x_edges(xc):
    """Midpoint edges for column centers ``xc`` (length N -> N+1)."""
    xc = np.asarray(xc, dtype=float)
    if len(xc) == 1:
        return np.array([xc[0] - 0.5, xc[0] + 0.5])
    mids = 0.5 * (xc[:-1] + xc[1:])
    first = xc[0] - 0.5 * (xc[1] - xc[0])
    last = xc[-1] + 0.5 * (xc[-1] - xc[-2])
    return np.concatenate([[first], mids, [last]])


def _interface_corners(z_iface):
    """Corner heights for pcolormesh from interface heights.

    z_iface has shape (nInterfaces, ncols); returns (nInterfaces, ncols+1) with
    columns averaged onto the x-edges (edges replicated at the two ends).
    """
    left = z_iface[:, :1]
    mid = 0.5 * (z_iface[:, :-1] + z_iface[:, 1:])
    right = z_iface[:, -1:]
    return np.concatenate([left, mid, right], axis=1)


def get_time_label(ds, tindex):
    """xtime string for the selected time index (or a fallback)."""
    if 'xtime' in ds.variables:
        try:
            xt = ds['xtime'].values
            return _decode_xtime(xt[tindex] if xt.ndim else xt)
        except Exception:
            pass
    return f"t={tindex}"


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_levels_only(ax, dist_km, z_iface, ter_cols, by_index):
    """Draw the zgrid interfaces and the terrain fill (mode a)."""
    n_iface = z_iface.shape[0]
    if by_index:
        y = np.repeat(np.arange(n_iface)[:, None], z_iface.shape[1], axis=1)
        ylabel = 'Vertical level interface index'
    else:
        y = z_iface
        ylabel = 'Geometric height (m MSL)'

    for k in range(n_iface):
        # Emphasize the lowest interface (follows the terrain).
        lw, color = (0.9, 'k') if k == 0 else (0.4, '0.35')
        ax.plot(dist_km, y[k, :], color=color, linewidth=lw)

    if not by_index:
        ybottom = float(np.min(z_iface))
        ax.fill_between(dist_km, ybottom, ter_cols, color='0.55',
                        zorder=5, linewidth=0)
        ax.set_ylim(ybottom, float(np.max(z_iface)))

    ax.set_ylabel(ylabel)
    return


def plot_field(ax, fig, dist_km, z_iface, field2d, ter_cols, by_index,
               plot_kwargs, cbar_label, extend):
    """Color a 3D field along the transect with pcolormesh (mode b)."""
    n_iface = z_iface.shape[0]
    ncols = z_iface.shape[1]

    xe = _x_edges(dist_km)
    x2d = np.tile(xe, (n_iface, 1))

    if by_index:
        yc = np.repeat(np.arange(n_iface)[:, None], ncols + 1, axis=1)
        y2d = yc.astype(float)
        ylabel = 'Vertical level index'
    else:
        y2d = _interface_corners(z_iface)
        ylabel = 'Geometric height (m MSL)'

    mesh = ax.pcolormesh(x2d, y2d, field2d,
                         cmap=plot_kwargs['cmap'],
                         vmin=plot_kwargs['vmin'], vmax=plot_kwargs['vmax'],
                         shading='flat')

    if not by_index:
        ybottom = float(np.min(z_iface))
        ax.fill_between(dist_km, ybottom, ter_cols, color='0.4',
                        zorder=5, linewidth=0)
        ax.plot(dist_km, ter_cols, color='k', linewidth=0.6, zorder=6)
        ax.set_ylim(ybottom, float(np.max(z_iface)))

    ax.set_ylabel(ylabel)
    add_colorbar(ax, fig=fig, label=cbar_label, extend=extend, **plot_kwargs)
    return mesh


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run(infile, vname=None, gridfile=None, outfile=None,
        start=None, end=None, lat=None, lon=None, npoints=500,
        levels_only=False, by_index=False, tindex=0, zmax=None,
        cmap='Spectral', vmin=None, vmax=None, clip=False, extend='both',
        dpi=150):
    """Build and draw a native-grid vertical cross-section."""
    ds = open_mpas_file(infile)

    # List colorable variables when nothing to plot was requested.
    if vname is None and not levels_only:
        print("File:", infile)
        print(format_3d_variables_table(ds))
        ds.close()
        return

    # Resolve vertical grid + terrain + mesh coords (from infile or -gf).
    ds_grid = resolve_vertical_grid(ds, gridfile)

    lat_cell = ds_grid['latitude'].values
    lon_cell = ds_grid['longitude'].values
    zgrid = ds_grid['zgrid'].values          # (nCells, nVertLevelsP1)
    ter = ds_grid['ter'].values              # (nCells,)

    # Out-of-domain guard scaled to the mesh resolution (km per cell). Points
    # whose nearest cell is farther than a few cell widths are off the mesh.
    if 'resolution' in ds_grid:
        max_snap_km = 3.0 * float(np.median(ds_grid['resolution'].values))
    else:
        max_snap_km = None  # no areaCell to size the mesh -> skip the guard

    # Geometry + nearest-cell sampling.
    lat0, lon0, lat1, lon1 = resolve_endpoints(start, end, lat, lon,
                                               lat_cell, lon_cell)
    cells, dist_km, n_outside = sample_transect(
        lat0, lon0, lat1, lon1, lat_cell, lon_cell, npoints,
        max_snap_km=max_snap_km)
    if len(cells) < 2:
        raise SystemExit(
            "\nERROR: the transect resolves to a single cell; it may barely "
            "clip the domain. Pick end points farther apart and inside the mesh.")
    print(f"Transect ({lat0:.3f},{lon0:.3f}) -> ({lat1:.3f},{lon1:.3f}): "
          f"{len(cells)} cells over {dist_km[-1]:.1f} km.")
    if n_outside:
        print(f"  Note: {n_outside}/{npoints} sample points were outside the "
              "mesh domain and were skipped.")

    z_iface = zgrid[cells, :].T              # (nVertLevelsP1, ncols)
    ter_cols = ter[cells]

    fig, ax = plt.subplots(figsize=(11, 6))

    if levels_only:
        plot_levels_only(ax, dist_km, z_iface, ter_cols, by_index)
        title = f"Vertical levels ({z_iface.shape[0]} interfaces)"
    else:
        if vname not in ds:
            raise SystemExit(f"\nERROR: variable '{vname}' not found in {infile}.")
        da = ds[vname]
        if 'nVertLevels' not in da.dims:
            hint = ""
            if vname == 'ter' or ('nCells' in da.dims and da.ndim <= 2):
                hint = ("\n       To see the terrain along the transect (it is "
                        "drawn as the filled bottom), use --levels-only.")
            raise SystemExit(
                f"\nERROR: '{vname}' has dims {da.dims}; a colored cross-section "
                "needs a 3D field on (nCells, nVertLevels). Run without -v to "
                f"list the colorable variables.{hint}")
        if 'Time' in da.dims:
            da = da.isel(Time=tindex)

        field = da.values                    # (nCells, nVertLevels)
        field2d = field[cells, :].T          # (nVertLevels, ncols)

        # Derive the color scale from the VISIBLE part only: when the vertical
        # axis is capped with --zmax, values above it (e.g. huge stratospheric
        # theta) must not wash out the tropospheric gradient.
        scale2d = field2d
        if zmax is not None and not by_index:
            z_center = 0.5 * (z_iface[:-1, :] + z_iface[1:, :])
            visible = z_center <= zmax
            if visible.any():
                scale2d = field2d[visible]
        plot_kwargs = set_plot_kwargs(da=xr.DataArray(scale2d), clip=clip,
                                      cmap=cmap, vmin=vmin, vmax=vmax)
        units = da.attrs.get('units', '')
        cbar_label = f"{vname} ({units})" if units else vname
        plot_field(ax, fig, dist_km, z_iface, field2d, ter_cols, by_index,
                   plot_kwargs, cbar_label, extend)
        title = f"{vname}"
        if 'Time' in ds[vname].dims:
            title += f"\n{get_time_label(ds, tindex)}"

    if zmax is not None and not by_index:
        ax.set_ylim(ax.get_ylim()[0], zmax)

    ax.set_xlabel('Distance along transect (km)')
    ax.set_xlim(dist_km[0], dist_km[-1])
    subtitle = (f"({lat0:.2f}, {lon0:.2f}) → ({lat1:.2f}, {lon1:.2f})")
    ax.set_title(f"{title}\n{subtitle}", fontsize=11)
    ax.grid(True, alpha=0.2, linewidth=0.4)

    ds.close()

    if outfile is not None:
        fig.savefig(outfile, dpi=dpi, bbox_inches='tight')
        print(f"Saved: {os.path.abspath(outfile)}")
    else:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("-f", "--infile", "--files", dest="infile", type=str,
                        required=True,
                        help="MPAS file with the field / vertical grid")
    parser.add_argument("-gf", "--gridfile", type=str, default=None,
                        help="File providing zgrid/ter/mesh coords if infile "
                             "lacks them (static/init/grid .nc)")
    parser.add_argument("-o", "--outfile", type=str, default=None,
                        help="Output image (.png/.pdf). Omit to show it "
                             "interactively.")
    parser.add_argument("-v", "--var", type=str, default=None,
                        help="3D variable to color. Omit (without "
                             "--levels-only) to list available variables.")

    # Transect definition
    parser.add_argument("--start", type=str, default=None,
                        help="Transect start point 'lat,lon' (with --end)")
    parser.add_argument("--end", type=str, default=None,
                        help="Transect end point 'lat,lon' (with --start)")
    parser.add_argument("--lat", type=float, default=None,
                        help="Constant-latitude transect at this latitude")
    parser.add_argument("--lon", type=float, default=None,
                        help="Constant-longitude transect at this longitude")
    parser.add_argument("--npoints", type=int, default=500,
                        help="Number of samples along the line (default: 500). "
                             "Raise it for fine meshes / long transects.")

    # Vertical axis / modes
    parser.add_argument("--levels-only", action='store_true',
                        help="Draw the zgrid interfaces + terrain, no field")
    parser.add_argument("--by-index", action='store_true',
                        help="Vertical axis as level index instead of height (m)")
    parser.add_argument("--zmax", type=float, default=None,
                        help="Cap the vertical axis at this height (m)")
    parser.add_argument("-t", "--time", dest="time", type=int, default=0,
                        help="Time index for the field (default: 0)")

    # Color
    parser.add_argument("--cmap", type=str, default='Spectral',
                        help="Colormap (default: Spectral)")
    parser.add_argument("--vmin", type=float, default=None,
                        help="Minimum value for the color scale")
    parser.add_argument("--vmax", type=float, default=None,
                        help="Maximum value for the color scale")
    parser.add_argument("-c", "--clip", type=str, default='no',
                        help="Clip extremes at mean +/- 4*std: yes or no")
    parser.add_argument("--extend", type=str, default='both',
                        help="Colorbar extend: both/neither/min/max")

    parser.add_argument("--dpi", type=int, default=150,
                        help="Output resolution (default: 150)")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.exists(args.infile):
        raise SystemExit(f"\nERROR: file does not exist: {args.infile}")

    run(infile=args.infile,
        vname=args.var,
        gridfile=args.gridfile,
        outfile=args.outfile,
        start=args.start, end=args.end, lat=args.lat, lon=args.lon,
        npoints=args.npoints,
        levels_only=args.levels_only,
        by_index=args.by_index,
        tindex=args.time,
        zmax=args.zmax,
        cmap=args.cmap, vmin=args.vmin, vmax=args.vmax,
        clip=_yn(args.clip), extend=args.extend,
        dpi=args.dpi)


if __name__ == "__main__":
    main()
