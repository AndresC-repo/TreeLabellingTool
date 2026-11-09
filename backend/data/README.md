Reference data for working out where a tile is (services/location.py).

- `us_states.geojson` — US state boundaries (incl. DC, PR), from the `us-atlas` 3.0.1
  package (`states-10m.json`, US Census cartographic boundary files), converted to GeoJSON
  with postal codes. Accuracy is about 1:10M — fine for picking the state of a tile,
  approximate within a few hundred metres of a state line.
- `us_cities.csv` — the 1,000 largest US cities with coordinates and population
  (plotly/datasets `us-cities-top-1k.csv`, 2014 populations). Used to name the nearest
  city of a tile.
