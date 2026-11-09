#!/usr/bin/env python3
"""Prepare official STATPOP grid and swissBOUNDARIES3D browser datasets."""

import argparse
import hashlib
import json
import logging
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely
from pyproj.transformer import TransformerGroup

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/"
POPULATION = "ch.bfs.statistik-bevoelkerung_haushalte"
BOUNDARIES = "ch.swisstopo.swissboundaries3d"
GRID_URL = "https://cdn.proj.org/ch_swisstopo_CHENyx06a.tif"
DOC_URL = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36755795/master"
DICTIONARY_URL = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36755793/master"
ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def items(collection: str) -> list[dict]:
    url = f"{STAC}{collection}/items?limit=100"
    result = []
    while url:
        page = get_json(url)
        result.extend(page["features"])
        url = next((link["href"] for link in page["links"] if link["rel"] == "next"), None)
    return sorted(result, key=lambda item: item["properties"]["datetime"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, path: Path, expected: str | None = None) -> dict:
    if not path.exists():
        logging.info("download %s", url)
        temporary = path.with_suffix(path.suffix + ".partial")
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(path)
    digest = sha256(path)
    if expected:
        require(expected.lower() == "1220" + digest, f"Checksum mismatch: {path}; remove this cache file and retry")
    return {"url": url, "sha256": digest, "bytes": path.stat().st_size}


def asset(item: dict, suffix: str, cache: Path) -> tuple[Path, dict]:
    matches = [(key, value) for key, value in item["assets"].items() if key.endswith(suffix)]
    require(len(matches) == 1, f"Expected one asset ending {suffix}")
    key, source = matches[0]
    require(source["proj:epsg"] == 2056, f"Unexpected source projection: {key}")
    path = cache / key
    provenance = download(source["href"], path, source["checksum:multihash"])
    provenance.update({"asset": key, "epsg": source["proj:epsg"], "updated": source["updated"],
                       "item": item["id"], "datetime": item["properties"]["datetime"]})
    return path, provenance


def read_table(path: Path, columns: list[str], year: int) -> tuple[pd.DataFrame, list[str]]:
    header = pd.read_csv(path, sep=";", nrows=0).columns.tolist()
    require(set(columns) <= set(header), f"Missing required CSV columns: {path}")
    frame = pd.read_csv(path, sep=";", usecols=columns)
    require(not frame.isna().any().any(), f"Missing values: {path}")
    require((frame == frame.astype("int64")).all().all(), f"Noninteger source values: {path}")
    frame = frame.astype("int64")
    require(frame.ERHJAHR.eq(year).all(), f"Unexpected survey year: {path}")
    require(frame.BBTOT.ge(0).all(), f"Negative population: {path}")
    return frame, header


def grid_transform(cache: Path) -> tuple[pyproj.Transformer, dict]:
    path = cache / "ch_swisstopo_CHENyx06a.tif"
    provenance = download(GRID_URL, path)
    pyproj.datadir.append_data_dir(str(cache))
    group = TransformerGroup(2056, 21781, always_xy=True, allow_ballpark=False)
    require(group.best_available and bool(group.transformers), "Precise LV95 → LV03 transformation unavailable")
    transformer = group.transformers[0]
    provenance.update({"operation": transformer.description, "accuracy_m": transformer.accuracy})
    return transformer, provenance


def grid_summary(frame: pd.DataFrame) -> dict:
    upper = int(frame.BBTOT.sum())
    grouped = int(frame.BBTOT.eq(3).sum())
    return {"cells": len(frame), "population_lower": upper - 2 * grouped,
            "population_upper": upper, "privacy_grouped_cells": grouped,
            "noloc_cells": int(frame.NOLOC.sum())}


def assign_grid(points: gpd.GeoDataFrame, regions: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    # Intersects includes border points; use the lowest official ID for exact ties.
    joined = gpd.sjoin(points, regions[["id", "geometry"]], how="left", predicate="intersects")
    ties = int(joined.index.duplicated().sum())
    joined = joined.reset_index(names="cell").sort_values(["cell", "id"], na_position="last")
    joined = joined.drop_duplicates("cell").set_index("cell").sort_index()
    unassigned = joined.loc[joined.id.isna()]
    assigned = joined.loc[joined.id.notna()].copy()
    assigned["grouped"] = assigned.BBTOT.eq(3).astype(int)
    totals = assigned.groupby("id").agg(grid_population_upper=("BBTOT", "sum"),
                                         grid_cell_count=("BBTOT", "size"),
                                         grid_grouped_cells=("grouped", "sum"),
                                         grid_noloc_cells=("NOLOC", "sum"))
    totals["grid_population_lower"] = totals.grid_population_upper - 2 * totals.grid_grouped_cells
    require(int(totals.grid_population_upper.sum()) + int(unassigned.BBTOT.sum()) == int(points.BBTOT.sum()),
            "Population assignment conservation failed")
    require(int(totals.grid_cell_count.sum()) + len(unassigned) == len(points), "Cell conservation failed")
    return totals, {"unassigned": grid_summary(unassigned), "boundary_tie_extra_matches": ties,
                    "assigned_population_upper": int(totals.grid_population_upper.sum()),
                    "assigned_cells": int(totals.grid_cell_count.sum())}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def prepare(cache: Path, output: Path, year: int) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    population_items = items(POPULATION)
    boundary_items = items(BOUNDARIES)
    population = next((item for item in population_items if item["properties"]["datetime"].startswith(str(year))), None)
    require(population is not None, f"STATPOP {year} is unavailable")
    boundary = boundary_items[-1]
    grid_path, grid_source = asset(population, "_ha_2056.csv", cache)
    official_path, official_source = asset(population, "_gmde_2056.csv", cache)
    boundary_path, boundary_source = asset(boundary, ".gpkg.zip", cache)
    docs = [download(DOC_URL, cache / "statpop-description.pdf"),
            download(DICTIONARY_URL, cache / "statpop-dictionary.xlsx")]
    transformer, transform_source = grid_transform(cache)
    grid, grid_header = read_table(grid_path, ["ERHJAHR", "PUBJAHR", "RELI", "E_KOORD", "N_KOORD", "BBTOT", "NOLOC"], year)
    official, official_header = read_table(official_path, ["ERHJAHR", "PUBJAHR", "GDENR", "GDEHISTID", "BBTOT"], year)
    require(grid.NOLOC.isin([0, 1]).all(), "Unexpected NOLOC code")
    require(grid.BBTOT.ge(3).all(), "Unexpected ungrouped small count; review privacy encoding")
    require(not grid.RELI.duplicated().any(), "Duplicate hectare key")
    require(not grid.duplicated(["E_KOORD", "N_KOORD"]).any(), "Duplicate cell coordinates")
    require(((grid.E_KOORD % 100 == 0) & (grid.N_KOORD % 100 == 0)).all(), "Non-hectare source corner")
    require((grid.RELI == (grid.E_KOORD - 2000000) // 100 * 10000 + (grid.N_KOORD - 1000000) // 100).all(),
            "RELI disagrees with source southwest coordinates")
    require(not official.GDENR.duplicated().any(), "Duplicate official municipality ID")
    x, y = transformer.transform(grid.E_KOORD.to_numpy(), grid.N_KOORD.to_numpy(), errcheck=True)
    require(np.isfinite(x).all() and np.isfinite(y).all(), "Invalid LV03 coordinates")
    back_x, back_y = transformer.transform(x, y, direction="INVERSE", errcheck=True)
    roundtrip = float(max(np.max(np.abs(back_x - grid.E_KOORD)), np.max(np.abs(back_y - grid.N_KOORD))))
    require(roundtrip < 0.01, "LV03 transform roundtrip exceeds 1 cm")
    rows = [[round(float(a), 2), round(float(b), 2), int(c), int(d)]
            for a, b, c, d in zip(x, y, grid.BBTOT, grid.NOLOC)]
    points = gpd.GeoDataFrame(grid[["BBTOT", "NOLOC"]].copy(),
                              geometry=gpd.points_from_xy(grid.E_KOORD, grid.N_KOORD), crs=2056)
    with zipfile.ZipFile(boundary_path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".gpkg")]
        require(len(members) == 1, "Expected one boundary GeoPackage")
        # Extract only the selected file, never archive-provided paths.
        gpkg = cache / "swissboundaries.gpkg"
        with archive.open(members[0]) as src, gpkg.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    results = {}
    validation = {"grid": grid_summary(grid), "grid_csv_header": grid_header,
                  "official_csv_header": official_header, "transform_roundtrip_max_m": roundtrip,
                  "source_grid_epsg": 2056, "source_cell_size_m": 100,
                  "official_municipality_population": int(official.BBTOT.sum()), "levels": {}}
    matched_ids = set()
    for level, layer, key in [("municipalities", "tlm_hoheitsgebiet", "bfs_nummer"),
                               ("districts", "tlm_bezirksgebiet", "bezirksnummer"),
                               ("cantons", "tlm_kantonsgebiet", "kantonsnummer")]:
        logging.info("aggregate %s", level)
        regions = gpd.read_file(gpkg, layer=layer)
        require(regions.crs.to_epsg() == 2056, f"Unexpected boundary CRS: {layer}")
        regions = regions.loc[regions.icc.eq("CH")].copy()
        if level == "municipalities":
            regions = regions.loc[regions.objektart.eq("Gemeindegebiet")].copy()
        regions["geometry"] = shapely.force_2d(regions.geometry)
        require(regions.geometry.is_valid.all(), f"Invalid original geometry: {layer}")
        regions["id"] = regions[key].astype(int)
        require(not regions.id.duplicated().any(), f"Duplicate region IDs: {layer}")
        regions = regions.sort_values("id").reset_index(drop=True)
        regions["area_km2"] = regions.geometry.area / 1000000
        require(regions.area_km2.gt(0).all(), f"Zero-area boundary: {layer}")
        totals, evidence = assign_grid(points, regions)
        regions = regions.join(totals, on="id")
        for column in totals.columns:
            regions[column] = regions[column].fillna(0).astype("int64")
        features = []
        # PIRA: display-only per-feature generalization; use original polygons for analysis.
        display = regions.geometry.simplify(20, preserve_topology=True).to_crs(4326)
        display = gpd.GeoSeries(shapely.set_precision(display.array, 0.000001), crs=4326)
        display = gpd.GeoSeries(shapely.orient_polygons(display.array), crs=4326)
        require(display.is_valid.all() and not display.is_empty.any(), f"Invalid display geometry: {layer}")
        for index, row in regions.iterrows():
            props = {"id": int(row.id), "name": row["name"], "area_km2": round(float(row.area_km2), 6)}
            for column in totals.columns:
                props[column] = int(row[column])
            props["canton_id"] = int(row.kantonsnummer)
            if level == "municipalities":
                props["district_id"] = int(row.bezirksnummer) if pd.notna(row.bezirksnummer) else None
            # PIRA: no inferred merger mapping; extend via an official mutation table if needed.
            exact = official.loc[official.GDENR.eq(row.id) & official.GDEHISTID.eq(row.get("hist_nr", -1))]
            use_official = level == "municipalities" and len(exact) == 1
            if use_official:
                matched_ids.add(int(row.id))
            props["population"] = int(exact.iloc[0].BBTOT) if use_official else int(row.grid_population_upper)
            props["population_source"] = "official_municipality" if use_official else "grid_upper_estimate"
            props["population_is_estimate"] = not use_official
            props["grid_privacy_affected"] = bool(row.grid_grouped_cells)
            props["density_per_km2"] = round(props["population"] / props["area_km2"], 3)
            geometry = json.loads(shapely.to_geojson(display.iloc[index]))
            features.append({"type": "Feature", "id": props["id"], "properties": props, "geometry": geometry})
        results[level + ".geojson"] = {"type": "FeatureCollection", "features": features}
        evidence.update({"features": len(features), "original_crs": 2056,
                         "original_geometries_valid": True, "display_geometries_valid": True})
        validation["levels"][level] = evidence
    unmatched = official.loc[~official.GDENR.isin(matched_ids), ["GDENR", "GDEHISTID", "BBTOT"]]
    validation["official_totals_matched"] = len(matched_ids)
    validation["official_totals_unmatched"] = unmatched.to_dict("records")
    results["grid.json"] = {"schema_version": 1, "year": year, "epsg": 21781,
                             "cell_size_m": 100, "anchor": "southwest", "coordinate_precision_m": 0.01,
                             "columns": ["e", "n", "population", "noloc"], "privacy_grouped_value": 3,
                             "privacy_grouped_range": [1, 3], "cells": rows}
    metadata = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                "population_year": year, "population_date": population["properties"]["datetime"],
                "latest_population_date_available": population_items[-1]["properties"]["datetime"],
                "boundary_date": boundary["properties"]["datetime"],
                "sources": {"grid": grid_source, "official_totals": official_source, "boundaries": boundary_source,
                            "transformation_grid": transform_source, "documentation": docs},
                "attribution": ["Statistique de la population et des ménages (STATPOP), OFS GEOSTAT", "Boundaries: swisstopo"],
                "population_terms": "https://opendata.swiss/en/terms-of-use/#terms_by",
                "boundary_terms": "https://www.swisstopo.admin.ch/en/terms-and-conditions",
                "method": {"assignment": "Untransformed EPSG2056 southwest point intersects original boundary; lowest ID wins ties; no nearest fallback",
                           "privacy": "3 means 1–3; grid sums use published 3 as upper estimate, lower subtracts 2 per grouped cell",
                           "noloc": "1 marks a collective hectare containing residents not precisely geocoded, assigned to municipal centre; retained, not redistributed",
                           "official_join": "Municipality BFS ID AND historical ID must both match; no inferred merger mappings",
                           "area": "Original EPSG2056 polygon area, including water within polygon, km²",
                           "density": "population divided by area_km2; preferred official municipality count, otherwise grid upper estimate",
                           "geometry": "Display only: 20 m topology-preserving simplification per feature, WGS84 longitude/latitude rounded to 6 decimals; shared borders may diverge",
                           "grid_coordinates": "CHENyx06-corrected EPSG21781 SW corners, rounded to 0.01 m; transformed LV95 lattice, NOT re-binned to integer LV03 hectares; 100 m squares are a display approximation",
                           "levels": "Each level assigned independently, not summed from municipality features; district coverage excludes cantons without districts"},
                "limitations": ["Privacy ranges are not spatial error bounds; southwest assignment can misallocate boundary-crossing cells.",
                                "Unassigned cells are reported, not forced into regions; administrative sums can omit them.",
                                "2025 statistics and 2026 boundaries differ; changed municipalities without exact historical-ID matches use grid estimates.",
                                "NOLOC cell totals may combine precisely located and unlocated residents; flag is not a count of unlocated persons.",
                                "Grid-derived totals are not official administrative population figures."],
                "validation": validation,
                "versions": {"geopandas": gpd.__version__, "pandas": pd.__version__, "numpy": np.__version__,
                             "pyproj": pyproj.__version__, "shapely": shapely.__version__}}
    output.mkdir(parents=True, exist_ok=True)
    for filename, value in results.items():
        write_json(output / filename, value)
    metadata["outputs"] = {filename: {"sha256": sha256(output / filename), "bytes": (output / filename).stat().st_size}
                           for filename in results}
    write_json(output / "metadata.json", metadata)
    logging.info("complete cells=%d population_upper=%d official_municipalities=%d",
                 len(grid), int(grid.BBTOT.sum()), len(matched_ids))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "swiss-population-raw")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    prepare(args.cache.resolve(), args.output.resolve(), args.year)
