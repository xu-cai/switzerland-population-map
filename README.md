# Switzerland population density map

Serve the static application from `dist/`:

```sh
python3 -m http.server 8080 --directory dist
```

Open http://localhost:8080. Internet access is required for official swisstopo base-map tiles. Population and administrative data are bundled locally.

See `DATA.md` for provenance, privacy, regional estimates and regeneration.

## Verification

`node scripts/test_app.cjs` checks data integration and control logic with mocked Leaflet (not browser rendering). Official-source and data validation checks are documented in `DATA.md`. Browser visual/interaction QA remains pending because the Browser plugin was unavailable during implementation.
