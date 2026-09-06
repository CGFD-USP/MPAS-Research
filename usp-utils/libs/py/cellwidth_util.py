#!/usr/bin/env python
#
#  Cell-width profiles for MPAS meshes with a buffer / transition zone.
#
#  A regional MPAS mesh built by create_regional_grid.py used to be uniform: the
#  whole domain sat at the target spacing and the coarse ramp towards the global
#  background was discarded by the cut. That makes the lateral boundary jump
#  straight from the driving-data spacing (GFS 0.25 deg ~ 25 km) to the regional
#  spacing (e.g. 5 km) in a single step.
#
#  This module describes the alternative: a buffer ring INSIDE the regional
#  domain, over which the spacing coarsens smoothly from the target resolution
#  to the driving-data resolution, so the LBC-driven flow can adjust gradually.
#
#  Profile as a function of s, the signed distance (km) to the boundary of the
#  area of interest (negative inside):
#
#      h(s) = r                                    s <= 0        (1) core
#      h(s) = r + (r_outer - r) * S(s / W)         0 < s <= W    (2) ramp
#      h(s) = r_outer                              W < s <= W+P  (3) plateau
#      h(s) = min(r_outer + (s-W-P)*slope, l)      s > W+P       (4) outer ramp
#
#  Segment 3 is flat on purpose: MPAS-Limited-Area grows its 7 relaxation rings
#  OUTWARD from the region boundary, and limited-area practice is for that belt
#  to be locally uniform and comparable to the driving data. The region is
#  therefore cut part-way into the plateau (see BufferSpec.cut_offset) so every
#  ring lands in the flat band. Segment 4 is discarded by the cut.
#
#  Deliberately depends on numpy only, so the profile maths can be checked
#  without jigsawpy / mpas_tools installed.
#
#  by Claude (USP MPAS-Research) 2026
#

from dataclasses import dataclass

import numpy as np

# MPAS-Limited-Area marks num_boundary_layers = 8 layers but writes
# bdyMaskCell - 1, so a regional mesh carries 7 relaxation rings outside the
# boundary given in the points file (verified against limited_area.py and
# against the bdyMaskCell histogram of an existing regional mesh).
RELAX_LAYERS = 7

# tanh never reaches its asymptotes; TANH_EPS is the fraction of the jump left
# at each end before renormalisation, which is then divided out so the profile
# hits r and r_outer exactly.
TANH_EPS = 0.01

PROFILES = ("tanh", "smoothstep", "smootherstep", "cosine", "linear")

_TANH_A = float(np.arctanh(1.0 - 2.0 * TANH_EPS))

# C = max|S'(t)| for each shape function. This is what converts a target
# cell-to-cell growth ratio into a ramp width; see ramp_width_from_growth.
SHAPE_MAX_SLOPE = {
    "linear": 1.0,
    "cosine": float(np.pi / 2.0),
    "smoothstep": 1.5,
    "smootherstep": 1.875,
    "tanh": _TANH_A / (1.0 - 2.0 * TANH_EPS),
}


def blend_shape(t, profile="tanh"):
    """
    Shape function S(t) of the ramp, with S(0) = 0 and S(1) = 1.

    Parameters
    ----------
    t : array_like
        Normalised position across the ramp; clipped to [0, 1].
    profile : str
        One of PROFILES.

    Returns
    -------
    ndarray
        S(t), in [0, 1].
    """
    t = np.clip(np.asarray(t, dtype=float), 0.0, 1.0)

    if profile == "linear":
        return t
    if profile == "smoothstep":
        return t * t * (3.0 - 2.0 * t)
    if profile == "smootherstep":
        return t * t * t * (t * (6.0 * t - 15.0) + 10.0)
    if profile == "cosine":
        return 0.5 * (1.0 - np.cos(np.pi * t))
    if profile == "tanh":
        raw = 0.5 * (1.0 + np.tanh(2.0 * _TANH_A * (t - 0.5)))
        return np.clip((raw - TANH_EPS) / (1.0 - 2.0 * TANH_EPS), 0.0, 1.0)

    raise ValueError("Unknown buffer profile %r (expected one of %s)"
                     % (profile, ", ".join(PROFILES)))


def _check_profile(profile):
    if profile not in SHAPE_MAX_SLOPE:
        raise ValueError("Unknown buffer profile %r (expected one of %s)"
                         % (profile, ", ".join(PROFILES)))
    return SHAPE_MAX_SLOPE[profile]


def ramp_width_from_growth(r, r_outer, growth, profile="tanh"):
    """
    Width (km) of the ramp that keeps the cell-to-cell growth ratio below
    ``growth``.

    Walking outward by one cell advances s by h and increases h by (g-1)*h,
    so g(s) = 1 + dh/ds. With h(s) = r + (r_outer - r) * S(s/W) the steepest
    point is dh/ds = C * (r_outer - r) / W, hence

        W = C * (r_outer - r) / (growth - 1)

    where C = max|S'| depends only on the profile shape.
    """
    if growth <= 1.0:
        raise ValueError("buffer growth ratio must be > 1 (got %r)" % (growth,))
    c = _check_profile(profile)
    return c * (float(r_outer) - float(r)) / (growth - 1.0)


def growth_from_ramp_width(r, r_outer, width, profile="tanh"):
    """Inverse of ramp_width_from_growth: max cell-to-cell ratio for a width."""
    if width <= 0.0:
        raise ValueError("buffer width must be > 0 (got %r)" % (width,))
    c = _check_profile(profile)
    return 1.0 + c * (float(r_outer) - float(r)) / float(width)


def ramp_cell_count(r, r_outer, width, profile="tanh", n=2001):
    """
    Approximate number of cells across the ramp, integral of ds / h(s).

    Useful as a sanity check: a ramp only a handful of cells wide is not a
    smooth transition however nice the shape function looks.
    """
    s = np.linspace(0.0, float(width), n)
    h = float(r) + (float(r_outer) - float(r)) * blend_shape(s / float(width),
                                                             profile)
    trapezoid = getattr(np, "trapezoid", None) or np.trapz
    return float(trapezoid(1.0 / h, s))


@dataclass(frozen=True)
class BufferSpec:
    """
    Everything needed to evaluate the buffered cell-width profile.

    Attributes
    ----------
    r : float
        Target spacing (km) over the area of interest.
    r_outer : float
        Spacing (km) at the outer edge of the regional domain; normally the
        lateral-BC driving resolution.
    width : float
        Width (km) of the ramp from r to r_outer.
    profile : str
        Ramp shape, one of PROFILES.
    n_pre : int
        Cells of flat r_outer placed INSIDE the cut boundary. Absorbs the
        one-cell jitter of the region-marking walk.
    n_post : int
        Cells of flat r_outer kept beyond the outermost relaxation ring before
        the discarded outer ramp starts.
    l : float
        Global background spacing (km); the outer ramp is clipped here.
    outer_slope : float
        Slope (km per km) of the discarded outer ramp.
    """

    r: float
    r_outer: float
    width: float
    profile: str = "tanh"
    n_pre: int = 2
    n_post: int = 3
    l: float = 200.0
    outer_slope: float = 100.0 / 600.0

    @property
    def plateau_width(self):
        """Width (km) of the flat r_outer band (segment 3)."""
        return (self.n_pre + RELAX_LAYERS + self.n_post) * self.r_outer

    @property
    def cut_offset(self):
        """
        Distance (km) from the area-of-interest boundary to the cut boundary
        written in the points file. The 7 relaxation rings grow outward from
        here, into the rest of the plateau.
        """
        return self.width + self.n_pre * self.r_outer

    @property
    def mesh_offset(self):
        """Distance (km) from the area of interest to the outer mesh edge."""
        return self.cut_offset + RELAX_LAYERS * self.r_outer

    @property
    def total_offset(self):
        """Distance (km) at which the discarded outer ramp starts."""
        return self.width + self.plateau_width

    @property
    def growth(self):
        """Max cell-to-cell growth ratio implied by width and profile."""
        return growth_from_ramp_width(self.r, self.r_outer, self.width,
                                      self.profile)

    @property
    def ramp_cells(self):
        """Approximate number of cells across the ramp."""
        return ramp_cell_count(self.r, self.r_outer, self.width, self.profile)

    def validate(self):
        """Return a list of human-readable warnings (empty if all is well)."""
        warnings = []
        if self.growth > 1.20:
            warnings.append(
                "cell-to-cell growth ratio is %.3f, above the ~1.15 usually "
                "recommended for MPAS meshes. jigsaw applies no gradient "
                "limiter, so a ramp this sharp will show up as poor cell "
                "quality. Widen it with --buffer-width or lower "
                "--buffer-decay." % self.growth)
        if self.ramp_cells < 8:
            warnings.append(
                "the ramp is only ~%.1f cells wide; that is a step rather "
                "than a transition." % self.ramp_cells)
        if self.r_outer >= self.l:
            warnings.append(
                "--buffer-res (%.1f km) is not smaller than the background "
                "spacing -l (%.1f km); the discarded outer ramp will be flat."
                % (self.r_outer, self.l))
        return warnings


def buffered_cellwidth(s, spec, out=None):
    """
    Evaluate the four-segment cell-width profile.

    Parameters
    ----------
    s : ndarray
        Signed distance (km) to the boundary of the area of interest, negative
        inside.
    spec : BufferSpec
    out : ndarray, optional
        Pre-allocated output array (same shape as ``s``), to keep peak memory
        down when sweeping a large lat/lon grid in chunks.

    Returns
    -------
    ndarray
        Cell width in km.
    """
    s = np.asarray(s)
    if out is None:
        out = np.empty(s.shape, dtype=float)

    w = spec.width
    plateau_end = spec.total_offset

    # (1) core, and the default everywhere before the masks below refine it
    out.fill(spec.r)

    # (2) ramp
    ramp = (s > 0.0) & (s <= w)
    if ramp.any():
        t = s[ramp] / w
        out[ramp] = spec.r + (spec.r_outer - spec.r) * blend_shape(t,
                                                                   spec.profile)

    # (3) flat plateau covering the relaxation rings
    plateau = (s > w) & (s <= plateau_end)
    out[plateau] = spec.r_outer

    # (4) discarded ramp out to the global background
    far = s > plateau_end
    if far.any():
        out[far] = np.minimum(
            spec.r_outer + (s[far] - plateau_end) * spec.outer_slope, spec.l)

    return out


def describe(spec, core_radius=None, core_label="area of interest"):
    """
    Human-readable summary of the resolved geometry.

    ``core_radius`` is the radius (km) of the area of interest for circular
    regions; for other shapes pass None and only the offsets are reported.
    """
    lines = []
    add = lines.append

    def at(offset):
        if core_radius is None:
            return "+%.1f km" % offset
        return "%.1f km" % (core_radius + offset)

    add("Buffer / transition zone")
    add("------------------------")
    if core_radius is not None:
        add("  %-34s %8.1f km" % (core_label + " (R_core)", core_radius))
    add("  %-34s %8.1f km  (%.1f -> %.1f km, %s)"
        % ("buffer ramp width", spec.width, spec.r, spec.r_outer,
           spec.profile))
    add("  %-34s %8.3f    (~%.1f cells across the ramp)"
        % ("max cell-to-cell growth ratio", spec.growth, spec.ramp_cells))
    add("  %-34s %8.1f km  (%d pre + %d relaxation + %d post cells)"
        % ("flat %.1f km plateau" % spec.r_outer, spec.plateau_width,
           spec.n_pre, RELAX_LAYERS, spec.n_post))
    add("  %-34s %8s" % ("LBC zone starts (points file)", at(spec.cut_offset)))
    add("  %-34s %8s  (%d relaxation rings beyond it,"
        % ("regional mesh outer edge", at(spec.mesh_offset), RELAX_LAYERS))
    add("  %-34s %8s   all kept in the mesh)" % ("", ""))
    add("  %-34s %8s  (discarded by the cut)"
        % ("outer ramp to %.0f km starts at" % spec.l, at(spec.total_offset)))
    return "\n".join(lines)
