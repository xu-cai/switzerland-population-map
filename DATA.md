# Official population data

## Sources and dates

Prepared from the official [geo.admin STAC API](https://data.geo.admin.ch/api/stac/v0.9/):

- **STATPOP 2025**, reference date **31 December 2025**, publication year 2026, latest population year available when prepared. Collection `ch.bfs.statistik-bevoelkerung_haushalte`, item `statistik-bevoelkerung_haushalte_2025`; hectare and municipality CSV assets, EPSG:2056. Hectare asset updated 17 September 2026.
- **swissBOUNDARIES3D**, latest item **`swissboundaries3d_2026-01`**, boundary date **1 January 2026**. Collection `ch.swisstopo.swissboundaries3d`; EPSG:2056 GeoPackage ZIP. Switzerland only; foreign municipalities, communal territories and non-municipality cantonal territories are not included in the municipality file. The district/canton files use their respective official polygon layers.
- Official [STATPOP description, 2026, French](https://dam-api.bfs.admin.ch/hub/api/dam/assets/36755795/master), pp. 3–5, and [variable dictionary](https://dam-api.bfs.admin.ch/hub/api/dam/assets/36755793/master). These confirm `BBTOT` = permanent resident population, southwest hectare anchoring, privacy grouping and `NOLOC` semantics.
- The [swisstopo CHENyx06 correction grid distributed by PROJ](https://cdn.proj.org/ch_swisstopo_CHENyx06a.tif) supports the actual LV95 → LV03 transformation. Mere subtraction of 2,000,000/1,000,000 would omit local datum corrections.

`dist/data/metadata.json` records exact source URLs, STAC dates, SHA-256 hashes, transformation operation, dependency versions, output hashes and validation results. STATPOP and boundary archives are verified against their STAC SHA-256 multihashes before processing.

Attribution: **Statistique de la population et des ménages (STATPOP), OFS GEOSTAT**; **Boundaries: swisstopo**. STATPOP is OPEN BY ([terms](https://opendata.swiss/en/terms-of-use/#terms_by)); see also [swisstopo terms](https://www.swisstopo.admin.ch/en/terms-and-conditions). These are derived display data, not official published administrative totals except where explicitly labelled.

## Browser schema

All files are compact UTF-8 JSON, directly fetchable without special hosting configuration.

### `grid.json`

Object with `schema_version: 1`, `year: 2025`, `epsg: 21781`, `anchor: "southwest"`, `cell_size_m: 100`, `coordinate_precision_m: 0.01`, `columns: ["e","n","population","noloc"]`, privacy metadata, and `cells` containing rows in that order.

- `e`, `n`: **EPSG:21781 metres**, easting then northing; transformed southwest corner, rounded to centimetres. Source `E_KOORD`, `N_KOORD` are EPSG:2056 southwest corners on the 100 m lattice, independently checked against `RELI`. Transformation uses CHENyx06 and prohibits ballpark fallback. This is the transformed LV95 lattice, **not** a reaggregation to integer LV03 hectares. Drawing a 100 m square from each transformed corner approximates the slightly distorted transformed cell; not suitable for surveying. Use EPSG:21781, not EPSG:2056, to convert these output coordinates to longitude/latitude.
- `population`: published permanent-resident `BBTOT`. **A value of 3 means 1–3 people, never an exact count of 3.** Values above 3 are published counts. Display grouped cells as “1–3”. For a source hectare, persons/km² is population × 100 (the grouped range is 100–300).
- `noloc`: 1 marks a collective hectare containing people assigned to municipality-centre coordinates because their precise address/EGID is unavailable. A flagged cell can also contain precisely located residents. This flag is not the number of unlocated persons. Cells are retained without redistribution or double-counting from the separate NOLOC table.

### `municipalities.geojson`, `districts.geojson`, `cantons.geojson`

RFC 7946-style FeatureCollections; 2D WGS84 **longitude, latitude**, polygon/multipolygon geometries. Feature IDs and `properties.id` use official BFS municipality, district or canton numbers. Properties:

| Property | Meaning |
| --- | --- |
| `name`, `canton_id`, `district_id` | Official name/hierarchy; municipality `district_id` may be null in cantons without districts. |
| `area_km2` | Original unsimplified EPSG:2056 polygon area, including water inside the polygon. |
| `population` | Preferred official municipality total when both BFS ID and historical ID match; otherwise published grid sum (upper estimate). |
| `population_source` | `official_municipality` or `grid_upper_estimate`. |
| `population_is_estimate` | False only for the matched official municipality totals. |
| `density_per_km2` | `population / area_km2`, rounded to 3 decimals; inherits population's estimate status. |
| `grid_population_lower`, `grid_population_upper` | Assigned-cell sum with every grouped cell contributing 1 or 3 respectively. These are privacy ranges, **not bounds on spatial assignment error**. |
| `grid_cell_count`, `grid_grouped_cells`, `grid_noloc_cells` | Assigned, privacy-grouped and collective-cell counts. |
| `grid_privacy_affected` | Whether the separate grid sum contains grouped cells; applies even when preferred `population` is official. |

Grid assignment uses the **source EPSG:2056 southwest corner intersecting original unsimplified boundaries**, consistent with the documented FSO corner convention. All of a cell's published count goes to that polygon; no area weighting or building-level assignment. Exact shared-boundary ties use the lowest official ID. Outside points remain unassigned: no nearest-region fallback. Each administrative level is assigned independently; do not expect district sums to cover cantons without districts, or official municipality totals to equal grid-derived canton/district sums.

Display geometries use 20 m topology-preserving simplification **per feature**, then 6-decimal WGS84 precision. Adjacent simplified borders may diverge slightly. Statistics and spatial assignment use the original geometry, never display geometry.

## Accuracy and observed validation

- **347,956 cells**; **74,825** have privacy code 3. Published grid sum: **9,200,103**; privacy lower sum: **9,050,453**. Neither is an official national count. Official municipality table total: **9,127,125**.
- **1,920 NOLOC-flagged cells**: local spikes may represent collective coordinates, not actual residential concentrations.
- **2,110 municipalities**, **135 districts**, **26 cantons**. Original and emitted geometries pass validity checks.
- Official totals match **2,105 municipalities** by both BFS and historical ID. Five 2026 municipalities (Fétigny-Ménières, Moutier, Gurmels, Kriegstetten, Brugg) use grid estimates because of mergers/renumbering/changed historical versions. Ten unmatched 2025 source rows are listed in metadata; no speculative merger mapping is applied.
- Source headers, survey years, integer counts, 100 m source lattice, unique keys/coordinates, coordinate/key consistency, CRS declarations, checksums and projection roundtrip are checked. Maximum unrounded transform roundtrip error was below **0.000001 m**; this numerical consistency does not imply survey accuracy.
- Assignment conservation was verified separately at each level: assigned sum + unassigned sum = **9,200,103**. Municipality unassigned: **506 cells / 7,175 published count**; district unassigned: **31,834 / 1,250,634** (including areas without districts); canton unassigned: **167 / 2,272**. No shared-corner ties occurred in this release. Small municipality/canton residuals can arise from border-crossing hectares and excluded non-municipality areas; they are not silently reassigned.

Privacy grouping biases raw sums upward. Southwest assignment can move all residents of a border-crossing hectare to one administrative unit, even if buildings lie in another. The 2025 territorial reference and latest 2026 boundaries differ. `population_is_estimate` and source labels must remain visible in derived use. Density uses total polygon area, not inhabited or land-only area.

## Rerun

Python 3.12+ with a working PROJ/GDAL wheel environment (verified here on Python 3.14):

```sh
python3 -m venv /tmp/swiss-population-venv
/tmp/swiss-population-venv/bin/pip install -r scripts/requirements.txt
/tmp/swiss-population-venv/bin/python scripts/prepare_data.py
/tmp/swiss-population-venv/bin/python scripts/validate_data.py
/tmp/swiss-population-venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

The pipeline defaults to **2025**, discovers all STAC pages and chooses the latest boundary item by reference date. It downloads raw files only to the platform temporary directory (`tempfile.gettempdir()/swiss-population-raw`), caching them with checksum validation. Override with `--cache /path/to/temp-cache`, `--output /path/to/output`, or an explicitly chosen `--year`. It writes only the five named files in the output directory; no UI/hosting configuration is modified. Network/source/schema errors fail visibly; review and remove only an identified corrupt cached file if checksum validation fails.

Identical source assets and dependencies reproduce the four data-file hashes; metadata additionally contains a new generation timestamp. Future official revisions or a newer boundary item intentionally change results; retained metadata identifies the exact release used here. The cache must remain available for a no-redownload rerun; STAC discovery still requires the network.
