#!/usr/bin/env python
#
#  Interactive tool to draw a regional-mesh boundary on a map.
#
#  Click to place polygon vertices on a cartopy map; the tool writes a
#  "lat, lon" points file that create_regional_grid.py --shape polygon reads:
#
#      python create_regional_grid.py -r 30 -l 200 \
#             --shape polygon --polygon-file <output> -o my_region
#
#  Controls
#  --------
#      left click    add a vertex
#      right click   undo the last vertex
#      'c'           clear all vertices
#      enter         save and quit
#      escape        quit without saving
#
#  Needs an INTERACTIVE matplotlib backend (a display). On a headless server,
#  run it on your local machine or over SSH X forwarding (ssh -X).
#

import argparse
import os
import sys

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

PLATE = ccrs.PlateCarree()


def ensure_ccw(points):
    """
    Return the boundary points in counter-clockwise order (as expected by
    MPAS-Limited-Area), using the shoelace signed area on (lon, lat).
    ``points`` is a list of (lat, lon) tuples.
    """
    area = 0.0
    n = len(points)
    for i in range(n):
        lat1, lon1 = points[i]
        lat2, lon2 = points[(i + 1) % n]
        area += lon1 * lat2 - lon2 * lat1
    if area < 0.0:  # clockwise -> reverse to make it CCW
        points = points[::-1]
    return points


def save_polygon(points, output):
    """Write (lat, lon) points to a polygon file, CCW, with a header."""
    if len(points) < 3:
        print("Need at least 3 vertices; not saving.")
        return False
    points = ensure_ccw(points)
    with open(output, "w") as f:
        f.write("# region boundary drawn with draw_region.py (lat, lon), CCW\n")
        for lat, lon in points:
            f.write("%.4f, %.4f\n" % (lat, lon))
    print("Saved %d vertices -> %s" % (len(points), output))
    print("Now run, e.g.:")
    print("  python create_regional_grid.py -r 30 -l 200 \\")
    print("         --shape polygon --polygon-file %s -o my_region -p"
          % output)
    return True


class RegionDrawer:
    """Collect polygon vertices from mouse clicks on a cartopy axis."""

    def __init__(self, ax, output):
        self.ax = ax
        self.output = output
        self.lats = []
        self.lons = []
        self.saved = False
        (self.line,) = ax.plot([], [], '-o', color='red', markersize=5,
                               linewidth=1.5, transform=PLATE)
        canvas = ax.figure.canvas
        canvas.mpl_connect('button_press_event', self.on_click)
        canvas.mpl_connect('key_press_event', self.on_key)
        self._update_title()

    def on_click(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        if event.button == 1:            # left -> add vertex
            self.lons.append(float(event.xdata))
            self.lats.append(float(event.ydata))
        elif event.button == 3:          # right -> undo last
            if self.lons:
                self.lons.pop()
                self.lats.pop()
        self._redraw()

    def on_key(self, event):
        if event.key == 'enter':
            self.saved = save_polygon(list(zip(self.lats, self.lons)),
                                      self.output)
            plt.close(self.ax.figure)
        elif event.key == 'escape':
            plt.close(self.ax.figure)
        elif event.key == 'c':
            self.lons.clear()
            self.lats.clear()
            self._redraw()

    def _redraw(self):
        # close the polygon visually once there are >= 3 vertices
        xs = list(self.lons)
        ys = list(self.lats)
        if len(xs) > 2:
            xs.append(self.lons[0])
            ys.append(self.lats[0])
        self.line.set_data(xs, ys)
        self._update_title()
        self.ax.figure.canvas.draw_idle()

    def _update_title(self):
        self.ax.set_title(
            "vertices: %d   |   left=add  right=undo  c=clear  "
            "enter=save  esc=quit" % len(self.lons))


def main(args):
    fig, ax = plt.subplots(figsize=(10, 8), subplot_kw={'projection': PLATE})
    ax.set_extent([args.lon_min, args.lon_max, args.lat_min, args.lat_max],
                  crs=PLATE)
    ax.add_feature(cfeature.LAND, facecolor='#f3efe6')
    ax.add_feature(cfeature.OCEAN, facecolor='#dbe9f6')
    ax.coastlines('50m', linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor='gray')
    gl = ax.gridlines(draw_labels=True, linewidth=0.3, color='gray', alpha=0.5)
    gl.top_labels = False
    gl.right_labels = False

    drawer = RegionDrawer(ax, args.output)
    print(__doc__)
    plt.show()

    if not drawer.saved:
        print("Exited without saving.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument(
        "-o", "--output", dest="output",
        required=False, default="region.txt", type=str,
        help="Output polygon file (lat, lon per line) (default: region.txt)",
        metavar="PATH")

    # Initial map view (pan/zoom with the toolbar afterwards).
    parser.add_argument("--lat-min", dest="lat_min", default=-60.0, type=float,
                        help="Initial map south edge (default: -60)",
                        metavar="FLOAT")
    parser.add_argument("--lat-max", dest="lat_max", default=20.0, type=float,
                        help="Initial map north edge (default: 20)",
                        metavar="FLOAT")
    parser.add_argument("--lon-min", dest="lon_min", default=-95.0, type=float,
                        help="Initial map west edge (default: -95)",
                        metavar="FLOAT")
    parser.add_argument("--lon-max", dest="lon_max", default=-20.0, type=float,
                        help="Initial map east edge (default: -20)",
                        metavar="FLOAT")

    args = parser.parse_args()
    main(args)
