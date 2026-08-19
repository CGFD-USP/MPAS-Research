#!/usr/bin/env python
#
#  Basic module to creat spherical grids for MPAS-Atmosphere
#  by Pedro S. Peixoto Dec 2021 <ppeixoto@usp.br>
#
#  Based on 
#  http://mpas-dev.github.io/MPAS-Tools/stable/mesh_creation.html#spherical-meshes
#  and Jigsaw scripts: https://github.com/dengwirda/jigsaw-python/tree/master/tests
  

import numpy as np
import argparse
import os
import glob
import numpy as np
import subprocess
import matplotlib.pyplot as plt

#from mpas_tools.ocean import build_spherical_mesh
#from scipy import interpolate

import jigsawpy as jig

import xarray

from mpas_tools.mesh.creation.jigsaw_to_netcdf import jigsaw_to_netcdf
from mpas_tools.mesh.conversion import convert
from mpas_tools.io import write_netcdf

def cellWidthVsLatLon(r=70):
    """
    Create cell width array for this mesh on a regular latitude-longitude grid.
    
    Input
    ---------
    r : float
        constant desired cell width resolution in km

    Returns
    -------
    cellWidth : ndarray
        m x n array of cell width in km
    lon : ndarray
        longitude in degrees (length n and between -180 and 180)
    lat : ndarray
        longitude in degrees (length m and between -90 and 90)
    """
    dlat = r/1000 #Make the lat-lon grid ~ 10x finer than resolution at equator, where 1deg ~ 100km
    dlon = dlat
    constantCellWidth = r  #in km

    nlat = int(180./dlat) + 1
    nlon = int(360./dlon) + 1

    lat = np.linspace(-90., 90., nlat)
    lon = np.linspace(-180., 180., nlon)

    cellWidth = constantCellWidth * np.ones((lat.size, lon.size))
    return cellWidth, lon, lat


def localrefVsLatLon(r=12,l=150, radius_high=50, transition_radius=600,
                     clon = 0.0, clat=0.0, p=False):
    """
    Create cell width array for this mesh on a locally refined latitude-longitude grid.
    Input
    ---------
    h : float
        grid spacing for high resolution area in km
    l : float
        grid spacing for low resolution area in km
    radius_high : float
        radius of influence of high resolution area in km
    transition_radius : float
        radius of the transition zone between high and low resolution in km 
    clon, clat : floats
        lon, lat of centre point
        
    Returns
    -------
    cellWidth : ndarray
        m x n array of cell width in km
    lon : ndarray
        longitude in degrees (length n and between -180 and 180)
    lat : ndarray
        longitude in degrees (length m and between -90 and 90)
    """
    dlat = r/200 #Make the lat-lon grid ~ 10x finer than resolution at equator, where 1deg ~ 100km
    dlon = dlat
    constantCellWidth = r  #in km
    print("Trying to set grid spacing of high resolution zone to approximately: "+str(constantCellWidth))

    nlat = int(180./dlat) + 1
    nlon = int(360./dlon) + 1

    lat = np.linspace(-90., 90., nlat)
    lon = np.linspace(-180., 180., nlon)

    lons, lats = np.meshgrid(lon, lat)

    #Calculate distances to center (lat=clat,lon=clon)
    dists = latlon_to_distance_center(lons, lats, clon, clat)

    if p:
        h = plt.contourf(lons, lats, dists)
        plt.axis('scaled')
        plt.colorbar()
        plt.show()

    #Parameters
    #------------------------------

    # Radius (in km) of high resolution area
    maxdist = radius_high
    print("Radius of high resolution area set approximately to: "+str(maxdist))

    distance = transition_radius/10
    print("Transition zone from high to low resolution set approximately to: "+ str(transition_radius))
    # (increase_of_resolution) / (distance)
    slope = 10./distance
    # Gammas
    gammas = l
    print("Global grid spacing set to approximately: "+str(gammas))
    
    # distance (in km) of transition zone belt: ratio / slope
    maxepsilons = 10000.
    epsilons = gammas/slope
    
    if(epsilons > maxepsilons):
        print("Transition zone too wide: set to 10,000 km")
        epsilons = maxepsilons
    
    # ## If radius of transition zone is not provided, try to find best value
    # if not(transition_radius):
    #     # distance (in km) of transition zone belt: ratio / slope
    #     maxepsilons = 10000.
    #     epsilons = gammas/slope
        
    #     if(epsilons > maxepsilons):
    #         epsilons = maxepsilons
    #     print("Transition zone radius not provided. Value set to: "+str(epsilons))
    # else:
    #     epsilons = transition_radius
    #     print("Transition zone radius provided: "+str(epsilons))


    # initialize with resolution = r (min resolution)
    resolution = constantCellWidth * np.ones(np.shape(dists))    

    # point in transition zone
    transition_zone = (dists > maxdist) & (dists <= maxdist + epsilons)
    sx = (dists - maxdist ) * slope
    transition_values = constantCellWidth + sx
    resolution = np.where(transition_zone, transition_values, resolution)

    # further points
    far_from_center = (dists > maxdist + epsilons)
    resolution[far_from_center] += epsilons * slope
    
    if p:
        h = plt.contourf(lons, lats, resolution, cmap="viridis", levels=100)
        plt.axis('scaled')
        plt.colorbar()
        plt.show()

    print(np.min(resolution), np.max(resolution))

    cellWidth = resolution #constantCellWidth * np.ones((lat.size, lon.size))
    
    return cellWidth, lon, lat

def density_function_dists(dists, slope=None, gammas=None, maxdist=None,
                           maxepsilons=None):

    epsilons = gammas/slope
    if epsilons > maxepsilons:
        epsilons = maxepsilons

    # initialize with resolution = 1
    resolution = np.ones(np.shape(dists))

    # point in transition zone
    transition_zone = (dists > maxdist) & (dists <= maxdist + epsilons)
    sx = (dists -maxdist ) *slope
    transition_values = 1.0 + sx
    resolution = np.where(transition_zone, transition_values, resolution)

    # further points
    far_from_center = (dists > maxdist + epsilons)
    resolution[far_from_center] += epsilons * slope

    # convert to density
    dens_f = 1 / resolution**2
    return dens_f


def latlon_to_distance_center(lon, lat, clon = 0.0, clat = 0.0):

    lon, lat = map(np.radians, [lon, lat])
    clon, clat = map(np.radians, [clon, clat])

    haver_formula = np.sin( (lat-clat)/ 2.0) ** 2 + \
                    np.cos(lat) * np.cos(clat) * np.sin((lon-clon) / 2.0) ** 2

    dists = 2 * np.arcsin(np.sqrt(haver_formula)) * 6367

    return dists




def jigsaw_gen_sph_grid(cellWidth, x, y, earth_radius=6371.0e3,
    basename="mesh" ):

    """
    A function for building a jigsaw spherical mesh
    Parameters
    ----------
    cellWidth : ndarray
        The size of each cell in the resulting mesh as a function of space
    x, y : ndarray
        The x and y coordinates of each point in the cellWidth array (lon and
        lat for spherical mesh)
    on_sphere : logical, optional
        Whether this mesh is spherical or planar
    earth_radius : float, optional
        Earth radius in meters
    """
    # Authors
    # -------
    #by P. Peixoto in Dec 2021
    # based on MPAS-Tools file from Mark Petersen, Phillip Wolfram, Xylar Asay-Davis 

    
    # setup files for JIGSAW
    opts = jig.jigsaw_jig_t()
    opts.geom_file = basename+'.msh'
    opts.jcfg_file = basename+'.jig'
    opts.mesh_file = basename+'-MESH.msh'
    opts.hfun_file = basename+'-HFUN.msh'

    # save HFUN data to file
    hmat = jig.jigsaw_msh_t()
    
    hmat.mshID = 'ELLIPSOID-GRID'
    hmat.xgrid = np.radians(x)
    hmat.ygrid = np.radians(y)
    hmat.value = cellWidth
    jig.savemsh(opts.hfun_file, hmat)

    # define JIGSAW geometry
    geom = jig.jigsaw_msh_t()
    geom.mshID = 'ELLIPSOID-MESH'
    geom.radii = earth_radius*1e-3*np.ones(3, float)
    jig.savemsh(opts.geom_file, geom)

    # build mesh via JIGSAW!
    opts.hfun_scal = 'absolute'
    opts.hfun_hmax = float("inf")
    opts.hfun_hmin = 0.0
    opts.mesh_dims = +2  # 2-dim. simplexes
    opts.mesh_iter = 5000000
    opts.optm_qlim = 0.9375
    opts.optm_qtol = 1.0e-6
    opts.optm_iter = 5000000
    opts.verbosity = +1
    jig.savejig(opts.jcfg_file, opts)
    
    #Call jigsaw
    process = subprocess.call(['jigsaw', opts.jcfg_file])

    return opts.mesh_file 

def jigsaw_gen_icos_grid(basename="mesh", level=4):

    # setup files for JIGSAW
    opts = jig.jigsaw_jig_t()
    icos = jig.jigsaw_msh_t()
    geom = jig.jigsaw_msh_t()

    opts.geom_file = basename+'.msh'
    opts.jcfg_file = basename+'.jig'
    opts.mesh_file = basename+'-MESH.msh'

    geom.mshID = "ellipsoid-mesh"
    geom.radii = np.full(3, 1.000E+000, dtype=geom.REALS_t)
        
    jig.savemsh(opts.geom_file, geom)

    opts.hfun_hmax = +1.
    opts.mesh_dims = +2                 # 2-dim. simplexes
    opts.optm_iter = +5120
    opts.optm_qtol = +1.0E-08
    
    jig.cmd.icosahedron(opts, level, icos)

    return opts.mesh_file


def _cleanup_intermediate(out_basepath, out_dir):
    """Remove the intermediary files produced while building a mesh."""
    for ext in ('.msh', '.jig', '-MESH.msh', '-HFUN.msh', '_triangles.nc'):
        f = out_basepath + ext
        if os.path.exists(f):
            os.remove(f)

    # MPAS-Tools 'convert' leaves a temporary working sub-directory behind
    leftovers = glob.glob(out_dir + '/*/graph.info')
    if leftovers:
        del_dir = os.path.dirname(leftovers[0])
        for f in ('graph.info', 'mesh_in.nc', 'mesh_out.nc'):
            path = os.path.join(del_dir, f)
            if os.path.exists(path):
                os.remove(path)
        os.removedirs(del_dir)


def build_global_mesh(opt, out_basepath, out_dir, out_filename,
                      r=30, l=150, rad=50, tr=600,
                      clon=0.0, clat=0.0, plots=False,
                      buffer_spec=None, dist_fn=None,
                      hfun_dlat=None, hfun_dtype=None):
    """
    Build a global MPAS mesh and write it to MPAS NetCDF format.

    This is the full jigsaw -> NetCDF -> MPAS-conversion pipeline that used to
    live inside ``create_spherical_grid.py``. It was moved here so that other
    scripts (e.g. the regional mesh creator) can reuse it without duplicating
    code.

    Parameters
    ----------
    opt : str
        Grid type: "unif" (uniform), "icos" (icosahedral) or "localref"
        (locally refined around clon/clat).
    out_basepath : str
        Base path (no extension) for the intermediary jigsaw/graph files.
    out_dir : str
        Output directory (already created by the caller).
    out_filename : str
        Final MPAS NetCDF mesh file to write.
    r : float
        Grid spacing of the high-resolution area in km.
    l : float
        Global (low-resolution) grid spacing in km for "localref"; for "icos"
        it is interpreted as the refinement level.
    rad : float
        Radius of the high-resolution area in km ("localref" only).
    tr : float
        Transition-zone radius in km ("localref" only).
    clon, clat : float
        Centre of the refinement, in degrees ("localref" only).
    plots : bool
        If True, show diagnostic plots of the resolution field.
    buffer_spec : cellwidth_util.BufferSpec, optional
        If given (with ``dist_fn``), build a regional field with a buffer /
        transition zone instead of the classic locally-refined one. Ignored
        unless ``opt == "localref"``.
    dist_fn : callable, optional
        Signed distance to the region boundary; see bufferedRegionVsLatLon.
    hfun_dlat : float, optional
        Working-grid spacing in degrees for the buffered field.
    hfun_dtype : numpy dtype, optional
        Storage type for the buffered field (float32 halves memory).

    Returns
    -------
    str
        Path to the MPAS NetCDF mesh that was written (``out_filename``).
    """
    if opt in ("unif", "localref"):
        if opt == "unif":
            cellWidth, lon, lat = cellWidthVsLatLon(r)
        elif buffer_spec is not None:  # localref with a buffer/transition zone
            if dist_fn is None:
                raise ValueError("buffer_spec requires dist_fn")
            cellWidth, lon, lat = bufferedRegionVsLatLon(
                buffer_spec, dist_fn, clon=clon, clat=clat,
                dlat=hfun_dlat, dtype=hfun_dtype, p=plots)
        else:  # localref
            cellWidth, lon, lat = localrefVsLatLon(
                r, l=l, radius_high=rad, transition_radius=tr,
                clon=clon, clat=clat, p=plots)
        mesh_file = jigsaw_gen_sph_grid(cellWidth, lon, lat,
                                        basename=out_basepath)

    elif opt == "icos":
        level = int(l)
        if level > 11:
            print("Please provide a reasonable refinement level - from 1 to 11."
                  " Current value too large ", level)
            print(" Setting level to 4")
            level = 4
        mesh_file = jigsaw_gen_icos_grid(basename=out_basepath, level=level)

    else:
        raise ValueError("Unknown grid option: " + repr(opt))

    # Convert jigsaw mesh to netcdf
    jigsaw_to_netcdf(msh_filename=mesh_file,
                     output_name=out_basepath + '_triangles.nc',
                     on_sphere=True, sphere_radius=1.0)

    # Convert to MPAS grid specific format (close the input dataset afterwards
    # so it does not leak file descriptors / keep the NetCDF file locked).
    with xarray.open_dataset(out_basepath + '_triangles.nc') as triangles:
        write_netcdf(
            convert(triangles, dir=out_dir,
                    graphInfoFileName=out_basepath + "_graph.info"),
            out_filename)

    # Clean-up intermediary files
    _cleanup_intermediate(out_basepath, out_dir)

    return out_filename


def resolve_plot_path(plot_out, out_dir, out_base):
    """
    Decide where to save the resolution plot.

    - ``plot_out`` falsy            -> next to the grid: out_dir/<out_base>_resolution.png
    - ``plot_out`` a directory      -> <plot_out>/<out_base>_resolution.png
    - ``plot_out`` a file path      -> that exact path
    """
    default_name = out_base + "_resolution.png"
    if not plot_out:
        return os.path.join(out_dir, default_name)
    if os.path.isdir(plot_out) or plot_out.endswith(os.sep):
        return os.path.join(plot_out, default_name)
    return plot_out


def plot_resolution(grid_file, out_png, states=False, center=None,
                    spec=None, core_radius=None, rings=None, show_bdy=True,
                    profile=None, vmin=None, vmax=None,
                    boundaries=None, dist_fn=None):
    """
    Quick-look plot of the cell resolution (km) of any MPAS mesh.

    Draws the cell centres coloured by their approximate spacing, so you can
    eyeball the mesh extent and confirm the resolution. Works for both global
    and regional meshes.

    If cartopy is available it adds coastlines and country borders (and state
    borders when ``states=True``, useful for regional meshes). It degrades
    gracefully to a plain scatter if cartopy is missing or its map data cannot
    be downloaded (e.g. offline).

    Parameters
    ----------
    grid_file : str
        MPAS mesh NetCDF (a global ``*.nc`` or a regional ``*.grid.nc``).
    out_png : str
        Output image path.
    states : bool
        Also draw state/province borders (recommended for regional meshes).
    center : (float, float), optional
        (clat, clon) of the region. Enables the radial-profile panel, which is
        the plot that actually shows whether jigsaw honoured the requested
        transition.
    spec : cellwidth_util.BufferSpec, optional
        If given, the analytic profile is drawn over the measured one and the
        colour scale is pinned to the requested spacings, so the flat zones
        read as flat instead of being stretched by autoscaling.
    core_radius : float, optional
        Radius (km) of the area of interest, for the profile markers.
    rings : list of (radius_km, label, colour), optional
        Extra circles to draw on the map and mark on the profile.
    boundaries : list of (points, label, colour), optional
        Real region outlines to draw on the map, ``points`` being a list of
        ``(lat, lon)``. Preferred over ``rings`` for anything that is not a
        circle.
    dist_fn : callable, optional
        ``dist_fn(lons, lats)`` giving the signed distance to the region
        boundary. When given, the profile panel is plotted against that instead
        of against distance from the centre, which is the only sensible x-axis
        for a non-circular domain.
    show_bdy : bool
        Outline the relaxation-zone cells (``bdyMaskCell > 0``). Seeing all
        seven rings sit inside the flat outer band is the verification that the
        buffer is doing its job.
    profile : bool, optional
        Force the profile panel on or off; defaults to on when ``center`` is
        given.
    vmin, vmax : float, optional
        Colour-scale limits in km.
    """
    from netCDF4 import Dataset

    ds = Dataset(grid_file)
    lat = np.degrees(ds.variables['latCell'][:])
    lon = np.degrees(ds.variables['lonCell'][:])
    lon = np.where(lon > 180.0, lon - 360.0, lon)

    # Approx. resolution from cell area. Meshes here live on a unit sphere
    # (sphere_radius=1), so scale areas up to the real Earth before converting.
    #
    # An MPAS cell is a hexagon of spacing h (centre-to-centre distance), whose
    # area is A = (sqrt(3)/2) h^2, so h = sqrt(2A/sqrt(3)). Using the diameter
    # of an equal-area disc instead, 2*sqrt(A/pi), overstates the spacing by
    # 5.0 % -- it used to make a nominally 5 km mesh plot as 5.24 km.
    area = ds.variables['areaCell'][:]
    sphere_radius = float(getattr(ds, 'sphere_radius', 1.0))
    earth_radius_m = 6371220.0 if sphere_radius == 1.0 else 1.0
    area_km2 = (area / 1.0e6) * earth_radius_m ** 2
    resolution_km = np.sqrt(2.0 * area_km2 / np.sqrt(3.0))
    bdy_mask = (ds.variables['bdyMaskCell'][:]
                if 'bdyMaskCell' in ds.variables else None)
    ds.close()

    if profile is None:
        profile = center is not None
    if vmin is None and spec is not None:
        vmin = spec.r
    if vmax is None and spec is not None:
        vmax = spec.r_outer * 1.05

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except ImportError:
        ccrs = None

    cmap = resolution_cmap()
    if vmin is not None and vmax is not None:
        norm, _ = resolution_norm(vmin, vmax)
        skw = {'cmap': cmap, 'norm': norm}
        cbkw = {'extend': 'max'}
    else:
        norm, _ = resolution_norm(float(resolution_km.min()),
                                  float(resolution_km.max()))
        skw = {'cmap': cmap, 'norm': norm}
        cbkw = {}

    # Map and profile go to separate files: they are read for different
    # reasons, and a two-panel figure makes each half too small to use in a
    # report or a slide.
    fig = plt.figure(figsize=(8, 7))

    if ccrs is not None:
        proj = ccrs.PlateCarree()
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        sc = ax.scatter(lon, lat, c=resolution_km, s=4, transform=proj, **skw)

        # Frame the data: whole globe if it spans (almost) everything,
        # otherwise zoom to the mesh with a small margin.
        span_lon = float(lon.max() - lon.min())
        span_lat = float(lat.max() - lat.min())
        if span_lon > 350.0 and span_lat > 170.0:
            ax.set_global()
        else:
            mlon = max(1.0, 0.05 * span_lon)
            mlat = max(1.0, 0.05 * span_lat)
            ax.set_extent([lon.min() - mlon, lon.max() + mlon,
                           lat.min() - mlat, lat.max() + mlat], crs=proj)

        # Map details (downloaded on first use; skip silently if unavailable).
        try:
            ax.coastlines(resolution='50m', linewidth=0.6)
            ax.add_feature(cfeature.BORDERS, linewidth=0.5)
            if states:
                ax.add_feature(cfeature.STATES, linewidth=0.3,
                               edgecolor='gray')
        except Exception as exc:
            print("WARNING: could not add cartopy map features (%s); "
                  "plotting points only." % exc)

        gl = ax.gridlines(draw_labels=True, linewidth=0.3, color='gray',
                          alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False
    else:
        print("WARNING: cartopy not available; plotting a plain scatter "
              "(no coastlines/borders).")
        ax = fig.add_subplot(1, 1, 1)
        sc = ax.scatter(lon, lat, c=resolution_km, s=4, **skw)
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.set_aspect("equal")

    if boundaries:
        kwb = {'transform': ccrs.PlateCarree()} if ccrs is not None else {}
        for points, lab, col in boundaries:
            blat = np.array([q[0] for q in points])
            blon = np.array([q[1] for q in points])
            blat = np.append(blat, blat[0])
            blon = np.append(blon, blon[0])
            ax.plot(blon, blat, lw=1.0, color=col, label=lab, **kwb)

    if show_bdy and bdy_mask is not None and (bdy_mask > 0).any():
        rel = bdy_mask > 0
        kw = {'transform': ccrs.PlateCarree()} if ccrs is not None else {}
        # Black outline, not a colour: the resolution palette runs from purple
        # through red to green, so any hue would vanish somewhere on the map.
        ax.scatter(lon[rel], lat[rel], s=6, facecolors='none',
                   edgecolors='black', linewidths=0.3,
                   label='relaxation zone', **kw)
        ax.legend(loc='lower left', fontsize=7, framealpha=0.8)

    cb = fig.colorbar(sc, ax=ax, shrink=0.8, **cbkw)
    cb.set_label("cell resolution (km)")
    ax.set_title(os.path.basename(grid_file))

    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    profile_png = None
    if profile:
        profile_png = profile_plot_path(out_png)
        figp, axp = plt.subplots(figsize=(7.5, 5.5))
        clat, clon = center

        # Distance from the centre only means something for a circle. For any
        # other shape the meaningful coordinate is the signed distance to the
        # region boundary, which is also exactly what the profile was designed
        # against, so the analytic curve overlays it directly.
        if dist_fn is not None:
            d = dist_fn(lon, lat)
            r0 = 0.0
            xlabel = "signed distance to the area of interest (km)"
        else:
            d = latlon_to_distance_center(lon, lat, clon=clon, clat=clat)
            r0 = core_radius if core_radius is not None else 0.0
            xlabel = "great-circle distance from region centre (km)"

        axp.scatter(d, resolution_km, s=2, alpha=0.25, color='C0',
                    label='mesh cells')
        if bdy_mask is not None and (bdy_mask > 0).any():
            rel = bdy_mask > 0
            axp.scatter(d[rel], resolution_km[rel], s=3, alpha=0.6,
                        color='crimson', label='relaxation zone')
        if spec is not None:
            import cellwidth_util as cwu
            dd = np.linspace(float(d.min()), float(d.max()) * 1.02, 1500)
            axp.plot(dd, cwu.buffered_cellwidth(dd - r0, spec), lw=1.8,
                     color='k', label='requested profile')
            marks = [(r0, 'area of interest', 'k'),
                     (r0 + spec.width, 'end of ramp', 'C1'),
                     (r0 + spec.cut_offset, 'LBC zone starts (.pts)', 'C3'),
                     (r0 + spec.mesh_offset, 'mesh edge', 'C2')]
            for x, lab, col in marks:
                axp.axvline(x, ls='--', lw=1, color=col)
                axp.text(x, axp.get_ylim()[1], ' ' + lab, rotation=90,
                         va='top', ha='left', fontsize=7, color=col)
        for ring in (rings or []):
            axp.axvline(ring[0], ls=':', lw=1,
                        color=ring[2] if len(ring) > 2 else 'gray')
        axp.set_xlabel(xlabel)
        axp.set_ylabel("cell resolution (km)")
        axp.set_title("%s - resolution profile" % os.path.basename(grid_file))
        axp.grid(alpha=0.3)
        axp.legend(fontsize=8, loc='upper left')

        figp.tight_layout()
        figp.savefig(profile_png, dpi=150, bbox_inches="tight")
        plt.close(figp)

    return out_png, profile_png


# Colour scale for grid spacing, given coarse -> fine. Matplotlib maps position
# 0 of a colormap to the LOWEST value, and the lowest spacing is the finest, so
# the list is reversed when the colormap is built: fine cells come out purple,
# coarse cells green.
RESOLUTION_COLORS_COARSE_TO_FINE = [
    "#008000", "#33B200", "#80D900", "#CCE600", "#FFE600", "#FFB200",
    "#FF8000", "#FF4000", "#FF0000", "#CC0033", "#99004C", "#660066",
]


def resolution_cmap():
    """Discrete colormap for cell spacing (fine = purple, coarse = green)."""
    from matplotlib.colors import ListedColormap

    colors = list(reversed(RESOLUTION_COLORS_COARSE_TO_FINE))
    cmap = ListedColormap(colors, name="mpas_resolution")
    # Anything coarser than the top of the scale keeps the coarsest colour,
    # so the discarded background does not read as a separate category.
    cmap.set_over(colors[-1])
    cmap.set_under(colors[0])
    return cmap


def resolution_norm(vmin, vmax):
    """BoundaryNorm with one bin per colour of resolution_cmap()."""
    from matplotlib.colors import BoundaryNorm

    cmap = resolution_cmap()
    levels = np.linspace(float(vmin), float(vmax), cmap.N + 1)
    return BoundaryNorm(levels, cmap.N), levels


def profile_plot_path(out_png):
    """Companion path for the separate resolution-profile figure."""
    base, ext = os.path.splitext(out_png)
    return base + "_profile" + (ext or ".png")


def latlon_grid(dlat, dlon=None):
    """
    Regular global lat/lon grid used as jigsaw's HFUN (target size) grid.

    Returns (lon, lat) in degrees, lon in [-180, 180] and lat in [-90, 90].
    Note the wrap column is duplicated (lon[0] == lon[-1] - 360), which is what
    jigsaw expects for a periodic grid.
    """
    dlon = dlat if dlon is None else dlon
    nlat = int(180. / dlat) + 1
    nlon = int(360. / dlon) + 1
    return np.linspace(-180., 180., nlon), np.linspace(-90., 90., nlat)


def bufferedRegionVsLatLon(spec, dist_fn, clon=0.0, clat=0.0, dlat=None,
                           dtype=None, chunk_rows=512, p=False):
    """
    Cell width array for a regional mesh with a buffer / transition zone.

    Unlike localrefVsLatLon, which is a function of distance from a point, this
    is a function of the signed distance to the *boundary of the area of
    interest*, so it follows the actual region shape -- a box gets a buffer of
    even width all the way round, including at its corners.

    Parameters
    ----------
    spec : cellwidth_util.BufferSpec
        The resolved profile (spacings, ramp width, plateau, background).
    dist_fn : callable
        ``dist_fn(lons, lats, pad_km=None)`` returning the signed great-circle
        distance in km to the region boundary, negative inside. Build one with
        regional_util.circle_distance_fn or regional_util.polygon_distance_fn.
    clon, clat : float
        Region centre, used only for the diagnostic plot.
    dlat : float, optional
        Spacing of the working grid in degrees. Defaults to ``spec.r / 200``,
        matching localrefVsLatLon. The field only has to resolve the
        *transition*, not the cell size, so a coarser grid is usually fine and
        much cheaper: at r = 5 km the default is 7201 x 14401 points.
    dtype : numpy dtype, optional
        float32 halves memory and shrinks the intermediate jigsaw HFUN file;
        defaults to float64.
    chunk_rows : int
        Number of latitude rows evaluated at a time, so peak memory stays
        bounded no matter how fine the grid is.
    p : bool
        Show a diagnostic plot of the resolution field.

    Returns
    -------
    cellWidth : ndarray
        m x n array of cell width in km.
    lon, lat : ndarray
        Grid coordinates in degrees.
    """
    import cellwidth_util as cwu

    if dlat is None:
        dlat = spec.r / 200.
    if dtype is None:
        dtype = np.float64

    lon, lat = latlon_grid(dlat)
    cellWidth = np.empty((lat.size, lon.size), dtype=dtype)

    # Past this distance the profile has flattened out at the background
    # spacing, so dist_fn may take whatever shortcut it likes.
    pad_km = spec.total_offset + (spec.l - spec.r_outer) / spec.outer_slope

    print("Building buffered resolution field on a %d x %d grid (dlat=%.4g deg)"
          % (lat.size, lon.size, dlat))
    print("  core %.1f km -> ramp %.1f km -> plateau %.1f km -> background %.1f km"
          % (spec.r, spec.width, spec.r_outer, spec.l))

    scratch = None
    for i0 in range(0, lat.size, chunk_rows):
        i1 = min(i0 + chunk_rows, lat.size)
        s = dist_fn(lon[None, :], lat[i0:i1, None], pad_km=pad_km)
        if scratch is None or scratch.shape != s.shape:
            scratch = np.empty(s.shape, dtype=float)
        cellWidth[i0:i1] = cwu.buffered_cellwidth(s, spec, out=scratch)

    print("  resolution field: min %.2f km, max %.2f km"
          % (cellWidth.min(), cellWidth.max()))

    if p:
        plot_cellwidth_field(cellWidth, lon, lat, None, clon=clon, clat=clat,
                             spec=spec, show=True)

    return cellWidth, lon, lat


def plot_cellwidth_field(cellWidth, lon, lat, out_png, clon=0.0, clat=0.0,
                         spec=None, core_radius=None, extent_km=None,
                         title=None, show=False, boundaries=None):
    """
    Plot the ANALYTIC cell-width field, before jigsaw is ever run.

    This is what --preview draws: it takes seconds, whereas generating a 5 km
    mesh takes minutes, so it is the right place to tune the ramp width.

    Left panel: the field around the region. Right panel: its radial profile,
    with the core / ramp / plateau boundaries marked.

    ``boundaries`` is a list of ``(points, label, colour)``, where ``points`` is
    a list of ``(lat, lon)``. Pass the real region outlines here: drawing
    circles at a circumscribed radius would misrepresent every non-circular
    domain, since the buffer follows the actual boundary, not a circle.
    """
    # Zoom to the regional domain: the field is global, but the part that gets
    # cut out is small and it is the only part worth looking at.
    if extent_km is None and spec is not None:
        extent_km = 1.25 * ((core_radius or 0.0) + spec.mesh_offset)
    if extent_km is None:
        extent_km = 3000.0
    half_deg = np.degrees(extent_km / 6371.0)

    jlo = np.searchsorted(lon, clon - half_deg / max(0.1, np.cos(np.radians(clat))))
    jhi = np.searchsorted(lon, clon + half_deg / max(0.1, np.cos(np.radians(clat))))
    ilo = np.searchsorted(lat, clat - half_deg)
    ihi = np.searchsorted(lat, clat + half_deg)
    jlo, ilo = max(0, jlo), max(0, ilo)
    jhi, ihi = min(lon.size, jhi + 1), min(lat.size, ihi + 1)

    # Keep the pcolormesh under a few hundred thousand quads.
    stride = max(1, int(np.sqrt((ihi - ilo) * (jhi - jlo) / 250000.)))
    sub = cellWidth[ilo:ihi:stride, jlo:jhi:stride]
    slon = lon[jlo:jhi:stride]
    slat = lat[ilo:ihi:stride]

    fig, ax = plt.subplots(figsize=(8, 7))

    # Pin the colour scale to the transition itself. Autoscaling would stretch
    # it over the 200 km background and render the whole regional domain as one
    # flat blob -- exactly the detail we are here to inspect.
    cmap = resolution_cmap()
    if spec is not None:
        norm, _ = resolution_norm(spec.r, spec.r_outer)
        extend = "max"
    else:
        norm, _ = resolution_norm(float(sub.min()), float(sub.max()))
        extend = "neither"
    pc = ax.pcolormesh(slon, slat, sub, cmap=cmap, norm=norm,
                       shading="nearest")
    if boundaries:
        for points, lab, col in boundaries:
            blat = np.array([q[0] for q in points])
            blon = np.array([q[1] for q in points])
            blat = np.append(blat, blat[0])
            blon = np.append(blon, blon[0])
            ax.plot(blon, blat, lw=1.0, color=col, label=lab)
        ax.legend(loc="upper right", fontsize=7, framealpha=0.85)

    ax.set_aspect(1.0 / max(0.1, np.cos(np.radians(clat))))
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(title or "target cell width (km)")
    fig.colorbar(pc, ax=ax, shrink=0.85,
                 extend=extend).set_label("cell width (km)")

    fig.tight_layout()
    if out_png:
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)

    # The profile goes to its own file rather than a cramped second panel.
    profile_png = None
    if spec is not None:
        import cellwidth_util as cwu
        profile_png = profile_plot_path(out_png) if out_png else None
        figp, axp = plt.subplots(figsize=(7.5, 5.5))
        s = np.linspace(-(core_radius or spec.total_offset),
                        spec.total_offset * 1.35, 2000)
        axp.plot(s, cwu.buffered_cellwidth(s, spec), lw=2, color="C0")
        for off, lab, col in ((0.0, "area of interest", "k"),
                              (spec.width, "end of ramp", "C1"),
                              (spec.cut_offset, "LBC zone starts (.pts)", "C3"),
                              (spec.mesh_offset, "mesh edge", "C2")):
            axp.axvline(off, ls="--", lw=1, color=col)
            axp.text(off, spec.l * 0.02 + spec.r_outer * 1.05, " " + lab,
                     rotation=90, va="bottom", fontsize=8, color=col)
        axp.axhline(spec.r, ls=":", lw=0.8, color="gray")
        axp.axhline(spec.r_outer, ls=":", lw=0.8, color="gray")
        axp.set_ylim(0, spec.r_outer * 2.0)
        axp.set_xlabel("signed distance to the area of interest (km)")
        axp.set_ylabel("cell width (km)")
        axp.set_title("requested profile (%s, growth %.3f)"
                      % (spec.profile, spec.growth))
        axp.grid(alpha=0.3)

        figp.tight_layout()
        if profile_png:
            figp.savefig(profile_png, dpi=150, bbox_inches="tight")
        if show:
            plt.show()
        plt.close(figp)

    return out_png, profile_png
