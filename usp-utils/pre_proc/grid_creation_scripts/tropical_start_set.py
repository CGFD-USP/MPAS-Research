"""Almost regular starting point sets (and their Delaunay triangulation) for JIGSAW on the tropical design.

  rings   reduced latitude-longitude rings, ring latitudes spaced by the local cell width, each ring with
          round(2 pi R cos(lat) / h) points, consecutive rings shifted by half a spacing, one point at each pole
  geo     points of icosahedral lattices of frequencies in steps of GEO_STEP, each used where its spacing is the
          closest to the cell width, so the density steps are small and the mismatch of neighbouring lattices
          is spread
  icos    points of nested bisections of the icosahedron: the level-k midpoints are kept where the cell width
          is below ICOS_KEEP times the edge length of level k-1, so the point density follows the design
          in steps of factors of two

Both return unit-sphere points. The mesh file for JIGSAW's INIT_FILE holds the triangulation too, so that
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


def triangulate(points):
    """Delaunay triangles of points on the unit sphere (convex hull), counterclockwise seen from outside."""
    from scipy.spatial import ConvexHull
    hull = ConvexHull(points)
    tri = hull.simplices
    n = np.cross(points[tri[:, 1]] - points[tri[:, 0]], points[tri[:, 2]] - points[tri[:, 0]])
    flip = (n * points[tri[:, 0]]).sum(1) < 0.0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri


def start_mesh(kind, width_of_lat, radius):
    """JIGSAW mesh (euclidean-mesh with vert3 and tria3) of the starting set, coordinates scaled to radius."""
    import jigsawpy as jig
    pts = {"rings": ring_points, "icos": icos_points, "geo": geodesic_points}[kind](width_of_lat, radius)
    mesh = jig.jigsaw_msh_t()
    mesh.mshID = "euclidean-mesh"
    mesh.vert3 = np.zeros(len(pts), dtype=mesh.VERT3_t)
    mesh.vert3["coord"] = pts * radius
    tri = triangulate(pts)
    mesh.tria3 = np.zeros(len(tri), dtype=mesh.TRIA3_t)
    mesh.tria3["index"] = tri
    return mesh

