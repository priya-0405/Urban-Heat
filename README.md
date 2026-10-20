# Urban Heat, Tree Cover & EV Sustainability

An interactive Streamlit capstone dashboard connecting urban heat mitigation
with green mobility. It can use live external sources where available and keeps
a synthetic-data mode for demos or offline use.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Features

- Compare land-surface temperature and vegetation indicators, then rank
  candidate planting sites.
- Choose synthetic demo data or Landsat analysis through Google Earth Engine.
- View current modeled weather and community-mapped EV charging locations near
  the selected coordinates.
- Estimate EV-versus-petrol commute emissions and energy costs using editable
  assumptions; inspect the grid-emissions break-even point and download a CSV.
- Refresh cached live sources with **Refresh live data now**.

## Live data setup and freshness

- **Satellite heat and vegetation:** Live mode uses Landsat 8/9 Collection 2
  Level-2 imagery through Google Earth Engine. Configure a `[gee]` section in
  `.streamlit/secrets.toml` with an Earth Engine service account's JSON fields,
  including `client_email`, `project_id`, and `private_key`. Register the
  service account with Earth Engine and enable the Earth Engine API for its
  project. Replace any example placeholders with real service-account values.
  Keep the secrets file private; do not commit credentials.
- **Weather:** Open-Meteo supplies current modeled conditions for the selected
  coordinates. Results are cached for 15 minutes.
- **EV charging locations:** OpenStreetMap's Overpass service supplies mapped
  charger locations, connector tags, and distances. Results are cached for
  15 minutes. These records do **not** report whether a charger is operational,
  occupied, or available in real time.
- **Refresh behavior:** The refresh button clears the app's cached analysis and
  live-source results. Satellite imagery is still limited by Landsat's
  acquisition and publication schedule; it is not minute-by-minute data.

## Interpretation limits

Demo heat and vegetation data is synthetic. Live satellite samples and planting
scores are screening aids, not validated planting instructions; site ownership,
soil, water, infrastructure, and on-site conditions must be checked.

The EV planner is a scenario estimate based on user-entered energy use, grid
emissions, vehicle efficiency, and prices. It excludes manufacturing,
maintenance, upstream fuel emissions, charging losses, and other lifecycle
effects. Defaults are examples, not live prices or verified local emissions
factors.
