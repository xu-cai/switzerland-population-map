"""Small boundary/failure-path checks for the preparation helpers."""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box

from prepare_data import assign_grid, download, grid_summary


class PreparationTests(unittest.TestCase):
    def test_grouped_count_range_is_not_exact_three(self):
        points = gpd.GeoDataFrame({"BBTOT": [3, 4], "NOLOC": [1, 0]},
                                  geometry=[Point(0, 0), Point(1, 1)], crs=2056)
        self.assertEqual(grid_summary(points), {"cells": 2, "population_lower": 5,
                                               "population_upper": 7, "privacy_grouped_cells": 1,
                                               "noloc_cells": 1})

    def test_shared_corner_assigned_once_to_lowest_id(self):
        points = gpd.GeoDataFrame({"BBTOT": [3], "NOLOC": [0]}, geometry=[Point(1, 1)], crs=2056)
        regions = gpd.GeoDataFrame({"id": [20, 10]}, geometry=[box(0, 0, 1, 2), box(1, 0, 2, 2)], crs=2056)
        totals, evidence = assign_grid(points, regions)
        self.assertEqual(totals.index.tolist(), [10])
        self.assertEqual(totals.loc[10, "grid_population_upper"], 3)
        self.assertEqual(evidence["boundary_tie_extra_matches"], 1)

    def test_outside_cells_are_not_forced_into_a_region(self):
        points = gpd.GeoDataFrame({"BBTOT": [5, 3], "NOLOC": [0, 1]},
                                  geometry=[Point(0, 0), Point(4, 4)], crs=2056)
        regions = gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 2, 2)], crs=2056)
        totals, evidence = assign_grid(points, regions)
        self.assertEqual(totals.loc[1, "grid_population_upper"], 5)
        self.assertEqual(evidence["unassigned"]["population_lower"], 1)
        self.assertEqual(evidence["unassigned"]["population_upper"], 3)
        self.assertEqual(evidence["unassigned"]["noloc_cells"], 1)

    def test_corrupt_cached_source_fails_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.csv"
            path.write_text("corrupt")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                download("https://example.invalid/not-requested", path, "1220" + "0" * 64)


if __name__ == "__main__":
    unittest.main()
