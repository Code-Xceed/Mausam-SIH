# Gazetteer Data — Attribution & License

`in_towns.jsonl.gz` is derived from GeoNames (https://www.geonames.org/) and
redistributed under the **Creative Commons Attribution 4.0 License (CC BY 4.0)**.

Sources:
- `cities500.zip` — https://download.geonames.org/export/dump/ (all Indian cities ≥ 500 population, with population figures)
- `IN.zip` — https://download.geonames.org/export/zip/ (Indian postal localities)

Rebuild after refreshing source data:

```bash
cd backend
.venv/Scripts/python scripts/build_gazetteer.py <path-to-cities500.txt> <path-to-IN.txt>
```

The build script dedupes on (name, state), keeps population ranking for
cities, and caps postal additions to stay under the asset budget.
