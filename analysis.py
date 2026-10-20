
"""
Core analysis for Urban Heat Island and Tree Cover.

Live mode: Landsat 8/9 Collection 2 Level-2 via Google Earth Engine.
Demo mode: Synthetic data; no Earth Engine credentials required.
"""

import os
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import ee
import numpy as np
import pandas as pd


# ---------------------------------------------------------------
# Configuration and errors
# ---------------------------------------------------------------

PROJECT_ID = os.getenv("EE_PROJECT_ID", "urban-heat-512108").strip()
_EE_READY = False


class LiveDataError(Exception):
    """Raised when a live data service returns no usable data."""


# ---------------------------------------------------------------
# Google Earth Engine authentication
# ---------------------------------------------------------------

def initialize_earth_engine():
    """
    Initialize Earth Engine using credentials created by:
        earthengine authenticate

    The project ID is read from the local EE_PROJECT_ID environment
    variable. No service-account private key is required.
    """
    global _EE_READY

    if _EE_READY:
        return True

    if not PROJECT_ID:
        print(
            "Earth Engine Project ID is missing. "
            "Set the EE_PROJECT_ID environment variable."
        )
        return False

    try:
        ee.Initialize(project=PROJECT_ID)

        # Test a real request rather than assuming initialization succeeded.
        ee.Number(1).getInfo()

        _EE_READY = True
        print("Earth Engine connected and verified successfully!")
        return True

    except Exception as exc:
        print(f"Earth Engine connection failed: {exc}")
        return False


# ---------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------

def _request_json(url, data=None, headers=None):
    request = Request(
        url,
        data=data,
        headers=headers or {},
    )

    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        raise LiveDataError(
            f"Live data request failed: {exc}"
        ) from exc


# ---------------------------------------------------------------
# Current weather: Open-Meteo
# ---------------------------------------------------------------

def current_weather(lat, lon):
    """Fetch current modeled weather conditions from Open-Meteo."""

    params = urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,relative_humidity_2m,"
            "apparent_temperature,precipitation,wind_speed_10m"
        ),
        "timezone": "auto",
    })

    data = _request_json(
        f"https://api.open-meteo.com/v1/forecast?{params}"
    )

    current = data.get("current")

    required_fields = (
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "precipitation",
        "wind_speed_10m",
    )

    if not isinstance(current, dict) or any(
        field not in current for field in required_fields
    ):
        raise LiveDataError(
            "The weather service returned no current conditions."
        )

    return {
        "time": current.get("time", "Unknown"),
        "temperature_c": current["temperature_2m"],
        "apparent_temperature_c": current["apparent_temperature"],
        "relative_humidity_percent": current["relative_humidity_2m"],
        "precipitation_mm": current["precipitation"],
        "wind_speed_kmh": current["wind_speed_10m"],
    }


# ---------------------------------------------------------------
# Distance helper
# ---------------------------------------------------------------

def _distance_km(lat1, lon1, lat2, lon2):
    """Calculate the distance between two coordinates."""

    earth_radius_km = 6371.0

    lat1, lon1, lat2, lon2 = map(
        math.radians,
        (lat1, lon1, lat2, lon2),
    )

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(
        math.sqrt(max(0.0, haversine))
    )


# ---------------------------------------------------------------
# Nearby EV chargers: OpenStreetMap Overpass
# ---------------------------------------------------------------

def nearby_ev_chargers(lat, lon, radius_km):
    """Fetch community-mapped EV charging locations from OpenStreetMap."""

    if not all(
        np.isfinite(value)
        for value in (lat, lon, radius_km)
    ):
        raise ValueError(
            "Coordinates and radius must be finite numbers."
        )

    if (
        not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or radius_km <= 0
    ):
        raise ValueError(
            "Coordinates or search radius are outside valid ranges."
        )

    radius_m = int(radius_km * 1000)

    query = (
        f"[out:json][timeout:20];"
        f"(node[\"amenity\"=\"charging_station\"]"
        f"(around:{radius_m},{lat},{lon});"
        f"way[\"amenity\"=\"charging_station\"]"
        f"(around:{radius_m},{lat},{lon});"
        f"relation[\"amenity\"=\"charging_station\"]"
        f"(around:{radius_m},{lat},{lon});"
        f");out center tags 100;"
    )

    body = urlencode({"data": query}).encode("utf-8")

    payload = _request_json(
        "https://overpass-api.de/api/interpreter",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "UrbanHeatTreeCover/1.0",
        },
    )

    if not isinstance(payload, dict) or "elements" not in payload:
        raise LiveDataError(
            "The EV charger service returned an invalid response."
        )

    if payload.get("remark"):
        raise LiveDataError(
            f"The EV charger service reported: {payload['remark']}"
        )

    rows = []
    seen_locations = set()

    for element in payload.get("elements", []):
        center = element.get("center", {})

        station_lat = element.get("lat", center.get("lat"))
        station_lon = element.get("lon", center.get("lon"))

        if station_lat is None or station_lon is None:
            continue

        location_key = (
            round(station_lat, 5),
            round(station_lon, 5),
        )

        if location_key in seen_locations:
            continue

        seen_locations.add(location_key)

        tags = element.get("tags", {})

        if not isinstance(tags, dict):
            tags = {}

        connectors = ", ".join(
            f"{key[len('socket:'):]}: {value}"
            for key, value in tags.items()
            if key.startswith("socket:")
        )

        rows.append({
            "name": tags.get(
                "name",
                "EV charging location",
            ),
            "distance_km": _distance_km(
                lat,
                lon,
                station_lat,
                station_lon,
            ),
            "lat": station_lat,
            "lon": station_lon,
            "operator": tags.get("operator", "Not listed"),
            "capacity": tags.get("capacity", "Not listed"),
            "connectors": connectors or "Not listed",
        })

    columns = [
        "name",
        "distance_km",
        "lat",
        "lon",
        "operator",
        "capacity",
        "connectors",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    ).sort_values(
        "distance_km",
        ignore_index=True,
    )


# ---------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------

def demo_data(lat, lon, radius_km, n=1500, seed=42):
    """
    Generate synthetic demonstration data.
    These values are NOT satellite observations.
    """

    rng = np.random.default_rng(seed)

    deg = radius_km / 111.0

    lats = lat + rng.uniform(-deg, deg, n)
    lons = lon + rng.uniform(-deg, deg, n)

    dist = np.sqrt(
        ((lats - lat) / deg) ** 2
        + ((lons - lon) / deg) ** 2
    )

    urban = np.clip(1 - dist / 1.2, 0, 1)

    ndvi_past = (
        0.55
        - 0.3 * urban
        + rng.normal(0, 0.07, n)
    )

    parks = rng.random(n) < 0.12
    ndvi_past[parks] += 0.25

    loss = np.clip(
        rng.normal(0.10 * urban, 0.04, n),
        -0.05,
        0.4,
    )

    ndvi_now = ndvi_past - loss

    water = rng.random(n) < 0.03
    ndvi_past[water] = -0.05
    ndvi_now[water] = -0.05

    ndvi_past = np.clip(ndvi_past, -0.1, 0.9)
    ndvi_now = np.clip(ndvi_now, -0.1, 0.9)

    lst = (
        30
        + 8 * urban
        - 6 * ndvi_now
        + rng.normal(0, 1.2, n)
    )

    lst[water] -= 5

    return pd.DataFrame({
        "lon": lons,
        "lat": lats,
        "ndvi_past": ndvi_past,
        "ndvi_now": ndvi_now,
        "lst": lst,
    })


# ---------------------------------------------------------------
# Google Earth Engine: Landsat processing
# ---------------------------------------------------------------

def _aoi(lat, lon, radius_km):
    """Create a rectangular region around the selected map location."""

    if not initialize_earth_engine():
        raise LiveDataError(
            "Earth Engine is not initialized. "
            "Check EE_PROJECT_ID and run earthengine authenticate."
        )

    return (
        ee.Geometry.Point([lon, lat])
        .buffer(radius_km * 1000)
        .bounds()
    )


def _clean_landsat(img):
    """Mask clouds and cloud shadows, then calculate NDVI and LST."""

    qa = img.select("QA_PIXEL")

    # QA_PIXEL bit 1 = dilated cloud, bit 2 = cirrus,
    # bit 3 = cloud, bit 4 = cloud shadow.
    clear = (
        qa.bitwiseAnd(1 << 1).eq(0)
        .And(qa.bitwiseAnd(1 << 2).eq(0))
        .And(qa.bitwiseAnd(1 << 3).eq(0))
        .And(qa.bitwiseAnd(1 << 4).eq(0))
    )

    red = (
        img.select("SR_B4")
        .multiply(0.0000275)
        .add(-0.2)
    )

    nir = (
        img.select("SR_B5")
        .multiply(0.0000275)
        .add(-0.2)
    )

    ndvi = (
        nir.subtract(red)
        .divide(nir.add(red))
        .rename("ndvi")
    )

    # Landsat Collection 2 Level-2 surface temperature conversion.
    lst = (
        img.select("ST_B10")
        .multiply(0.00341802)
        .add(149.0)
        .subtract(273.15)
        .rename("lst")
    )

    return ee.Image.cat(
        [ndvi, lst]
    ).updateMask(clear)


def _landsat_collection(aoi, year, months):
    """Load and process Landsat 8/9 scenes for the selected period."""

    collection = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .merge(
            ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        )
        .filterBounds(aoi)
        .filter(
            ee.Filter.calendarRange(
                year, year, "year"
            )
        )
        .filter(
            ee.Filter.calendarRange(
                months[0], months[1], "month"
            )
        )
        .filter(
            ee.Filter.lt("CLOUD_COVER", 80)
        )
        .map(_clean_landsat)
    )

    return collection


def _checked_collection(aoi, year, months):
    """Check that scenes exist before requesting the image composite."""

    collection = _landsat_collection(
        aoi,
        year,
        months,
    )

    count = collection.size().getInfo()

    if not count:
        raise LiveDataError(
            f"No Landsat 8/9 scenes were found for {year}, "
            f"months {months[0]}–{months[1]}. "
            "Try a wider month range or a different year."
        )

    return collection


def gee_points(
    lat,
    lon,
    radius_km,
    base_year,
    recent_year,
    months=(6, 8),
    n=1500,
):
    """Sample real Landsat pixels and return a DataFrame."""

    if not initialize_earth_engine():
        raise LiveDataError(
            "Earth Engine could not initialize. "
            "Check your local project configuration."
        )

    if base_year > recent_year:
        raise ValueError(
            "The baseline year must not be after the recent year."
        )

    if (
        len(months) != 2
        or not 1 <= months[0] <= months[1] <= 12
    ):
        raise ValueError(
            "Months must be a valid start/end month pair."
        )

    if radius_km <= 0 or n <= 0:
        raise ValueError(
            "Radius and sample count must be greater than zero."
        )

    aoi = _aoi(lat, lon, radius_km)

    past_collection = _checked_collection(
        aoi,
        base_year,
        months,
    )

    recent_collection = _checked_collection(
        aoi,
        recent_year,
        months,
    )

    past = (
        past_collection
        .select("ndvi")
        .median()
        .rename("ndvi_past")
    )

    recent = recent_collection.median()

    stack = ee.Image.cat([
        past,
        recent.select("ndvi").rename("ndvi_now"),
        recent.select("lst").rename("lst"),
    ]).clip(aoi)

    feature_collection = stack.sample(
        region=aoi,
        scale=30,
        numPixels=n,
        seed=42,
        geometries=True,
        tileScale=4,
    )

    result = feature_collection.getInfo()
    features = result.get("features", [])

    rows = []

    for feature in features:
        properties = feature.get("properties", {})
        geometry = feature.get("geometry")

        if not geometry:
            continue

        coordinates = geometry.get("coordinates", [])

        if len(coordinates) < 2:
            continue

        x, y = coordinates

        rows.append({
            "lon": x,
            "lat": y,
            "ndvi_past": properties.get("ndvi_past"),
            "ndvi_now": properties.get("ndvi_now"),
            "lst": properties.get("lst"),
        })

    df = pd.DataFrame(
        rows,
        columns=[
            "lon",
            "lat",
            "ndvi_past",
            "ndvi_now",
            "lst",
        ],
    ).dropna().reset_index(drop=True)

    if df.empty:
        raise LiveDataError(
            "No valid Landsat pixels were returned for this area "
            "and period. Try a larger radius, a wider month range, "
            "or different years."
        )

    return df


def gee_map_layers(
    lat,
    lon,
    radius_km,
    recent_year,
    months=(6, 8),
):
    """Return Earth Engine tile URLs for LST and NDVI map overlays."""

    if not initialize_earth_engine():
        raise LiveDataError(
            "Earth Engine could not initialize."
        )

    aoi = _aoi(lat, lon, radius_km)

    collection = _checked_collection(
        aoi,
        recent_year,
        months,
    )

    recent = collection.median().clip(aoi)

    lst_vis = {
        "min": 20,
        "max": 45,
        "palette": [
            "blue",
            "cyan",
            "yellow",
            "orange",
            "red",
        ],
    }

    ndvi_vis = {
        "min": 0,
        "max": 0.8,
        "palette": [
            "brown",
            "yellow",
            "green",
            "darkgreen",
        ],
    }

    return {
        "Land surface temp (°C)": (
            recent.select("lst")
            .getMapId(lst_vis)["tile_fetcher"].url_format
        ),
        "NDVI (vegetation index)": (
            recent.select("ndvi")
            .getMapId(ndvi_vis)["tile_fetcher"].url_format
        ),
    }


# ---------------------------------------------------------------
# Scoring and summary
# ---------------------------------------------------------------

def score_sites(df, top_n=20):
    """Rank potential planting sites; returns (scored, top_sites)."""

    df = df.copy()

    df["ndvi_change"] = (
        df["ndvi_now"] - df["ndvi_past"]
    )

    df["heat_pct"] = df["lst"].rank(pct=True)
    df["green_gap_pct"] = (
        -df["ndvi_now"]
    ).rank(pct=True)

    df["loss_pct"] = (
        -df["ndvi_change"]
    ).rank(pct=True)

    df["planting_score"] = (
        0.5 * df["heat_pct"]
        + 0.3 * df["green_gap_pct"]
        + 0.2 * df["loss_pct"]
    )

    # Exclude water and dense canopy from planting candidates.
    candidates = df[
        (df["ndvi_now"] > 0)
        & (df["ndvi_now"] < 0.25)
    ]

    top = candidates.sort_values(
        "planting_score",
        ascending=False,
    ).head(top_n)

    return df, top


def summary(df):
    """Summarize temperature and vegetation changes."""

    if df.empty:
        raise LiveDataError(
            "Cannot summarize an empty analysis dataset."
        )

    if "ndvi_change" not in df.columns:
        df = df.copy()
        df["ndvi_change"] = (
            df["ndvi_now"] - df["ndvi_past"]
        )

    return {
        "mean_lst": df["lst"].mean(),
        "hot_threshold": df["lst"].quantile(0.9),
        "loss_share": (
            df["ndvi_change"] < -0.05
        ).mean(),
        "mean_ndvi_change": df["ndvi_change"].mean(),
    }


# ---------------------------------------------------------------
# EV versus petrol commute calculator
# ---------------------------------------------------------------

def ev_commute_impact(
    daily_km,
    commute_days_per_year,
    ev_kwh_per_100_km,
    grid_kg_co2_per_kwh,
    petrol_km_per_litre,
    petrol_kg_co2_per_litre,
    electricity_price_per_kwh,
    petrol_price_per_litre,
):
    """Estimate annual EV versus petrol emissions and energy costs."""

    positive_values = {
        "daily_km": daily_km,
        "ev_kwh_per_100_km": ev_kwh_per_100_km,
        "petrol_km_per_litre": petrol_km_per_litre,
        "petrol_kg_co2_per_litre": petrol_kg_co2_per_litre,
    }

    for name, value in positive_values.items():
        if not np.isfinite(value) or value <= 0:
            raise ValueError(
                f"{name} must be finite and greater than zero."
            )

    non_negative_values = {
        "grid_kg_co2_per_kwh": grid_kg_co2_per_kwh,
        "electricity_price_per_kwh": electricity_price_per_kwh,
        "petrol_price_per_litre": petrol_price_per_litre,
    }

    for name, value in non_negative_values.items():
        if not np.isfinite(value) or value < 0:
            raise ValueError(
                f"{name} must be finite and at least zero."
            )

    if (
        not np.isfinite(commute_days_per_year)
        or int(commute_days_per_year) != commute_days_per_year
        or not 1 <= commute_days_per_year <= 366
    ):
        raise ValueError(
            "commute_days_per_year must be a whole number from 1 to 366."
        )

    annual_distance_km = (
        daily_km * commute_days_per_year
    )

    annual_ev_energy_kwh = (
        annual_distance_km
        * ev_kwh_per_100_km
        / 100
    )

    annual_petrol_litres = (
        annual_distance_km
        / petrol_km_per_litre
    )

    annual_ev_emissions_kg = (
        annual_ev_energy_kwh
        * grid_kg_co2_per_kwh
    )

    annual_petrol_emissions_kg = (
        annual_petrol_litres
        * petrol_kg_co2_per_litre
    )

    co2_avoided = (
        annual_petrol_emissions_kg
        - annual_ev_emissions_kg
    )

    ev_cost = (
        annual_ev_energy_kwh
        * electricity_price_per_kwh
    )

    petrol_cost = (
        annual_petrol_litres
        * petrol_price_per_litre
    )

    return {
        "annual_distance_km": annual_distance_km,
        "annual_ev_energy_kwh": annual_ev_energy_kwh,
        "annual_petrol_litres": annual_petrol_litres,
        "annual_ev_emissions_kg": annual_ev_emissions_kg,
        "annual_petrol_emissions_kg": annual_petrol_emissions_kg,
        "annual_co2_avoided_kg": co2_avoided,
        "co2_reduction_percent": (
            co2_avoided / annual_petrol_emissions_kg * 100
        ),
        "annual_ev_cost": ev_cost,
        "annual_petrol_cost": petrol_cost,
        "annual_cost_savings": petrol_cost - ev_cost,
        "break_even_grid_kg_co2_per_kwh": (
            annual_petrol_emissions_kg
            / annual_ev_energy_kwh
        ),
    }
