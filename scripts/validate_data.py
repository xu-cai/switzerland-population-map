#!/usr/bin/env python3
"""Independently check serialized browser data, provenance hashes and arithmetic."""

import hashlib
import json
import math
import sys
from pathlib import Path


def validate(directory: Path) -> None:
    metadata = json.loads((directory / "metadata.json").read_text())
    grid = json.loads((directory / "grid.json").read_text())
    assert grid["epsg"] == 21781 and grid["anchor"] == "southwest"
    assert grid["columns"] == ["e", "n", "population", "noloc"]
    assert grid["privacy_grouped_range"] == [1, 3]
    cells = grid["cells"]
    assert len({(row[0], row[1]) for row in cells}) == len(cells)
    for e, n, population, noloc in cells:
        assert 400000 < e < 900000 and 0 < n < 400000
        assert math.isfinite(e) and math.isfinite(n)
        assert type(population) is int and population >= 3
        assert noloc in (0, 1)
    upper = sum(row[2] for row in cells)
    grouped = sum(row[2] == 3 for row in cells)
    evidence = metadata["validation"]
    assert evidence["grid"] == {"cells": len(cells), "population_lower": upper - 2 * grouped,
                                 "population_upper": upper, "privacy_grouped_cells": grouped,
                                 "noloc_cells": sum(row[3] for row in cells)}
    assert metadata["population_date"].startswith(str(grid["year"]))
    assert metadata["boundary_date"] >= metadata["population_date"]
    official_matches = 0
    for level in ["municipalities", "districts", "cantons"]:
        collection = json.loads((directory / f"{level}.geojson").read_text())
        assert collection["type"] == "FeatureCollection"
        features = collection["features"]
        assert len({feature["id"] for feature in features}) == len(features)
        for feature in features:
            props = feature["properties"]
            assert props["id"] == feature["id"]
            assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
            polygons = feature["geometry"]["coordinates"]
            if feature["geometry"]["type"] == "Polygon":
                polygons = [polygons]
            for polygon in polygons:
                for index, ring in enumerate(polygon):
                    assert ring[0] == ring[-1]
                    signed_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
                    assert signed_area > 0 if index == 0 else signed_area < 0
            assert props["area_km2"] > 0
            assert props["grid_population_lower"] == props["grid_population_upper"] - 2 * props["grid_grouped_cells"]
            assert props["grid_privacy_affected"] == (props["grid_grouped_cells"] > 0)
            assert props["grid_noloc_cells"] <= props["grid_cell_count"]
            assert abs(props["density_per_km2"] - props["population"] / props["area_km2"]) <= 0.000501
            if props["population_source"] == "official_municipality":
                assert level == "municipalities" and not props["population_is_estimate"]
                official_matches += 1
            else:
                assert props["population_source"] == "grid_upper_estimate"
                assert props["population_is_estimate"]
                assert props["population"] == props["grid_population_upper"]
        assigned = sum(feature["properties"]["grid_population_upper"] for feature in features)
        assigned_cells = sum(feature["properties"]["grid_cell_count"] for feature in features)
        report = evidence["levels"][level]
        assert assigned == report["assigned_population_upper"]
        assert assigned + report["unassigned"]["population_upper"] == upper
        assert assigned_cells + report["unassigned"]["cells"] == len(cells)
        assert report["features"] == len(features)
        print(f"{level}: {len(features)} features; assigned {assigned:,}; unassigned {report['unassigned']['population_upper']:,}")
    assert official_matches == evidence["official_totals_matched"]
    matched_population = sum(feature["properties"]["population"] for feature in
                             json.loads((directory / "municipalities.geojson").read_text())["features"]
                             if feature["properties"]["population_source"] == "official_municipality")
    assert matched_population + sum(row["BBTOT"] for row in evidence["official_totals_unmatched"]) == evidence["official_municipality_population"]
    for filename, report in metadata["outputs"].items():
        data = (directory / filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == report["sha256"]
        assert len(data) == report["bytes"]
    print(f"PASS: {len(cells):,} cells, privacy range {upper - 2 * grouped:,}–{upper:,}; {official_matches} official municipality joins; output hashes verified")


if __name__ == "__main__":
    validate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "dist" / "data")
