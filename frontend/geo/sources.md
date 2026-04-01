# Map Data Sources

> Permanent record of every map file's provenance. Update this file whenever a map file is added, replaced, or re-sourced. The rest of the system references border files by name (`borders_{era_key}.geojson`), not by source — this file is how we know where each file came from.

## Sourcing priority (for future eras)

1. **aourednik/historical-basemaps** — primary source for pre-1886 coverage (free, open, GeoJSON)
2. **CShapes 2.0** — primary source for 1886–2019 coverage (academic, GIS-compatible)
3. **Manual curation via geojson.io** — last resort for periods with no dataset coverage. Any manually curated file must be flagged below with an accuracy note.

## Border files

| Era key | Target year | Source year used | Gap | Source dataset | File | Rationale |
|---------|------------|-----------------|-----|---------------|------|-----------|
| `roman_late_empire` | 410 | 400 | -10 | aourednik/historical-basemaps `world_400.geojson` | `borders_roman_late_empire.geojson` | 10 years early. Western/Eastern Roman split and Visigothic territories established by 400. Alaric's sack of Rome (410) happens during gameplay, not before it. |
| `viking_age` | 870 | 900 | +30 | aourednik/historical-basemaps `world_900.geojson` | `borders_viking_age.geojson` | 30 years late. Norse expansion, Danelaw, and Carolingian fragmentation all visible. Acceptable — the political picture at 900 closely matches 870. |
| `crusader_states` | 1190 | 1200 | +10 | aourednik/historical-basemaps `world_1200.geojson` | `borders_crusader_states.geojson` | 10 years late. Third Crusade ended 1192. Crusader coastal strip and Ayyubid territories visible. Very close match. |
| `black_death` | 1348 | 1300 | -48 | aourednik/historical-basemaps `world_1300.geojson` | `borders_black_death.geojson` | 48 years early. Pre-plague borders for France, HRE, Italian city-states, Papal States. Earlier is better — the plague arrives and reshapes the world during gameplay. |
| `fall_of_constantinople` | 1453 | 1400 | -53 | aourednik/historical-basemaps `world_1400.geojson` | `borders_fall_of_constantinople.geojson` | 53 years early. Constantinople still Byzantine, Ottoman Empire pre-expansion. Earlier is better — the fall happens during gameplay, not before it. |

## Base layers

| File | Source | Notes |
|------|--------|-------|
| `coastlines.geojson` | Natural Earth 110m (`ne_110m_coastline.geojson`) | Static physical coastlines. 140KB. |

## Processing

All border files simplified from raw source: coordinate precision reduced to 3 decimal places (~110m resolution), whitespace stripped. ~50% size reduction from raw.
