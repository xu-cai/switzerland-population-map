# Switzerland population density map

Serve the static application from `dist/`:

```sh
python3 -m http.server 8080 --directory dist
```

Open http://localhost:8080. Internet access is required for official swisstopo base-map tiles. Population and administrative data are bundled locally.

See `DATA.md` for provenance, privacy, regional estimates and regeneration.

## Verification

`node scripts/test_app.cjs` checks data integration and control logic with mocked Leaflet (not browser rendering). Official-source and data validation checks are documented in `DATA.md`. Playwright MCP Chrome QA passed on 9 November 2026: real grid/region clicks, privacy and collective-coordinate warnings, all 32 level/boundary/visibility combinations, all three base maps, zoom, pointer and keyboard pan, reset, source details, and five viewport sizes. The map fills the viewport with a floating left panel at every size; on small screens the panel can be hidden and reopens when a value is selected. Full-viewport Leaflet and grid-canvas resizing are checked. `scripts/browser_qa.js` can be run through Playwright MCP using its browser_run_code_unsafe filename option after opening the app. Tile-warning recovery is tested by injecting Leaflet tile events, not by simulating a full network outage. Final screenshots are in `qa/`.

CSS and application script URLs contain content hashes to avoid stale cached assets after publication. Refresh those hashes in `dist/index.html` if either file changes.
