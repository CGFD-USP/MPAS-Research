#!/usr/bin/env python3
"""Small regression tests for the OISST coastal-safe land extension."""

import unittest

import numpy as np

from oisst_land_fill import fill_land_sst_nearest_ocean


class TestOisstLandFill(unittest.TestCase):
    def test_preserves_ocean_and_fills_land(self):
        source = np.array(
            [
                [20.0, np.nan, 22.0],
                [21.0, np.nan, 23.0],
            ]
        )
        filled, land = fill_land_sst_nearest_ocean(source)

        np.testing.assert_array_equal(filled[~land], source[~land])
        self.assertTrue(np.isfinite(filled).all())
        np.testing.assert_array_equal(land, ~np.isfinite(source))

    def test_longitude_is_periodic(self):
        source = np.full((3, 6), np.nan)
        source[:, 2] = 10.0
        source[:, 5] = 25.0

        filled, _ = fill_land_sst_nearest_ocean(source)

        np.testing.assert_array_equal(filled[:, 0], 25.0)

    def test_rejects_field_without_ocean(self):
        with self.assertRaisesRegex(ValueError, "no finite ocean"):
            fill_land_sst_nearest_ocean(np.full((2, 3), np.nan))


if __name__ == "__main__":
    unittest.main()
