"""Almost regular starting point sets (and their Delaunay triangulation) for JIGSAW on the tropical design.

  rings   reduced latitude-longitude rings, ring latitudes spaced by the local cell width, each ring with
          round(2 pi R cos(lat) / h) points, consecutive rings shifted by half a spacing, one point at each pole
  geo     points of icosahedral lattices of frequencies in steps of GEO_STEP, each used where its spacing is the
          closest to the cell width, so the density steps are small and the mismatch of neighbouring lattices
          is spread
  icos    points of nested bisections of the icosahedron: the level-k midpoints are kept where the cell width
          is below ICOS_KEEP times the edge length of level k-1, so the point density follows the design
          in steps of factors of two

  coarsen the cell centres of a finer MPAS mesh after a decimation that keeps every other point along each lattice
          direction (decimate), i.e. the index-4 sublattice where the mesh is hexagonal
  mapped  the lattice of cont with the latitude of each point moved to the latitude with the same fraction of the
          design's cells to the south, so that the point density follows the design and the connectivity is the lattice's
  cont    the icosahedral lattice whose point count equals that of the design, i.e. a mesh without defects
          other than the 12 pentagons, for the continuation in the density (blend_width)

All return unit-sphere points. The mesh file for JIGSAW's INIT_FILE holds the triangulation too, so that
with mesh_iter 0 JIGSAW only optimises the given connectivity.
"""
import numpy as np

ROW = np.sqrt(3.0) / 2.0   # row spacing over point spacing of a hexagonal lattice
ICOS_KEEP = 1.0 / np.sqrt(2.0)
GEO_STEP = 1.12   # ratio of the frequencies of neighbouring lattices of the geo set


def _lonlat_to_xyz(lon, lat):
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)


def ring_points(width_of_lat, radius):
    """Points on the unit sphere. width_of_lat(lat in degrees) is the cell width, radius the sphere radius, same unit."""
    lats = [0.0]
    for sign in (1.0, -1.0):
        lat = 0.0
        while True:
            step = ROW * width_of_lat(np.degrees(lat)) / radius
            for _ in range(3):
                step = ROW * width_of_lat(np.degrees(lat + sign * 0.5 * step)) / radius
            lat += sign * step
            if abs(lat) > 0.5 * np.pi - 0.5 * step:
                break
            lats.append(lat)
    lats = np.sort(np.array(lats))
    out = [np.array([[0.0, 0.0, -1.0]]), np.array([[0.0, 0.0, 1.0]])]
    for j, lat in enumerate(lats):
        n = max(int(round(2.0 * np.pi * radius * np.cos(lat) / width_of_lat(np.degrees(lat)))), 5)
        shift = 0.5 if (j - np.searchsorted(lats, 0.0)) % 2 else 0.0
        lon = (np.arange(n) + shift) * 2.0 * np.pi / n
        out.append(_lonlat_to_xyz(lon, np.full(n, lat)))
    return np.concatenate(out)


def _icosahedron():
    la, lo = np.arctan(0.5), 0.2 * np.pi
    lon = np.array([0.0, 0.0] + [i * lo for i in range(10)])
    lat = np.array([-0.5 * np.pi, 0.5 * np.pi] + [la if i % 2 == 0 else -la for i in range(10)])
    tri = np.array([(0, 3, 5), (0, 5, 7), (0, 7, 9), (0, 9, 11), (0, 11, 3), (1, 2, 4), (1, 4, 6), (1, 6, 8),
                    (1, 8, 10), (1, 10, 2), (3, 2, 4), (5, 4, 6), (7, 6, 8), (9, 8, 10), (11, 10, 2), (4, 3, 5),
                    (6, 5, 7), (8, 7, 9), (10, 9, 11), (2, 11, 3)])
    return _lonlat_to_xyz(lon, lat), tri


def _bisect(xyz, tri):
    """One uniform bisection. Returns all points, the triangles and the index of the first new point."""
    edges = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    uniq, inv = np.unique(edges, axis=0, return_inverse=True)
    mid = xyz[uniq[:, 0]] + xyz[uniq[:, 1]]
    mid /= np.linalg.norm(mid, axis=1)[:, None]
    m01, m12, m20 = (len(xyz) + inv[i * len(tri):(i + 1) * len(tri)] for i in range(3))
    a, b, c = tri.T
    new = np.concatenate([np.stack([a, m01, m20], 1), np.stack([m01, b, m12], 1),
                          np.stack([m20, m12, c], 1), np.stack([m01, m12, m20], 1)])
    return np.concatenate([xyz, mid]), new, len(xyz)


def icos_points(width_of_lat, radius):
    """Points on the unit sphere, see the module text."""
    xyz, tri = _icosahedron()
    spacing = 1.1071 * radius
    lats = np.linspace(0.0, 90.0, 901)
    wmin, wmax = width_of_lat(lats).min(), width_of_lat(lats).max()
    while spacing * ICOS_KEEP > wmax:
        xyz, tri, _ = _bisect(xyz, tri)
        spacing *= 0.5
    points = [xyz]
    while spacing * ICOS_KEEP > wmin:
        xyz, tri, n0 = _bisect(xyz, tri)
        spacing *= 0.5
        new = xyz[n0:]
        points.append(new[width_of_lat(np.degrees(np.arcsin(new[:, 2]))) < 2.0 * spacing * ICOS_KEEP])
        # subdivide further only where a finer level can still be kept
        centre = xyz[tri].sum(1)
        centre /= np.linalg.norm(centre, axis=1)[:, None]
        tri = tri[width_of_lat(np.degrees(np.arcsin(centre[:, 2]))) < 1.6 * spacing * ICOS_KEEP]
    return np.unique(np.round(np.concatenate(points), 9), axis=0)


def _geodesic(nu):
    """Points of the frequency-nu subdivision of the icosahedron faces, projected to the unit sphere."""
    xyz, tri = _icosahedron()
    i, j = np.meshgrid(np.arange(nu + 1), np.arange(nu + 1))
    keep = i + j <= nu
    w = np.stack([(nu - i - j)[keep], i[keep], j[keep]], 1) / nu
    pts = np.einsum("pk,fkd->fpd", w, xyz[tri]).reshape(-1, 3)
    pts /= np.linalg.norm(pts, axis=1)[:, None]
    return np.unique(np.round(pts, 9), axis=0)


def lattice_spacing(nu, radius):
    """Mean point spacing of the frequency-nu icosahedral lattice (hexagons of equal area)."""
    return np.sqrt(2.0 / np.sqrt(3.0) * 4.0 * np.pi * radius ** 2 / (10 * nu ** 2 + 2))


def geodesic_points(width_of_lat, radius):
    """Points on the unit sphere, see the module text."""
    lats = np.linspace(0.0, 90.0, 901)
    wmin, wmax = width_of_lat(lats).min(), width_of_lat(lats).max()
    freq = lambda h: np.sqrt((2.0 / np.sqrt(3.0) * 4.0 * np.pi * radius ** 2 / h ** 2 - 2.0) / 10.0)
    coarse, fine = freq(wmax), freq(wmin)
    steps = max(int(round(np.log(fine / coarse) / np.log(GEO_STEP))), 1)
    nu = sorted(set(int(round(n)) for n in coarse * (fine / coarse) ** (np.arange(steps + 1) / steps)))
    spacing = lattice_spacing(np.array(nu), radius)
    out = []
    for n in nu:
        p = _geodesic(n)
        h = width_of_lat(np.degrees(np.arcsin(p[:, 2])))
        best = np.argmin(np.abs(np.log(h[:, None] / spacing[None, :])), axis=1)
        out.append(p[best == nu.index(n)])
    return np.concatenate(out)


def _integral(f, x):
    return np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(x))


def cell_count(width_of_lat, radius):
    """Number of hexagonal cells of a mesh of the given cell width (width_of_lat in degrees, radius in the width unit)."""
    lat = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 20001)
    h = width_of_lat(np.degrees(lat))
    return 2.0 / np.sqrt(3.0) * 2.0 * np.pi * radius ** 2 * _integral(h ** -2 * np.cos(lat), lat)


def continuation_points(width_of_lat, radius):
    """Points on the unit sphere, see the module text."""
    return _geodesic(int(round(np.sqrt((cell_count(width_of_lat, radius) - 2.0) / 10.0))))


def _cell_fraction(width_of_lat):
    """Latitudes (radians) and the fraction of the cells of the design that lie south of each."""
    lat = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 20001)
    f = width_of_lat(np.degrees(lat)) ** -2 * np.cos(lat)
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(lat))])
    return lat, cdf / cdf[-1]


def _set_latitudes(p, new):
    r = np.cos(new) / np.maximum(np.hypot(p[:, 0], p[:, 1]), 1e-300)
    return np.stack([p[:, 0] * r, p[:, 1] * r, np.sin(new)], 1)


def mapped_points(width_of_lat, radius):
    """Points on the unit sphere, see the module text."""
    p = continuation_points(width_of_lat, radius)
    lat, cdf = _cell_fraction(width_of_lat)
    return _set_latitudes(p, np.interp(0.5 * (1.0 + p[:, 2]), cdf, lat))


def remap_latitudes(p, src_width_of_lat, dst_width_of_lat):
    """Points p on the unit sphere moved along their meridians so that the fraction of points south of each
    one follows the cell fraction of the destination design instead of the source design."""
    lat_s, cdf_s = _cell_fraction(src_width_of_lat)
    lat_d, cdf_d = _cell_fraction(dst_width_of_lat)
    frac = np.interp(np.arcsin(np.clip(p[:, 2], -1.0, 1.0)), lat_s, cdf_s)
    return _set_latitudes(p, np.interp(frac, cdf_d, lat_d))


def blend_width(width_of_lat, radius, t, power=1.0):
    """Cell width of the continuation at parameter t in [0, 1], as a function of latitude (degrees). It is the
    geometric blend of the uniform width and the design, h_u^(1-p t) h_d^(p t), scaled to the cell count of the design."""
    lat = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 20001)
    h_d = width_of_lat(np.degrees(lat))
    area = 2.0 * np.pi * radius ** 2 * _integral(h_d ** -2 * np.cos(lat), lat)
    h_u = np.sqrt(4.0 * np.pi * radius ** 2 / area)
    g = lambda x: h_u ** (1.0 - power * t) * width_of_lat(x) ** (power * t)
    scale = np.sqrt(2.0 * np.pi * radius ** 2 * _integral(g(np.degrees(lat)) ** -2 * np.cos(lat), lat) / area)
    return lambda x: scale * g(x)


def neighbours(points, tri):
    """Neighbours of each point of a triangulation of the unit sphere, counterclockwise seen from outside."""
    pair = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    pair = np.unique(np.concatenate([pair, pair[:, ::-1]]), axis=0)
    p = points[pair[:, 0]]
    north = np.array([0.0, 0.0, 1.0])
    e1 = np.cross(north, p)
    bad = np.linalg.norm(e1, axis=1) < 1e-12
    e1[bad] = np.cross(np.array([1.0, 0.0, 0.0]), p[bad])
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(p, e1)
    d = points[pair[:, 1]] - p
    pair = pair[np.lexsort((np.arctan2((d * e2).sum(1), (d * e1).sum(1)), pair[:, 0]))]
    return np.split(pair[:, 1], np.cumsum(np.bincount(pair[:, 0], minlength=len(points)))[:-1])


def decimate(points, direction=(1.0, 0.0, 0.0)):
    """Indices of the points kept by a coarsening that doubles the spacing. Each kept point reaches its coarse
    neighbours by going straight through a neighbour (the opposite entry of the neighbour's ring), which gives the
    index-4 sublattice where the mesh is hexagonal. The first kept point is the closest to `direction`. Points left without a kept neighbour are kept as well."""
    nb = [list(x) for x in neighbours(points, triangulate(points))]
    state = np.zeros(len(points), dtype=np.int8)   # 0 free, 1 kept, 2 removed
    near = np.zeros(len(points), dtype=bool)       # has a kept neighbour
    start = int(np.argmax(points @ np.asarray(direction, dtype=float)))
    queue, head = [start], 0
    state[start] = 1
    near[nb[start]] = True
    while head < len(queue):
        c = queue[head]
        head += 1
        for j in nb[c]:
            if state[j] == 0:
                state[j] = 2
            ring = nb[j]
            o = ring[(ring.index(c) + len(ring) // 2) % len(ring)]
            if state[o] == 0 and not near[o]:
                state[o] = 1
                near[nb[o]] = True
                queue.append(o)
    for c in np.flatnonzero(~near & (state != 1)):
        if not near[c]:
            state[c] = 1
            near[nb[c]] = True
    return np.flatnonzero(state == 1)


def coarsen_points(grid_file, levels=1, direction=(1.0, 0.0, 0.0), remap=None):
    """Cell centres of an MPAS grid file on the unit sphere, decimated `levels` times (spacing 2^levels times larger).
    remap = (source width of lat, destination width of lat) moves the latitudes as in remap_latitudes."""
    import netCDF4
    with netCDF4.Dataset(grid_file) as f:
        pts = np.stack([np.ma.getdata(f[k][:]) for k in ("xCell", "yCell", "zCell")], 1).astype(float)
    pts /= np.linalg.norm(pts, axis=1)[:, None]
    for _ in range(levels):
        pts = pts[decimate(pts, direction)]
    return pts if remap is None else remap_latitudes(pts, *remap)


def triangulate(points):
    """Delaunay triangles of points on the unit sphere (convex hull), counterclockwise seen from outside."""
    from scipy.spatial import ConvexHull
    hull = ConvexHull(points)
    tri = hull.simplices
    n = np.cross(points[tri[:, 1]] - points[tri[:, 0]], points[tri[:, 2]] - points[tri[:, 0]])
    flip = (n * points[tri[:, 0]]).sum(1) < 0.0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri


def start_mesh(kind, width_of_lat, radius, source=None, levels=1, direction=(1.0, 0.0, 0.0), source_width_of_lat=None):
    """JIGSAW mesh (euclidean-mesh with vert3 and tria3) of the starting set, coordinates scaled to radius."""
    import jigsawpy as jig
    if kind == "coarsen":
        pts = coarsen_points(source, levels, direction, None if source_width_of_lat is None else (source_width_of_lat, width_of_lat))
    else:
        pts = {"rings": ring_points, "icos": icos_points, "geo": geodesic_points,
               "continuation": continuation_points, "mapped": mapped_points}[kind](width_of_lat, radius)
    mesh = jig.jigsaw_msh_t()
    mesh.mshID = "euclidean-mesh"
    mesh.vert3 = np.zeros(len(pts), dtype=mesh.VERT3_t)
    mesh.vert3["coord"] = pts * radius
    tri = triangulate(pts)
    mesh.tria3 = np.zeros(len(tri), dtype=mesh.TRIA3_t)
    mesh.tria3["index"] = tri
    return mesh

