"""Coastal-safe SST filling for OISST WPS intermediate files.

MPAS ``init_atmosphere`` case 8 currently interpolates the SST slab with
``FOUR_POINT``/``SEARCH`` while asking for the source mask value ``-1``.
OISST ``LANDSEA`` is encoded as 0 (water) and 1 (land), so neither value is
rejected by that interpolation path.  A finite constant over land therefore
enters the bilinear interpolation at coastal ocean cells.

This module keeps ``LANDSEA`` unchanged and replaces missing land SST with the
nearest valid ocean SST before writing the intermediate file.  The native MPAS
interpolation is not modified; it simply receives an ocean-consistent finite
extension at points that can contribute to a coastal stencil.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt


def fill_land_sst_nearest_ocean(sst_c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return coastal-safe SST (degC) and the original OISST land mask.

    Longitude is treated as periodic by tripling the regular global grid and
    retaining the centre copy.  Valid ocean values are preserved bit-for-bit.
    The nearest-neighbour extension is only a numerical guard for interpolation;
    ``LANDSEA`` remains the authoritative 1=land / 0=water classification.
    """

    source = np.asarray(sst_c)
    if source.ndim != 2:
        raise ValueError(f"expected a 2-D SST field, got shape {source.shape}")

    ocean = np.isfinite(source)
    if not ocean.any():
        raise ValueError("OISST field has no finite ocean SST values")

    land = ~ocean
    filled = source.copy()
    if not land.any():
        return filled, land

    nlon = source.shape[1]
    tiled_source = np.tile(source, (1, 3))
    tiled_land = ~np.isfinite(tiled_source)
    nearest = distance_transform_edt(
        tiled_land,
        return_distances=False,
        return_indices=True,
    )
    nearest_values = tiled_source[tuple(nearest)][:, nlon : 2 * nlon]
    filled[land] = nearest_values[land]

    if not np.isfinite(filled).all():
        raise RuntimeError("nearest-ocean SST extension left non-finite values")
    if not np.array_equal(filled[ocean], source[ocean]):
        raise RuntimeError("nearest-ocean SST extension modified source ocean values")

    return filled, land
