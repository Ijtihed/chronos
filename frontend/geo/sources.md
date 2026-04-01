# Map Data Sources

> Permanent record of every map file's provenance. Update this file whenever a map file is added, replaced, or re-sourced. The game references border files by name — this file records where they came from.

## Sourcing priority (for new eras)

1. **aourednik/historical-basemaps** — pre-1886 coverage, free, open, GeoJSON. Primary source.
2. **CShapes 2.0** — 1886–2019 global coverage. Use for modern-era runs.
3. **Manual curation via geojson.io** — last resort for periods with no dataset. Must be flagged with accuracy note.

## Border files

| Era key | Target year | Actual year | Source file | Source dataset | Gap | Rationale |
|---------|------------|-------------|-------------|---------------|-----|-----------|
| roman_late_empire | 410 | 400 | `borders_roman_late_empire.geojson` | aourednik/historical-basemaps `world_400.geojson` | -10 years | Western/Eastern Roman split and Visigothic territories established by 400. 10 years early means events like the sack of Rome (410) happen during gameplay and change the world. |
| viking_age | 870 | 900 | `borders_viking_age.geojson` | aourednik/historical-basemaps `world_900.geojson` | +30 years | Norse expansion well underway by 900. Danelaw visible, Carolingian fragmentation present. 30 years late but representative of the political landscape. |
| crusader_states | 1190 | 1200 | `borders_crusader_states.geojson` | aourednik/historical-basemaps `world_1200.geojson` | +10 years | Third Crusade ended 1192. By 1200, Crusader coastal strip and Ayyubid territories are visible. Very close match. |
| black_death | 1348 | 1300 | `borders_black_death.geojson` | aourednik/historical-basemaps `world_1300.geojson` | -48 years | Largest gap. 1300 is pre-plague — political entities (France, HRE, Italian city-states, Papal States) are correct. Earlier is better: the plague itself arrives during gameplay and reshapes the world. |
| fall_of_constantinople | 1453 | 1400 | `borders_fall_of_constantinople.geojson` | aourednik/historical-basemaps `world_1400.geojson` | -53 years | 1400 shows Constantinople still standing under Byzantine control. Earlier is better: the Ottoman siege and fall happen during gameplay. The 1492 alternative showed a post-fall world. |

## Coastline data

| File | Source | Notes |
|------|--------|-------|
| `coastlines.geojson` | Natural Earth 110m coastlines (`ne_110m_coastline.geojson`) | Static physical layer. 140KB. |

## Notes

- All aourednik files are world-scale FeatureCollection with MultiPolygon geometries, ~1MB each, 233–367 features per file.
- Files are used as-is from the dataset — no additional simplification was needed at this resolution.
- The "earlier is better" principle: using a map snapshot before the era's defining events means those events happen during gameplay and can reshape the world, rather than starting with the aftermath.
