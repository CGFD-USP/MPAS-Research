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

  # Wind decomposed relative to the transect: in-plane arrows (along-transect +
  # vertical) and normal-component symbols (dot = towards viewer, cross = away)
  python mpas_cross_section.py -f history.nc -gf meqbr_05km.init.nc -v theta \
      --lat -1 -u uReconstructZonal -v_wind uReconstructMeridional -w w \
      --zmax 12000 -o theta_wind.png

  # Animate the transect across many output files (several steps -> .mp4/.gif)
  python mpas_cross_section.py -f "history.*.nc" -gf meqbr_05km.init.nc \
      -v theta --lat -1 --zmax 15000 --fps 8 -o theta_xsec.mp4

Time model
----------
Input files are expanded into one ordered timeline (as in ``mpas_viz.py``). Use
``--list-times`` to inspect it and ``--tstart/--tend`` (inclusive) to sub-select:
one selected step gives a still image, more than one gives an animation. The
transect geometry is fixed in time, so only the field/wind are re-read per frame.

Reuses the shared building blocks from ``mpas_viz.py`` (file opening, derived
mesh coordinates, color-scale helpers, colorbar, grid-file resolution, the
timeline/animation machinery and the argparse conventions) so behaviour stays
consistent across the toolset.

Author: Danilo Couto de Souza (2026).
"""

import os
import sys
import glob
import argparse

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
from tqdm import tqdm

# Reuse the shared plotting/mesh helpers from the sibling mpas_viz module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpas_viz  # noqa: E402
from mpas_viz import (  # noqa: E402
    open_mpas_file,
    set_plot_kwargs,
    add_colorbar,
    build_timeline,
    format_timeline_table,
    _stitch_pngs,
    _render_table,
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
# Wind decomposition relative to the transect
# ---------------------------------------------------------------------------
def transect_tangent(latc, lonc, smooth=5):
    """Per-column along-transect unit vector (east, north) from cell centers.

    The nearest-cell path wiggles slightly (it hops between cell centers), which
    would give a pure zonal/meridional wind a spurious normal component; a short
    moving average over the direction (``smooth`` columns) damps that.

    Returns ``(te, tn)`` pointing from the transect start towards its end.
    """
    latc = np.asarray(latc, dtype=float)
    lonc = np.asarray(lonc, dtype=float)
    de = np.cos(np.radians(latc)) * np.gradient(lonc)   # local eastward metric
    dn = np.gradient(latc)                              # local northward metric

    if smooth > 1 and len(de) > smooth:
        pad = smooth // 2
        k = np.ones(smooth) / smooth
        de = np.convolve(np.pad(de, pad, mode='edge'), k, 'valid')[:len(latc)]
        dn = np.convolve(np.pad(dn, pad, mode='edge'), k, 'valid')[:len(latc)]

    norm = np.hypot(de, dn)
    norm[norm == 0] = 1.0
    return de / norm, dn / norm


def _wind_cell_field(ds, name, tindex, nlev, cells):
    """Extract a (nlev, ncols) wind array at layer centers for ``cells``."""
    if name not in ds:
        raise SystemExit(f"\nERROR: wind variable '{name}' not found in the file.")
    da = ds[name]
    if 'Time' in da.dims:
        da = da.isel(Time=tindex)
    arr = da.values
    if arr.ndim != 2:
        raise SystemExit(
            f"\nERROR: wind variable '{name}' has dims {ds[name].dims}; expected "
            "a 3D field on (nCells, nVertLevels[/P1]).")
    # Interface field (nVertLevelsP1, e.g. w) -> average onto layer centers.
    if arr.shape[1] == nlev + 1:
        arr = 0.5 * (arr[:, :-1] + arr[:, 1:])
    return arr[cells, :].T                       # (nlev, ncols)


def add_transect_wind(ax, dist_km, z_center, cells, ds, tindex,
                      u_var, v_var, w_var, te, tn,
                      wind_stride=None, wind_lstride=3, w_exag=100.0,
                      ref_speed=None):
    """Overlay winds decomposed relative to the transect orientation.

    The horizontal wind (u east, v north) is split into:
      * along-transect ``u_t = u·te + v·tn`` (positive towards the right/end),
      * transect-normal ``u_n = u·tn - v·te`` (positive = out of the page,
        towards the viewer).

    In-plane arrows show the (along-transect, vertical) circulation; ``w`` is
    multiplied by ``w_exag`` so the qualitative tilt is visible (arrow angle is
    atan2(w·exag, u_t), independent of the km-vs-m axes). The normal component is
    drawn with the standard meteorological symbols: a filled dot inside a circle
    for flow towards the viewer (⊙, out of page) and a cross for flow away from
    the viewer (⊗, into page), sized by magnitude.
    """
    nlev, ncols = z_center.shape
    u = _wind_cell_field(ds, u_var, tindex, nlev, cells)
    v = _wind_cell_field(ds, v_var, tindex, nlev, cells)
    w = (_wind_cell_field(ds, w_var, tindex, nlev, cells)
         if w_var is not None else np.zeros_like(u))

    te2, tn2 = te[None, :], tn[None, :]
    u_t = u * te2 + v * tn2
    u_n = u * tn2 - v * te2

    if wind_stride is None:
        wind_stride = max(1, ncols // 30)        # aim for ~30 arrows across
    ci = np.arange(0, ncols, wind_stride)
    li = np.arange(0, nlev, wind_lstride)
    C, L = np.meshgrid(ci, li)

    X = np.tile(dist_km, (nlev, 1))[L, C]
    Z = z_center[L, C]
    Ut, W, Un = u_t[L, C], w[L, C], u_n[L, C]

    # In-plane circulation arrows (along-transect, vertical). angles='uv' keeps
    # the tilt tied to the components, not to the distorted data axes.
    q = ax.quiver(X, Z, Ut, W * w_exag, angles='uv', pivot='mid',
                  scale_units='width', width=0.0022, color='k',
                  alpha=0.85, zorder=8)
    if ref_speed is None:
        ref_speed = max(1.0, round(float(np.nanpercentile(np.abs(Ut), 90))))
    ax.quiverkey(q, 0.80, 1.035, ref_speed,
                 f"{ref_speed:g} m/s (along/vert, w×{w_exag:g})",
                 labelpos='E', coordinates='axes', fontproperties={'size': 8})

    # Normal-component symbols: dot = towards viewer, cross = away. Size ∝ |u_n|.
    # Skip points with negligible normal flow so pure in-plane regions stay clean.
    amax = float(np.nanmax(np.abs(Un))) or 1.0
    sig = np.abs(Un) >= 0.05 * amax
    size = 15.0 + 120.0 * (np.abs(Un) / amax)
    toward = sig & (Un > 0)
    away = sig & (Un <= 0)
    ax.scatter(X[sig], Z[sig], s=size[sig], facecolors='none', edgecolors='k',
               linewidths=0.6, zorder=9)
    ax.scatter(X[toward], Z[toward], s=size[toward] * 0.22, c='k',
               marker='o', zorder=10)
    ax.scatter(X[away], Z[away], s=size[away] * 0.5, c='k',
               marker='x', linewidths=0.8, zorder=10)

    ax.text(0.005, 1.035, "normal:  ⊙ toward viewer   ⊗ away",
            transform=ax.transAxes, fontsize=8, va='bottom')
    return


# ---------------------------------------------------------------------------
# Geometry + per-frame rendering (shared by still image and animation frames)
# ---------------------------------------------------------------------------
def build_geometry(grid_file, gridfile, start, end, lat, lon, npoints):
    """Resolve the fixed transect geometry (independent of time).

    Returns a dict with the selected cells, along-track distance, the vertical
    interfaces and terrain for those cells, and the mesh coordinates/endpoints.
    """
    ds_src = open_mpas_file(grid_file)
    ds_grid = resolve_vertical_grid(ds_src, gridfile)

    lat_cell = ds_grid['latitude'].values
    lon_cell = ds_grid['longitude'].values
    zgrid = ds_grid['zgrid'].values          # (nCells, nVertLevelsP1)
    ter = ds_grid['ter'].values              # (nCells,)
    max_snap_km = (3.0 * float(np.median(ds_grid['resolution'].values))
                   if 'resolution' in ds_grid else None)
    if ds_grid is not ds_src:
        ds_grid.close()
    ds_src.close()

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

    return {
        'cells': cells, 'dist_km': dist_km,
        'z_iface': zgrid[cells, :].T, 'ter_cols': ter[cells],
        'lat_cell': lat_cell, 'lon_cell': lon_cell,
        'endpoints': (lat0, lon0, lat1, lon1),
    }


def _field_at_cells(ds, vname, tindex, cells):
    """Extract a (nVertLevels, ncols) field slice along the transect."""
    da = ds[vname]
    if 'Time' in da.dims:
        da = da.isel(Time=tindex)
    return da.values[cells, :].T, da


def _z_center_plot(z_iface, ncols, by_index):
    """Layer-center vertical coordinate used to place wind symbols/arrows."""
    if by_index:
        n_lev = z_iface.shape[0] - 1
        return np.repeat((np.arange(n_lev) + 0.5)[:, None], ncols, axis=1)
    return 0.5 * (z_iface[:-1, :] + z_iface[1:, :])


def _finalize_axes(ax, geom, title, zmax, by_index):
    """Apply the shared labels, limits and title to a cross-section axis."""
    lat0, lon0, lat1, lon1 = geom['endpoints']
    if zmax is not None and not by_index:
        ax.set_ylim(ax.get_ylim()[0], zmax)
    ax.set_xlabel('Distance along transect (km)')
    ax.set_xlim(geom['dist_km'][0], geom['dist_km'][-1])
    ax.set_title(f"{title}\n({lat0:.2f}, {lon0:.2f}) → ({lat1:.2f}, {lon1:.2f})",
                 fontsize=11)
    ax.grid(True, alpha=0.2, linewidth=0.4)


def auto_extent(lon, lat, values=None, margin_frac=0.05, clamp=True):
    """Bounding box ``[lon_min, lon_max, lat_min, lat_max]`` of the valid cells.

    When ``values`` is given, only cells with finite (non-NaN) data are used, so
    the box tightens to where the field actually exists; otherwise the full mesh
    footprint is used. A small relative margin is added and, with ``clamp``, the
    box is kept within the global lon/lat range.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if values is not None:
        valid = np.isfinite(np.asarray(values))
        if valid.ndim > 1:                       # (nCells, nLev, …) -> per cell
            valid = valid.any(axis=tuple(range(1, valid.ndim)))
        if valid.any():
            lon, lat = lon[valid], lat[valid]

    lon_min, lon_max = float(np.min(lon)), float(np.max(lon))
    lat_min, lat_max = float(np.min(lat)), float(np.max(lat))
    m_lon = margin_frac * ((lon_max - lon_min) or 1.0)
    m_lat = margin_frac * ((lat_max - lat_min) or 1.0)
    ext = [lon_min - m_lon, lon_max + m_lon, lat_min - m_lat, lat_max + m_lat]
    if clamp:
        ext[0], ext[1] = max(ext[0], -180.0), min(ext[1], 180.0)
        ext[2], ext[3] = max(ext[2], -90.0), min(ext[3], 90.0)
    return ext


def add_location_inset(fig, geom, rect=(0.135, 0.55, 0.24, 0.28)):
    """Draw a small cartopy locator map showing the transect as a red line.

    The inset extent is set automatically from the mesh footprint
    (``auto_extent``), so a regional mesh is framed nicely without manual bounds.
    """
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    cells = geom['cells']
    tlon = geom['lon_cell'][cells]
    tlat = geom['lat_cell'][cells]
    ext = auto_extent(geom['lon_cell'], geom['lat_cell'])

    inax = fig.add_axes(rect, projection=ccrs.PlateCarree())
    inax.set_extent(ext, crs=ccrs.PlateCarree())
    try:
        inax.add_feature(cfeature.LAND, facecolor='0.85', zorder=0)
        inax.add_feature(cfeature.OCEAN, facecolor='white', zorder=0)
        inax.coastlines('50m', linewidth=0.4, zorder=1)
    except Exception:
        pass  # Natural Earth data unavailable offline -> still show the transect
    inax.gridlines(draw_labels=False, linewidth=0.3, alpha=0.4)

    inax.plot(tlon, tlat, color='red', linewidth=1.6,
              transform=ccrs.PlateCarree(), zorder=3)
    inax.plot(tlon[0], tlat[0], marker='o', color='red', markersize=3,
              transform=ccrs.PlateCarree(), zorder=4)
    inax.plot(tlon[-1], tlat[-1], marker='s', color='red', markersize=3,
              transform=ccrs.PlateCarree(), zorder=4)
    inax.set_title('transect', fontsize=7)
    return inax


def render_field_frame(ax, fig, frame, geom, vname, plot_kwargs, *,
                       by_index, zmax, extend, cbar_label,
                       u_var, v_var, w_var, wind_stride, wind_lstride, w_exag,
                       show_inset=True):
    """Draw one timeline frame (field + optional wind) onto ``ax``."""
    ds = open_mpas_file(frame['file'])
    has_time = 'Time' in ds[vname].dims
    field2d, _ = _field_at_cells(ds, vname, frame['tindex'], geom['cells'])
    plot_field(ax, fig, geom['dist_km'], geom['z_iface'], field2d,
               geom['ter_cols'], by_index, plot_kwargs, cbar_label, extend)

    if u_var is not None and v_var is not None:
        z_center = _z_center_plot(geom['z_iface'], len(geom['cells']), by_index)
        te, tn = transect_tangent(geom['lat_cell'][geom['cells']],
                                  geom['lon_cell'][geom['cells']])
        add_transect_wind(ax, geom['dist_km'], z_center, geom['cells'], ds,
                          frame['tindex'], u_var, v_var, w_var, te, tn,
                          wind_stride=wind_stride, wind_lstride=wind_lstride,
                          w_exag=w_exag)

    title = f"{vname}\n{frame['xtime']}" if has_time else vname
    _finalize_axes(ax, geom, title, zmax, by_index)
    if show_inset:
        add_location_inset(fig, geom)
    ds.close()


def _save_or_show(fig, outfile, dpi):
    if outfile is not None:
        fig.savefig(outfile, dpi=dpi, bbox_inches='tight')
        print(f"Saved: {os.path.abspath(outfile)}")
    else:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run(infile, vname=None, gridfile=None, outfile=None,
        start=None, end=None, lat=None, lon=None, npoints=500,
        levels_only=False, by_index=False, tstart=None, tend=None,
        list_times=False, zmax=None,
        cmap='Spectral_r', vmin=None, vmax=None, clip=False, extend='both',
        u_var=None, v_var=None, w_var=None, wind_stride=None,
        wind_lstride=3, w_exag=100.0, inset=True, fps=5, dpi=150):
    """Draw a still cross-section, or animate when several time steps are picked.

    Files are expanded into one ordered timeline (as in ``mpas_viz.py``); a
    single selected step gives a still image, more than one gives an animation.
    The transect geometry is fixed in time, so it is resolved once and only the
    field/wind are re-read per frame.
    """
    # 1. Build the timeline; optionally just list it.
    timeline = build_timeline(infile)
    if list_times:
        print("Files:", infile)
        print(format_timeline_table(timeline))
        return

    # 2. No variable (and not levels-only): list colorable 3D variables and exit.
    if vname is None and not levels_only:
        ds0 = open_mpas_file(timeline[0]['file'])
        print("File:", timeline[0]['file'])
        print(format_3d_variables_table(ds0))
        ds0.close()
        return

    # 3. Fixed transect geometry (grid comes from -gf or the first file).
    geom = build_geometry(timeline[0]['file'], gridfile,
                          start, end, lat, lon, npoints)

    # 4. Levels-only is time-independent -> a single static image.
    if levels_only:
        fig, ax = plt.subplots(figsize=(11, 6))
        plot_levels_only(ax, geom['dist_km'], geom['z_iface'], geom['ter_cols'],
                         by_index)
        _finalize_axes(ax, geom,
                       f"Vertical levels ({geom['z_iface'].shape[0]} interfaces)",
                       zmax, by_index)
        if inset:
            add_location_inset(fig, geom)
        _save_or_show(fig, outfile, dpi)
        return

    # 5. Validate the field on the first file.
    ds0 = open_mpas_file(timeline[0]['file'])
    if vname not in ds0:
        raise SystemExit(f"\nERROR: variable '{vname}' not found in the file(s).")
    da0 = ds0[vname]
    if 'nVertLevels' not in da0.dims:
        hint = ""
        if vname == 'ter' or ('nCells' in da0.dims and da0.ndim <= 2):
            hint = ("\n       To see the terrain along the transect (it is "
                    "drawn as the filled bottom), use --levels-only.")
        raise SystemExit(
            f"\nERROR: '{vname}' has dims {da0.dims}; a colored cross-section "
            "needs a 3D field on (nCells, nVertLevels). Run without -v to list "
            f"the colorable variables.{hint}")
    has_time = 'Time' in da0.dims
    units = da0.attrs.get('units', '')
    cbar_label = f"{vname} ({units})" if units else vname
    ds0.close()

    # 6. Select the timeline sub-range (inclusive). A field without a Time
    #    dimension is inherently a single frame.
    last = len(timeline) - 1
    lo = 0 if tstart is None else max(0, tstart)
    hi = last if tend is None else min(last, tend)
    if lo > hi:
        raise SystemExit(
            f"\nERROR: time range --tstart {tstart} --tend {tend} is invalid "
            f"for a timeline of {len(timeline)} step(s).")
    selected = timeline[lo:hi + 1]
    if not has_time:
        selected = selected[:1]

    # 7. One consistent color scale across the selected frames (visible part
    #    only when --zmax caps the view).
    visible = None
    if zmax is not None and not by_index:
        z_center = 0.5 * (geom['z_iface'][:-1, :] + geom['z_iface'][1:, :])
        visible = z_center <= zmax
    darrays = []
    for frame in selected:
        ds = open_mpas_file(frame['file'])
        f2d, _ = _field_at_cells(ds, vname, frame['tindex'], geom['cells'])
        darrays.append(f2d[visible] if (visible is not None and visible.any())
                       else f2d)
        ds.close()
    plot_kwargs = set_plot_kwargs(list_darrays=darrays, clip=clip,
                                  cmap=cmap, vmin=vmin, vmax=vmax)

    frame_kw = dict(by_index=by_index, zmax=zmax, extend=extend,
                    cbar_label=cbar_label, u_var=u_var, v_var=v_var,
                    w_var=w_var, wind_stride=wind_stride,
                    wind_lstride=wind_lstride, w_exag=w_exag, show_inset=inset)

    # 8. Single frame -> still image.
    if len(selected) == 1:
        fig, ax = plt.subplots(figsize=(11, 6))
        render_field_frame(ax, fig, selected[0], geom, vname, plot_kwargs,
                           **frame_kw)
        _save_or_show(fig, outfile, dpi)
        return

    # 9. Multiple frames -> animation.
    if outfile is None:
        outfile = 'mpas_xsec_animation.mp4'
    print(f"{len(selected)} time steps selected -> animation: {outfile}  "
          f"(fps={fps}, dpi={dpi})")
    temp_files = []
    for i, frame in enumerate(tqdm(selected, desc="  Frames")):
        fig, ax = plt.subplots(figsize=(11, 6))
        render_field_frame(ax, fig, frame, geom, vname, plot_kwargs, **frame_kw)
        tmp = f'_mpas_xsec_frame_{i:05d}.png'
        fig.savefig(tmp, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        temp_files.append(tmp)
    print("  Combining frames...")
    _stitch_pngs(temp_files, outfile, fps)
    print(f"Saved: {os.path.abspath(outfile)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("-f", "--infile", "--files", dest="infile", type=str,
                        required=True,
                        help="MPAS file or glob pattern (e.g. 'history.*.nc'). "
                             "Several time steps -> animation.")
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

    # Time selection (one step -> still image; several -> animation)
    parser.add_argument("--tstart", "--tmin", dest="tstart", type=int,
                        default=None, help="First timeline index (inclusive)")
    parser.add_argument("--tend", "--tmax", dest="tend", type=int, default=None,
                        help="Last timeline index (inclusive)")
    parser.add_argument("-t", "--time", dest="time", type=int, default=None,
                        help="Single timeline index (shortcut for one still)")
    parser.add_argument("--list-times", action='store_true',
                        help="Print the available time steps and exit")

    # Color
    parser.add_argument("--cmap", type=str, default='Spectral_r',
                        help="Colormap (default: Spectral_r — red = higher)")
    parser.add_argument("--vmin", type=float, default=None,
                        help="Minimum value for the color scale")
    parser.add_argument("--vmax", type=float, default=None,
                        help="Maximum value for the color scale")
    parser.add_argument("-c", "--clip", type=str, default='no',
                        help="Clip extremes at mean +/- 4*std: yes or no")
    parser.add_argument("--extend", type=str, default='both',
                        help="Colorbar extend: both/neither/min/max")

    # Wind overlay (decomposed relative to the transect orientation)
    parser.add_argument("-u", "--u_wind", type=str, default=None,
                        help="Cell-centered zonal wind variable (e.g. "
                             "uReconstructZonal); enables the wind overlay")
    parser.add_argument("-v_wind", "--v_wind", type=str, default=None,
                        help="Cell-centered meridional wind variable (e.g. "
                             "uReconstructMeridional)")
    parser.add_argument("-w", "--w_wind", type=str, default=None,
                        help="Vertical velocity variable (e.g. w); tilts the "
                             "in-plane arrows")
    parser.add_argument("--w-exag", type=float, default=100.0,
                        help="Vertical exaggeration applied to w for the arrow "
                             "tilt (default: 100; qualitative)")
    parser.add_argument("--wind-stride", type=int, default=None,
                        help="Plot a wind symbol every Nth column (default: "
                             "auto, ~30 across)")
    parser.add_argument("--wind-lstride", type=int, default=3,
                        help="Plot a wind symbol every Nth level (default: 3)")

    parser.add_argument("--no-inset", action='store_true',
                        help="Do not draw the location mini-map inset")

    # Animation / output
    parser.add_argument("--fps", type=int, default=5,
                        help="Animation frames per second (default: 5)")
    parser.add_argument("--dpi", type=int, default=150,
                        help="Output resolution (default: 150)")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not glob.glob(args.infile) and not os.path.exists(args.infile):
        raise SystemExit(f"\nERROR: no file matches: {args.infile}")

    # -t is a shortcut for a single still image.
    tstart, tend = args.tstart, args.tend
    if args.time is not None:
        tstart = tend = args.time

    run(infile=args.infile,
        vname=args.var,
        gridfile=args.gridfile,
        outfile=args.outfile,
        start=args.start, end=args.end, lat=args.lat, lon=args.lon,
        npoints=args.npoints,
        levels_only=args.levels_only,
        by_index=args.by_index,
        tstart=tstart, tend=tend, list_times=args.list_times,
        zmax=args.zmax,
        cmap=args.cmap, vmin=args.vmin, vmax=args.vmax,
        clip=_yn(args.clip), extend=args.extend,
        u_var=args.u_wind, v_var=args.v_wind, w_var=args.w_wind,
        wind_stride=args.wind_stride, wind_lstride=args.wind_lstride,
        w_exag=args.w_exag, inset=not args.no_inset, fps=args.fps,
        dpi=args.dpi)


if __name__ == "__main__":
    main()
