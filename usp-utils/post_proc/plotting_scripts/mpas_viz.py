#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified visualization framework for scalar (and optional vector) fields on
native MPAS grids — no regridding required.

A single tool that PLOTS a still image when one time step is selected, or
ANIMATES when more than one is selected. Both modes share the same options, so
a useful flag (mask-land, custom color scale, wind vectors, ...) automatically
works for plots and animations alike.

Time model
----------
All input files are expanded into a single, ordered "timeline" of
(file, time_index) entries. Use ``--list-times`` to inspect it and
``--tstart/--tend`` (inclusive, global indices) to select a sub-range:

  * 1 selected step  -> still image (.png/.pdf/...)
  * >1 selected steps -> animation (.mp4/.gif)

This works both for many single-step files (e.g. ``history.*.nc``) and for a
single file that holds several time steps (e.g. ``x1.*.sfc_update.nc``).

Usage examples
--------------
  # List plottable variables
  python mpas_viz.py -f x1.10242.sfc_update.nc

  # List available time steps
  python mpas_viz.py -f x1.10242.sfc_update.nc --list-times

  # Still map of SST, masking land (grid connectivity + landmask from static)
  python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
      -g no -ml yes -o sst.png

  # Animate SST over all 6 steps of a single multi-time file
  python mpas_viz.py -f x1.10242.sfc_update.nc -v sst -gf x1.10242.static.nc \
      -g no --tstart 0 --tend 5 -o sst.gif

  # Animate surface pressure across many history files, in parallel
  python mpas_viz.py -f "history.*.nc" -v surface_pressure -j 4 -o mslp.mp4

  # Wind vectors over potential temperature at a vertical level
  python mpas_viz.py -f "history.*.nc" -v theta -l 10 \
      -u uReconstructZonal -v_wind uReconstructMeridional -o wind.mp4

History
-------
Unifies the former ``mpas_plot.py`` (still maps) and ``mpas_animate.py``
(animations) into one framework. Originally adapted by Danilo Couto de Souza
(2023), with edits by P. Peixoto, F.A.V.B. Alves and G. Torres Mendonça.
Unified framework: Danilo Couto de Souza (2026).
"""

import math
import os
import glob
import argparse
from multiprocessing import Pool, cpu_count

import xarray as xr
import numpy as np

import matplotlib as mpl
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

from tqdm import tqdm


# Variables we can derive on the fly from raw MPAS mesh variables.
derived_variables = {
    'latCell': ['latitude'],
    'lonCell': ['longitude'],
    'latVertex': ['latitudeVertex'],
    'lonVertex': ['longitudeVertex'],
    'areaCell': ['area', 'resolution'],
}


# ---------------------------------------------------------------------------
# Dataset / mesh helpers
# ---------------------------------------------------------------------------
def add_mpas_mesh_variables(ds, full=True, **kwargs):
    """Add derived geometric variables (lat/lon in degrees, area, resolution)."""
    for v in ds.data_vars:
        if v not in derived_variables:
            continue

        newvs = derived_variables[v]

        for newv in newvs:
            if newv in ds:
                continue

            if 'lat' in v or 'lon' in v:
                ds[newv] = xr.apply_ufunc(np.rad2deg, ds[v])
                ds[newv] = ds[newv].where(ds[newv] <= 180.0, ds[newv] - 360.0)
                ds[newv].attrs['units'] = 'degrees'

            elif newv == 'area':
                radius_circle = ds.attrs.get('sphere_radius', 1.0)
                if radius_circle == 1:
                    correction_rad_earth = 6371220.0
                else:
                    correction_rad_earth = 1

                ds[newv] = (ds[v] / 10 ** 6) * correction_rad_earth**2
                ds[newv].attrs['units'] = 'km^2 (assuming areaCell in m^2)'
                ds[newv].attrs['long_name'] = 'Area of the cell in km^2'

            elif newv == 'resolution':
                radius_circle = ds.attrs.get('sphere_radius', 1.0)
                if radius_circle == 1.0:
                    correction_rad_earth = 6371220.0
                else:
                    correction_rad_earth = 1

                area = (ds[v] / 10 ** 6) * correction_rad_earth**2
                ds[newv] = 2 * (xr.apply_ufunc(np.sqrt, area / math.pi))
                ds[newv].attrs['units'] = 'km'
                ds[newv].attrs['long_name'] = 'Resolution of the cell (approx)'

    return ds


def open_mpas_file(file, **kwargs):
    """Open an MPAS NetCDF file and add the derived mesh variables."""
    ds = xr.open_dataset(file)
    ds = add_mpas_mesh_variables(ds, **kwargs)
    return ds


def list_plottable_variables(ds):
    """Names of variables this tool can draw (defined on cells or vertices)."""
    plottable = []
    for v in ds.data_vars:
        dims = ds[v].dims
        if 'nCells' in dims or 'nVertices' in dims:
            plottable.append(str(v))
    return sorted(plottable)


def format_variables_table(ds):
    """Pretty, aligned table of plottable variables to help the user pick one."""
    variables = list_plottable_variables(ds)

    if not variables:
        return ("No plottable variables (with 'nCells' or 'nVertices' "
                "dimension) were found in this file.")

    def extra_dims(v):
        dims = ds[v].dims
        marks = []
        if 'Time' in dims:
            marks.append('Time')
        if 'nVertLevels' in dims:
            marks.append('Level')
        return ', '.join(marks) if marks else '-'

    def grid_type(v):
        dims = ds[v].dims
        if 'nCells' in dims:
            return 'cells'
        if 'nVertices' in dims:
            return 'vertices'
        return '-'

    MAX_LONGNAME = 45

    rows = []
    for v in variables:
        attrs = ds[v].attrs
        long_name = str(attrs.get('long_name', '') or '-')
        if len(long_name) > MAX_LONGNAME:
            long_name = long_name[:MAX_LONGNAME - 1] + '…'
        units = str(attrs.get('units', '') or '-')
        rows.append([v, long_name, units, grid_type(v), extra_dims(v)])

    headers = ['Variable', 'Long name', 'Units', 'Grid', 'Extra dims']
    return _render_table(f"Available plottable variables ({len(rows)})",
                         headers, rows,
                         footer="Pick one with: -v/--var <Variable>")


def _render_table(title, headers, rows, footer=None):
    """Render an aligned box-drawing table (shared by variable/time listings)."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def make_rule(left, mid, right):
        return left + mid.join('─' * (w + 2) for w in widths) + right

    def make_row(cells):
        return ('│ '
                + ' │ '.join(str(c).ljust(widths[i]) for i, c in enumerate(cells))
                + ' │')

    lines = [f"\n{title}:\n", make_rule('┌', '┬', '┐'), make_row(headers),
             make_rule('├', '┼', '┤')]
    for row in rows:
        lines.append(make_row(row))
    lines.append(make_rule('└', '┴', '┘'))
    if footer:
        lines.append("\n" + footer)
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Map / colorbar helpers
# ---------------------------------------------------------------------------
def add_cartopy_details(ax, zorder=1, show_coastlines=True):
    """Add coastlines (optional) and reference gridlines to a map axis."""
    if show_coastlines:
        ax.coastlines(resolution='10m', zorder=zorder + 1, linewidth=0.1)

    gl = ax.gridlines(draw_labels=True, alpha=0.5, linestyle='--',
                      zorder=zorder + 2, linewidth=0.5)
    gl.top_labels = False
    gl.right_labels = False


def get_vim_vmax(da, clip=False):
    """Return sensible vmin/vmax for ``da`` (symmetric around 0 when signed)."""
    truemaxval = da.max().values
    trueminval = da.min().values

    if (trueminval <= 0) and (truemaxval > 0):
        if truemaxval > abs(trueminval):
            slice = da.values[da.values > 0]
        else:
            slice = -da.values[da.values <= 0]
        sigma = np.std(slice)
        m = np.mean(slice)
        if clip:
            maxval = min(truemaxval, m + 4 * sigma)
        else:
            maxval = truemaxval
        minval = -maxval

    elif (truemaxval >= 0):
        minval = trueminval
        sigma = np.std(da.values)
        m = np.mean(da.values)
        if clip:
            maxval = min(truemaxval, m + 4 * sigma)
        else:
            maxval = truemaxval
    else:
        maxval = truemaxval
        sigma = np.std(da.values)
        m = np.mean(da.values)
        if clip:
            minval = max(trueminval, m - 4 * sigma)
        else:
            minval = trueminval

    return minval, maxval


def set_plot_kwargs(da=None, clip=False, list_darrays=None, **kwargs):
    """Build {cmap, vmin, vmax}, honoring user overrides or deriving from data.

    Pass ``da`` for a single field, or ``list_darrays`` to fix one consistent
    color scale across many fields (animation frames).
    """
    plot_kwargs = {k: v for k, v in kwargs.items()
                   if k in ['cmap', 'vmin', 'vmax']
                   and v is not None}

    if 'cmap' not in plot_kwargs:
        plot_kwargs['cmap'] = 'Spectral'

    vmin = plot_kwargs.get('vmin', None)
    if vmin is None:
        if da is not None:
            vmin, _ = get_vim_vmax(da, clip)
        elif list_darrays is not None:
            vmin = np.min([v.min() for v in list_darrays if v is not None])
    if vmin is not None:
        plot_kwargs['vmin'] = vmin

    vmax = plot_kwargs.get('vmax', None)
    if vmax is None:
        if da is not None:
            _, vmax = get_vim_vmax(da, clip)
        elif list_darrays is not None:
            vmax = np.max([v.max() for v in list_darrays if v is not None])
    if vmax is not None:
        plot_kwargs['vmax'] = vmax

    return plot_kwargs


def colorvalue(val, da, vmin=None, vmax=None, cmap='Spectral'):
    """Map a scalar value to an RGBA color given the colormap and range."""
    cm = mpl.colormaps[cmap]
    if vmin is None:
        vmin = da.min().values
    if vmax is None:
        vmax = da.max().values

    if vmin == vmax:
        norm_val = mpl.colors.Normalize(vmin=vmin - 1, vmax=vmax + 1, clip=True)(val)
    else:
        norm_val = mpl.colors.Normalize(vmin=vmin, vmax=vmax, clip=True)(val)

    return cm(norm_val)


def add_colorbar(axs, fig=None, label=None, extend='both', **plot_kwargs):
    """Attach a colorbar built from the fixed vmin/vmax to the figure."""
    if fig is None:
        fig = plt.gcf()

    try:
        x = axs[0, 0]
    except Exception:
        try:
            x = axs[0]
            n = len(axs)
        except Exception:
            axs = np.array([axs]).reshape([1, 1])
        else:
            axs = axs.reshape([n, 1])

    cbar = fig.colorbar(
        mpl.cm.ScalarMappable(
            norm=mpl.colors.Normalize(vmin=plot_kwargs['vmin'],
                                      vmax=plot_kwargs['vmax'], clip=True),
            cmap=plot_kwargs['cmap']),
        ax=axs[:, :], shrink=0.6, extend=extend)
    cbar.ax.locator_params(nbins=10)
    if label is not None:
        cbar.set_label(label)

    return


# ---------------------------------------------------------------------------
# Variable operations
# ---------------------------------------------------------------------------
def sum_variables(ds, var1, var2, new_var_name=None):
    """Add two dataset variables, returning (ds, new_var_name)."""
    if var1 not in ds.data_vars or var2 not in ds.data_vars:
        raise ValueError(f"Variables {var1} or {var2} not found in dataset")

    if new_var_name is None:
        new_var_name = f"{var1}_plus_{var2}"

    ds[new_var_name] = ds[var1] + ds[var2]
    ds[new_var_name].attrs = ds[var1].attrs.copy()
    ds[new_var_name].attrs['long_name'] = f"{var1} + {var2}"

    return ds, new_var_name


# ---------------------------------------------------------------------------
# Cell / vertex rendering (single shared renderer)
# ---------------------------------------------------------------------------
def _resolve_grid(ds, gridfile, grid_properties):
    """Return a dataset that carries the mesh connectivity, with friendly errors.

    Looks in ``ds`` first, then in the user-supplied ``-gf/--gridfile``.
    """
    if set(grid_properties).issubset(set(ds.keys())):
        return ds

    if gridfile is None:
        raise SystemExit(
            "\nERROR: this file does not contain the mesh connectivity "
            f"({', '.join(grid_properties)}), which is required to plot it.\n"
            "       Supply a grid/static/init file with -gf/--gridfile, e.g.:\n"
            "           -gf x1.10242.grid.nc\n"
            "       (note: -g/--grid is the yes/no flag for drawing cell "
            "edges, NOT the grid file).")

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

    if not set(grid_properties).issubset(set(ds_grid.keys())):
        raise SystemExit(
            f"\nERROR: the grid file '{gridfile}' does not contain the "
            f"required mesh connectivity ({', '.join(grid_properties)}).\n"
            "       Use a proper MPAS grid/static/init file (e.g. "
            "x1.<nCells>.static.nc).")

    return ds_grid


def _resolve_landmask(ds, ds_grid, mask_land):
    """Return a (nCells,) landmask DataArray (1=land) or None when not masking."""
    if not mask_land:
        return None

    landmask = None
    if 'landmask' in ds:
        landmask = ds['landmask']
    elif 'landmask' in ds_grid:
        landmask = ds_grid['landmask']
    else:
        print("WARNING  --mask-land requested but no 'landmask' variable was "
              "found in the data or grid file. Supply a static/init file with "
              "-gf (e.g. -gf x1.<nCells>.static.nc) to mask land. Plotting all "
              "cells.")
        return None

    if 'Time' in landmask.dims:
        landmask = landmask.isel(Time=0)
    return landmask


def plot_cells_mpas(da, ds, ax, plotEdge=True, gridfile=None, mask_land=False,
                    show_progress=True, **plot_kwargs):
    """Fill the Voronoi cells (``nCells``) with the field ``da``.

    plotEdge   : draw cell edges (nicer on coarse meshes, slower on fine ones).
    gridfile   : file providing mesh connectivity when ``ds`` lacks it.
    mask_land  : skip land cells (uses 'landmask'; 1=land) — for ocean fields.
    show_progress : show a per-cell tqdm bar (off for animation workers).
    """
    grid_properties = ['verticesOnCell', 'nEdgesOnCell']
    ds_grid = _resolve_grid(ds, gridfile, grid_properties)
    landmask = _resolve_landmask(ds, ds_grid, mask_land)

    cells = ds['nCells'].values
    iterator = tqdm(cells, desc="    Plotting cells", leave=False) \
        if show_progress else cells

    for cell in iterator:
        # Skip land cells when masking is enabled (landmask == 1 over land)
        if landmask is not None and landmask.sel(nCells=cell).item() == 1:
            continue

        value = da.sel(nCells=cell)
        vertices = ds_grid['verticesOnCell'].sel(nCells=cell).values
        num_sides = int(ds_grid['nEdgesOnCell'].sel(nCells=cell))

        if 0 in vertices[:num_sides]:
            continue  # Border cell

        # MPAS connectivity is 1-based; xarray indexing is 0-based.
        vertices = vertices[:num_sides] - 1
        lats = ds_grid['latitudeVertex'].sel(nVertices=vertices)
        lons = ds_grid['longitudeVertex'].sel(nVertices=vertices)

        color = colorvalue(value, da, vmin=plot_kwargs['vmin'],
                           vmax=plot_kwargs['vmax'],
                           cmap=plot_kwargs.get('cmap', 'Spectral'))

        # Wrap polygons that straddle the +/-180 antimeridian.
        if lons.max().item() > 170 and lons.min().item() < -170:
            lons = xr.where(lons >= 170.0, lons - 360.0, lons)

        if plotEdge:
            edgecolor, lw = 'grey', 0.1
        else:
            edgecolor, lw = None, None

        ax.fill(lons, lats, edgecolor=edgecolor, linewidth=lw, facecolor=color)

    return


def plot_dual_mpas(da, ds, ax, plotEdge=True, show_progress=True, **plot_kwargs):
    """Fill the dual triangular mesh (``nVertices``) with the field ``da``."""
    vertices_iter = ds['nVertices'].values
    iterator = tqdm(vertices_iter, desc="    Plotting triangles", leave=False) \
        if show_progress else vertices_iter

    for vertex in iterator:
        value = da.sel(nVertices=vertex)
        cells = ds['cellsOnVertex'].sel(nVertices=vertex).values

        if 0 in cells:
            continue  # Border triangle

        cells = cells - 1
        lats = ds['latitude'].sel(nCells=cells)
        lons = ds['longitude'].sel(nCells=cells)

        color = colorvalue(value, da, vmin=plot_kwargs['vmin'],
                           vmax=plot_kwargs['vmax'],
                           cmap=plot_kwargs.get('cmap', 'Spectral'))

        if lons.max().item() > 170 and lons.min().item() < -170:
            lons = xr.where(lons >= 170.0, lons - 360.0, lons)

        if plotEdge:
            edgecolor, lw = 'grey', 0.1
        else:
            edgecolor, lw = None, None

        ax.fill(lons, lats, edgecolor=edgecolor, linewidth=lw, facecolor=color)

    return


def add_wind_vectors(ax, ds, u_da, v_da, stride=10, scale=None):
    """Overlay wind vectors (quiver) at cell centers, every ``stride``-th cell."""
    lats = ds['latitude'].values[::stride]
    lons = ds['longitude'].values[::stride]
    u = u_da.values[::stride]
    v = v_da.values[::stride]

    mask = ~(np.isnan(u) | np.isnan(v))
    lats, lons, u, v = lats[mask], lons[mask], u[mask], v[mask]

    if scale is None:
        scale = np.nanmax(np.sqrt(u**2 + v**2)) * 50

    ax.quiver(lons, lats, u, v, transform=ccrs.PlateCarree(),
              scale=scale, width=0.002, headwidth=3, headlength=4,
              color='black', alpha=0.7, zorder=10)


# ---------------------------------------------------------------------------
# Timeline (global ordered list of (file, time_index) frames)
# ---------------------------------------------------------------------------
def _decode_xtime(xtime_value):
    """Decode an MPAS xtime entry (bytes char array or str) to a clean string."""
    if isinstance(xtime_value, bytes):
        s = xtime_value.decode('utf-8', errors='ignore')
    elif isinstance(xtime_value, np.ndarray):
        s = b''.join(np.atleast_1d(xtime_value).astype('S1').tolist()).decode(
            'utf-8', errors='ignore')
    else:
        s = str(xtime_value)
    return s.strip().strip('\x00').strip()


def expand_files(file_pattern):
    """Resolve ``file_pattern`` into a sorted list of existing files."""
    files = sorted(glob.glob(file_pattern))
    if not files and os.path.exists(file_pattern):
        files = [file_pattern]
    if not files:
        raise FileNotFoundError(
            f"No files found matching pattern: {file_pattern}")
    return files


def build_timeline(file_pattern):
    """Expand all input files into an ordered list of timeline frames.

    Returns a list of dicts: {'file', 'tindex', 'xtime', 'gindex'} where
    ``tindex`` is the Time index within the file and ``gindex`` is the global
    position in the timeline.
    """
    files = expand_files(file_pattern)
    timeline = []

    for file in files:
        ds = xr.open_dataset(file)
        try:
            ntimes = ds.sizes.get('Time', 1) if 'Time' in ds.dims else 1
            xtimes = None
            if 'xtime' in ds.variables:
                try:
                    xtimes = [_decode_xtime(x) for x in ds['xtime'].values]
                except Exception:
                    xtimes = None
            for t in range(ntimes):
                if xtimes is not None and t < len(xtimes):
                    label = xtimes[t]
                else:
                    label = f"t={t}"
                timeline.append({'file': file, 'tindex': t, 'xtime': label})
        finally:
            ds.close()

    for gi, frame in enumerate(timeline):
        frame['gindex'] = gi

    return timeline


def format_timeline_table(timeline):
    """Pretty table of the global timeline for ``--list-times``."""
    if not timeline:
        return "No time steps found."

    rows = [[f['gindex'], os.path.basename(f['file']), f['tindex'], f['xtime']]
            for f in timeline]
    headers = ['Index', 'File', 'Time idx', 'xtime']
    return _render_table(f"Available time steps ({len(rows)})", headers, rows,
                         footer="Select a range with: --tstart <i> --tend <j> "
                                "(inclusive)")


# ---------------------------------------------------------------------------
# Frame extraction (shared by still plots and animation frames)
# ---------------------------------------------------------------------------
def load_frame(frame, vname, level=None, sum_vars=None, deaccumulate=False,
               prev_frame=None):
    """Open a timeline frame and return (da, ds) ready to plot.

    Handles --sum-vars, time/level selection and --deaccumulate (difference
    against ``prev_frame``). ``ds`` is returned for grid lookup / units.
    """
    ds = open_mpas_file(frame['file'])

    if sum_vars is not None:
        var1, var2 = (s.strip() for s in sum_vars.split('+'))
        ds, vname = sum_variables(ds, var1, var2, new_var_name=vname or None)

    da = ds[vname].isel(Time=frame['tindex']) if 'Time' in ds[vname].dims \
        else ds[vname]

    if deaccumulate and prev_frame is not None:
        ds_prev = open_mpas_file(prev_frame['file'])
        if sum_vars is not None:
            var1, var2 = (s.strip() for s in sum_vars.split('+'))
            ds_prev, _ = sum_variables(ds_prev, var1, var2, new_var_name=vname)
        da_prev = ds_prev[vname].isel(Time=prev_frame['tindex']) \
            if 'Time' in ds_prev[vname].dims else ds_prev[vname]
        da = da - da_prev
        ds_prev.close()

    if level is not None and 'nVertLevels' in da.dims:
        da = da.isel(nVertLevels=level)

    return da, ds, vname


# ---------------------------------------------------------------------------
# Single-frame rendering (used by still image AND each animation frame)
# ---------------------------------------------------------------------------
def render_one_frame(ax, frame, vname, plot_kwargs, *, fig=None,
                     level=None, gridfile=None, mask_land=False,
                     plotEdge=True, show_coastlines=True, show_progress=True,
                     u_var=None, v_var=None, stride=15,
                     sum_vars=None, deaccumulate=False, prev_frame=None,
                     lat_min=None, lat_max=None, lon_min=None, lon_max=None,
                     extend='both', add_cbar=True):
    """Draw one timeline frame onto ``ax`` (cells/vertices, wind, title, cbar)."""
    ax.clear()
    add_cartopy_details(ax, zorder=2, show_coastlines=show_coastlines)

    if (lat_min is not None and lat_max is not None and
            lon_min is not None and lon_max is not None):
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    else:
        ax.set_extent([-180.0, 180, -90.0, 90.0], crs=ccrs.PlateCarree())

    da, ds, vname = load_frame(frame, vname, level=level, sum_vars=sum_vars,
                               deaccumulate=deaccumulate, prev_frame=prev_frame)

    if 'nCells' in da.dims:
        plot_cells_mpas(da, ds, ax, plotEdge, gridfile=gridfile,
                        mask_land=mask_land, show_progress=show_progress,
                        **plot_kwargs)
    elif 'nVertices' in da.dims:
        plot_dual_mpas(da, ds, ax, plotEdge, show_progress=show_progress,
                       **plot_kwargs)
    else:
        print(f"WARNING  cannot plot variable with dimensions {da.dims}")
        ds.close()
        return

    if u_var is not None and v_var is not None \
            and u_var in ds.data_vars and v_var in ds.data_vars:
        u_frame = ds[u_var].isel(Time=frame['tindex']) \
            if 'Time' in ds[u_var].dims else ds[u_var]
        v_frame = ds[v_var].isel(Time=frame['tindex']) \
            if 'Time' in ds[v_var].dims else ds[v_var]
        if level is not None and 'nVertLevels' in u_frame.dims:
            u_frame = u_frame.isel(nVertLevels=level)
            v_frame = v_frame.isel(nVertLevels=level)
        add_wind_vectors(ax, ds, u_frame, v_frame, stride=stride)

    title = f'{vname}'
    if level is not None and 'nVertLevels' in ds[vname].dims:
        title += f' (level {level})'
    title += f"\n{frame['xtime']}"
    ax.set_title(title, fontsize=12)

    if add_cbar:
        units = ds[vname].attrs.get('units', '')
        add_colorbar(ax, fig=fig, label=f'{vname} ({units})', extend=extend,
                     **plot_kwargs)

    ds.close()


def _render_frame_to_png(args):
    """Worker: render one frame to a temporary PNG (for parallel animation)."""
    (idx, frame, prev_frame, vname, plot_kwargs, kw, dpi) = args

    fig = plt.figure(figsize=(12, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())
    render_one_frame(ax, frame, vname, plot_kwargs, fig=fig,
                     prev_frame=prev_frame, show_progress=False, **kw)
    temp_file = f'_mpas_viz_frame_{idx:05d}.png'
    fig.savefig(temp_file, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return temp_file


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def _stitch_pngs(temp_files, outfile, fps):
    """Combine rendered PNG frames into a .gif or .mp4 and clean up temps."""
    if outfile.endswith('.gif'):
        from PIL import Image
        # Load each frame inside a context manager and keep an in-memory copy,
        # so the file descriptors are released promptly (many frames would
        # otherwise exhaust the OS file-descriptor limit).
        images = []
        for f in temp_files:
            with Image.open(f) as im:
                images.append(im.copy())
        images[0].save(outfile, save_all=True, append_images=images[1:],
                       duration=int(1000 / fps), loop=0, optimize=False)
    else:
        try:
            import imageio
            with imageio.get_writer(outfile, fps=fps) as writer:
                for f in tqdm(temp_files, desc="  Writing video"):
                    writer.append_data(imageio.imread(f))
        except ImportError:
            import subprocess
            listfile = '_mpas_viz_filelist.txt'
            with open(listfile, 'w') as f:
                for img in temp_files:
                    f.write(f"file '{img}'\nduration {1.0 / fps}\n")
            subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i',
                            listfile, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                            outfile, '-y'], check=True)
            os.remove(listfile)

    for f in temp_files:
        os.remove(f)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run(file_pattern, vname=None, outfile=None,
        level=None, tstart=None, tend=None, list_times=False,
        gridfile=None, plotEdge=True, mask_land=False, clip=False,
        cmap='Spectral', vmin=None, vmax=None, extend='both',
        lat_min=None, lat_max=None, lon_min=None, lon_max=None,
        show_coastlines=True, u_var=None, v_var=None, stride=15,
        sum_vars=None, deaccumulate=False,
        fps=5, dpi=150, n_jobs=1):
    """Plot a still image or an animation depending on the selected time range."""

    # 1. Build the global timeline.
    timeline = build_timeline(file_pattern)

    # 2. Just list times?
    if list_times:
        print("Files:", file_pattern)
        print(format_timeline_table(timeline))
        return

    # 3. No variable (and no sum): list plottable variables and exit.
    if vname is None and sum_vars is None:
        ds0 = open_mpas_file(timeline[0]['file'])
        print("File:", timeline[0]['file'])
        print(format_variables_table(ds0))
        ds0.close()
        return

    # 4. Select the timeline sub-range (inclusive on both ends). Indices are
    #    clamped to the valid range so legacy '--tmax N' (which used to be an
    #    exclusive slice bound and could equal/exceed the count) still works.
    last = len(timeline) - 1
    lo = 0 if tstart is None else max(0, tstart)
    hi = last if tend is None else min(last, tend)
    if lo > hi:
        raise SystemExit(
            f"\nERROR: time range --tstart {tstart} --tend {tend} is invalid "
            f"for a timeline of {len(timeline)} step(s) (valid indices "
            f"0..{last}). Use --list-times to inspect them.")
    selected = timeline[lo:hi + 1]

    # 5. Consistent color scale across the selected frames.
    print(f"Loading {len(selected)} time step(s) to set the color scale...")
    darrays = []
    for i, frame in enumerate(tqdm(selected, desc="Scanning frames")):
        prev = selected[i - 1] if (deaccumulate and i > 0) else None
        da, ds, vname = load_frame(frame, vname, level=level, sum_vars=sum_vars,
                                   deaccumulate=deaccumulate, prev_frame=prev)
        darrays.append(da.load())
        ds.close()

    plot_kwargs = set_plot_kwargs(da=None, clip=clip, list_darrays=darrays,
                                  cmap=cmap, vmin=vmin, vmax=vmax)

    # Shared per-frame rendering kwargs.
    frame_kw = dict(level=level, gridfile=gridfile, mask_land=mask_land,
                    plotEdge=plotEdge, show_coastlines=show_coastlines,
                    u_var=u_var, v_var=v_var, stride=stride,
                    sum_vars=sum_vars, deaccumulate=deaccumulate,
                    lat_min=lat_min, lat_max=lat_max,
                    lon_min=lon_min, lon_max=lon_max, extend=extend)

    # 6. Single frame -> still image.
    if len(selected) == 1:
        print(f"Single time step selected -> still image.")
        fig = plt.figure(figsize=(10, 8))
        ax = plt.axes(projection=ccrs.PlateCarree())
        render_one_frame(ax, selected[0], vname, plot_kwargs, fig=fig,
                         show_progress=True, prev_frame=None, **frame_kw)
        if outfile is not None:
            fig.savefig(outfile, dpi=dpi if dpi else 800, bbox_inches='tight')
            print(f"Saved: {os.path.abspath(outfile)}")
        else:
            plt.show()
        plt.close(fig)
        return

    # 7. Multiple frames -> animation.
    if outfile is None:
        outfile = 'mpas_animation.mp4'
    print(f"{len(selected)} time steps selected -> animation: {outfile}")
    print(f"  Color scale: vmin={plot_kwargs['vmin']:.3e}, "
          f"vmax={plot_kwargs['vmax']:.3e}  cmap={plot_kwargs['cmap']}  "
          f"fps={fps}  dpi={dpi}")

    prev_frames = [None] + selected[:-1] if deaccumulate else [None] * len(selected)

    if n_jobs and n_jobs != 1:
        if n_jobs == -1:
            n_jobs = cpu_count()
        print(f"  Rendering frames in parallel with {n_jobs} workers...")
        args_list = [(i, selected[i], prev_frames[i], vname, plot_kwargs,
                      frame_kw, dpi) for i in range(len(selected))]
        with Pool(processes=n_jobs) as pool:
            temp_files = list(tqdm(pool.imap(_render_frame_to_png, args_list),
                                   total=len(selected), desc="  Frames"))
    else:
        print("  Rendering frames sequentially (use -j >1 for speedup)...")
        temp_files = []
        for i, frame in enumerate(tqdm(selected, desc="  Frames")):
            temp_files.append(_render_frame_to_png(
                (i, frame, prev_frames[i], vname, plot_kwargs, frame_kw, dpi)))

    print("  Combining frames...")
    _stitch_pngs(temp_files, outfile, fps)
    print(f"Saved: {os.path.abspath(outfile)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _yn(value):
    return str(value).lower() in ['yes', 'y', 'true', '1']


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    # Input / output
    parser.add_argument("-f", "--infile", "--files", dest="infile", type=str,
                        required=True,
                        help="MPAS file or glob pattern (e.g. 'history.*.nc')")
    parser.add_argument("-o", "--outfile", type=str, default=None,
                        help="Output file. Image (.png/.pdf) for one step; "
                             "video (.mp4/.gif) for many. Omit to show a still "
                             "interactively.")
    parser.add_argument("-v", "--var", type=str, default=None,
                        help="Variable to plot. Omit (without --sum-vars) to "
                             "list available variables and exit.")

    # Variable operations
    parser.add_argument("--sum-vars", type=str, default=None,
                        help="Sum two variables, e.g. 'rainc+rainnc'")
    parser.add_argument("--deaccumulate", action='store_true',
                        help="Plot differences between consecutive steps "
                             "(accumulated field -> rate)")
    parser.add_argument("-l", "--level", type=int, default=None,
                        help="Vertical level (for 3D fields)")

    # Time selection
    parser.add_argument("--tstart", "--tmin", dest="tstart", type=int,
                        default=None, help="First timeline index (inclusive)")
    parser.add_argument("--tend", "--tmax", dest="tend", type=int, default=None,
                        help="Last timeline index (inclusive)")
    parser.add_argument("-t", "--time", dest="time", type=int, default=None,
                        help="Single timeline index (shortcut for one still "
                             "image)")
    parser.add_argument("--list-times", action='store_true',
                        help="Print the available time steps and exit")

    # Mesh / mask
    parser.add_argument("-gf", "--gridfile", type=str, default=None,
                        help="File providing mesh connectivity if infile lacks "
                             "it (grid/static/init .nc)")
    parser.add_argument("-g", "--grid", type=str, default='yes',
                        help="Draw cell edges: yes or no")
    parser.add_argument("-ml", "--mask-land", type=str, default='no',
                        help="Hide cells over land: yes or no (uses 'landmask'; "
                             "for ocean-only fields like sst)")

    # Color
    parser.add_argument("-c", "--clip", type=str, default='no',
                        help="Clip extremes at mean +/- 4*std: yes or no")
    parser.add_argument("--cmap", type=str, default='Spectral',
                        help="Colormap (default: Spectral)")
    parser.add_argument("--vmin", type=float, default=None,
                        help="Minimum value for the color scale")
    parser.add_argument("--vmax", type=float, default=None,
                        help="Maximum value for the color scale")
    parser.add_argument("--extend", type=str, default='both',
                        help="Colorbar extend: both/neither/min/max")

    # Map extent / features
    parser.add_argument("-lat_min", type=float, default=None)
    parser.add_argument("-lat_max", type=float, default=None)
    parser.add_argument("-lon_min", type=float, default=None)
    parser.add_argument("-lon_max", type=float, default=None)
    parser.add_argument("--no-coastlines", action='store_true',
                        help="Hide coastlines")

    # Wind vectors
    parser.add_argument("-u", "--u_wind", type=str, default=None,
                        help="U (zonal) wind component variable (optional)")
    parser.add_argument("-v_wind", "--v_wind", type=str, default=None,
                        help="V (meridional) wind component variable (optional)")
    parser.add_argument("--stride", type=int, default=15,
                        help="Plot every Nth wind vector (default: 15)")

    # Animation
    parser.add_argument("--fps", type=int, default=5,
                        help="Frames per second (default: 5)")
    parser.add_argument("--dpi", type=int, default=150,
                        help="Output resolution (default: 150)")
    parser.add_argument("-j", "--jobs", type=int, default=1,
                        help="Parallel frame workers (default: 1; -1 = all CPUs)")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not glob.glob(args.infile) and not os.path.exists(args.infile):
        raise SystemExit(f"\nERROR: no file matches: {args.infile}")

    # -g/--grid only accepts yes/no; catch the common "passed a file here" slip.
    if args.grid not in ['yes', 'Yes', 'Y', 'y', 'no', 'No', 'N', 'n']:
        raise SystemExit(
            f"\nERROR: -g/--grid only accepts yes/no (draw cell edges), but got "
            f"'{args.grid}'.\n"
            "       If you meant to pass a grid file, use -gf/--gridfile:\n"
            f"           -gf {args.grid}")

    # -t is a shortcut for a single still image.
    tstart, tend = args.tstart, args.tend
    if args.time is not None:
        tstart = tend = args.time

    run(file_pattern=args.infile,
        vname=args.var,
        outfile=args.outfile,
        level=args.level,
        tstart=tstart,
        tend=tend,
        list_times=args.list_times,
        gridfile=args.gridfile,
        plotEdge=_yn(args.grid),
        mask_land=_yn(args.mask_land),
        clip=_yn(args.clip),
        cmap=args.cmap,
        vmin=args.vmin,
        vmax=args.vmax,
        extend=args.extend,
        lat_min=args.lat_min, lat_max=args.lat_max,
        lon_min=args.lon_min, lon_max=args.lon_max,
        show_coastlines=not args.no_coastlines,
        u_var=args.u_wind, v_var=args.v_wind, stride=args.stride,
        sum_vars=args.sum_vars, deaccumulate=args.deaccumulate,
        fps=args.fps, dpi=args.dpi, n_jobs=args.jobs)


if __name__ == "__main__":
    main()
