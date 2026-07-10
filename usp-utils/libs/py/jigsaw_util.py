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
                      clon=0.0, clat=0.0, plots=False):
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

    Returns
    -------
    str
        Path to the MPAS NetCDF mesh that was written (``out_filename``).
    """
    if opt in ("unif", "localref"):
        if opt == "unif":
            cellWidth, lon, lat = cellWidthVsLatLon(r)
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


def plot_resolution(grid_file, out_png, states=False):
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
    """
    from netCDF4 import Dataset

    ds = Dataset(grid_file)
    lat = np.degrees(ds.variables['latCell'][:])
    lon = np.degrees(ds.variables['lonCell'][:])
    lon = np.where(lon > 180.0, lon - 360.0, lon)

    # Approx. resolution from cell area. Meshes here live on a unit sphere
    # (sphere_radius=1), so scale areas up to the real Earth before converting.
    area = ds.variables['areaCell'][:]
    sphere_radius = float(getattr(ds, 'sphere_radius', 1.0))
    earth_radius_m = 6371220.0 if sphere_radius == 1.0 else 1.0
    area_km2 = (area / 1.0e6) * earth_radius_m ** 2
    resolution_km = 2.0 * np.sqrt(area_km2 / np.pi)
    ds.close()

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except ImportError:
        ccrs = None

    if ccrs is not None:
        proj = ccrs.PlateCarree()
        fig, ax = plt.subplots(figsize=(8, 7), subplot_kw={'projection': proj})
        sc = ax.scatter(lon, lat, c=resolution_km, s=4, cmap="viridis",
                        transform=proj)

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
        fig, ax = plt.subplots(figsize=(8, 7))
        sc = ax.scatter(lon, lat, c=resolution_km, s=4, cmap="viridis")
        ax.set_xlabel("longitude")
        ax.set_ylabel("latitude")
        ax.set_aspect("equal")

    cb = fig.colorbar(sc, ax=ax, shrink=0.8)
    cb.set_label("cell resolution (km)")
    ax.set_title(os.path.basename(grid_file))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return out_png
