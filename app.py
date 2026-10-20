


import html
import requests
import streamlit as st
import folium
import pandas as pd
import analysis as an

from folium.plugins import HeatMap
from streamlit_folium import st_folium


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="Urban Heat, Tree Cover & EV Sustainability",
    page_icon="🌳",
    layout="wide",
)

st.title("🌳 Urban Heat, Tree Cover & EV Sustainability")
st.caption(
    "Analyze urban heat, identify potential tree-planting sites, "
    "and explore EV charging locations."
)


# --------------------------------------------------
# CITY GEOCODING
# --------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def get_city_coordinates(city_name):
    """Find city coordinates using OpenStreetMap Nominatim."""

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": city_name,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "in",
    }

    headers = {
        "User-Agent": "UrbanHeatTreeCoverStudentProject/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()

    results = response.json()

    if not results:
        return None

    return {
        "latitude": float(results[0]["lat"]),
        "longitude": float(results[0]["lon"]),
        "display_name": results[0]["display_name"],
    }


# --------------------------------------------------
# SESSION STATE DEFAULTS
# --------------------------------------------------
if "latitude" not in st.session_state:
    st.session_state["latitude"] = 13.0827

if "longitude" not in st.session_state:
    st.session_state["longitude"] = 80.2707

if "city_name" not in st.session_state:
    st.session_state["city_name"] = "Chennai"

if "city_display_name" not in st.session_state:
    st.session_state["city_display_name"] = "Chennai, Tamil Nadu, India"

if "city_search_message" not in st.session_state:
    st.session_state["city_search_message"] = ""


# --------------------------------------------------
# SIDEBAR: CITY SEARCH
# --------------------------------------------------
st.sidebar.header("📍 Study Area")

city = st.sidebar.text_input(
    "Enter city name",
    key="city_name",
    placeholder="Example: Madurai",
)

if st.sidebar.button(
    "🔍 Find City",
    use_container_width=True,
):
    if not city.strip():
        st.session_state["city_search_message"] = (
            "Please enter a city name."
        )
    else:
        try:
            with st.spinner("Finding city coordinates..."):
                result = get_city_coordinates(city.strip())

            if result:
                # Update the coordinates before their widgets are created.
                st.session_state["latitude"] = result["latitude"]
                st.session_state["longitude"] = result["longitude"]
                st.session_state["city_display_name"] = (
                    result["display_name"]
                )
                st.session_state["city_search_message"] = (
                    "success"
                )
            else:
                st.session_state["city_search_message"] = (
                    "City not found. Try a name such as "
                    "'Madurai, Tamil Nadu'."
                )

        except requests.RequestException:
            st.session_state["city_search_message"] = (
                "Could not look up the city. Check your internet "
                "connection and try again."
            )

if st.session_state["city_search_message"] == "success":
    st.sidebar.success("City location updated!")
    st.sidebar.caption(
        st.session_state["city_display_name"]
    )
elif st.session_state["city_search_message"]:
    st.sidebar.error(
        st.session_state["city_search_message"]
    )

lat = st.sidebar.number_input(
    "Latitude",
    key="latitude",
    format="%.6f",
)

lon = st.sidebar.number_input(
    "Longitude",
    key="longitude",
    format="%.6f",
)

st.sidebar.caption(
    f"Coordinates: {lat:.6f}, {lon:.6f}"
)

radius_km = st.sidebar.slider(
    "Study radius (km)",
    min_value=2,
    max_value=15,
    value=5,
)


# --------------------------------------------------
# SIDEBAR: ANALYSIS SETTINGS
# --------------------------------------------------
st.sidebar.header("⚙️ Analysis Settings")

mode = st.sidebar.radio(
    "Data source",
    ["Demo", "Live"],
    help=(
        "Demo uses sample data. Live requires working "
        "Google Earth Engine access."
    ),
)

baseline_year = st.sidebar.selectbox(
    "Baseline year",
    options=list(range(2014, 2019)),
    index=1,
)

recent_year = st.sidebar.selectbox(
    "Recent year",
    options=list(range(2019, 2026)),
    index=6,
)

top_n = st.sidebar.slider(
    "Number of planting sites",
    min_value=5,
    max_value=50,
    value=15,
)

show_weather = st.sidebar.checkbox(
    "Show current weather",
    value=False,
)

show_ev = st.sidebar.checkbox(
    "Show nearby EV chargers",
    value=True,
)


# --------------------------------------------------
# EARTH ENGINE INITIALIZATION
# --------------------------------------------------
def ensure_earth_engine():
    """Initialize Earth Engine through analysis.py."""

    ready = an.initialize_earth_engine()

    if not ready:
        raise RuntimeError(
            "Earth Engine could not be initialized. "
            "Check your Earth Engine authentication and project settings."
        )


# --------------------------------------------------
# LOAD ANALYSIS DATA
# --------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def load_analysis(
    selected_mode,
    latitude,
    longitude,
    radius,
    base_year,
    current_year,
):
    if selected_mode == "Demo":
        return an.demo_data(
            latitude,
            longitude,
            radius,
            base_year,
            current_year,
        )

    ensure_earth_engine()

    return an.gee_points(
        latitude,
        longitude,
        radius,
        base_year,
        current_year,
    )


# --------------------------------------------------
# RUN ANALYSIS
# --------------------------------------------------
try:
    with st.spinner(
        f"Analyzing the study area near {city}..."
    ):
        df = load_analysis(
            mode,
            lat,
            lon,
            radius_km,
            baseline_year,
            recent_year,
        )

        if df is None or df.empty:
            st.warning(
                "No analysis data was returned. "
                "Try another city or increase the study radius."
            )
            st.stop()

        scored, top = an.score_sites(df, top_n)
        stats = an.summary(scored)

except Exception as exc:
    st.error(f"Unable to load analysis data: {exc}")

    if mode == "Live":
        st.info(
            "Try Demo mode to test the application without "
            "Earth Engine credentials."
        )

    st.stop()


# --------------------------------------------------
# SUMMARY METRICS
# --------------------------------------------------
st.subheader(
    f"📍 Study Area: {city}"
)

st.caption(
    f"Selected location: {st.session_state['city_display_name']}"
)

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Average Surface Temperature",
    f"{stats.get('mean_lst', 0):.1f} °C",
)

metric2.metric(
    "Hot-Area Threshold",
    f"{stats.get('hot_threshold', 0):.1f} °C",
)

metric3.metric(
    "Vegetation Loss",
    f"{stats.get('vegetation_loss_pct', 0):.1f}%",
)

metric4.metric(
    "Average NDVI Change",
    f"{stats.get('mean_ndvi_change', 0):.3f}",
)

st.divider()


# --------------------------------------------------
# INTERACTIVE MAP
# --------------------------------------------------
st.subheader("🗺️ Urban Heat & Tree-Planting Map")

m = folium.Map(
    location=[lat, lon],
    zoom_start=12,
    tiles="OpenStreetMap",
)

# Study-area marker
folium.Marker(
    location=[lat, lon],
    tooltip=f"Study area: {html.escape(city)}",
    popup=folium.Popup(
        f"""
        <b>{html.escape(city)}</b><br>
        Latitude: {lat:.6f}<br>
        Longitude: {lon:.6f}<br>
        Study radius: {radius_km} km
        """,
        max_width=280,
    ),
    icon=folium.Icon(
        color="red",
        icon="info-sign",
    ),
).add_to(m)


# Draw a circle around the selected study location
folium.Circle(
    location=[lat, lon],
    radius=radius_km * 1000,
    color="#1565c0",
    weight=2,
    fill=False,
    tooltip=f"Study radius: {radius_km} km",
).add_to(m)


# --------------------------------------------------
# HEATMAP LAYER
# --------------------------------------------------
if {"lat", "lon", "heat_pct"}.issubset(scored.columns):
    heat_data = (
        scored[["lat", "lon", "heat_pct"]]
        .dropna()
        .values
        .tolist()
    )

    if heat_data:
        heat_group = folium.FeatureGroup(
            name="Relative Heat Intensity",
            show=True,
        )

        HeatMap(
            heat_data,
            radius=20,
            blur=15,
            min_opacity=0.35,
        ).add_to(heat_group)

        heat_group.add_to(m)


# --------------------------------------------------
# LIVE SATELLITE OVERLAYS
# --------------------------------------------------
if mode == "Live":
    try:
        layers = an.gee_map_layers(
            lat,
            lon,
            radius_km,
            baseline_year,
            recent_year,
        )

        if isinstance(layers, dict):
            for layer_name, tile_url in layers.items():
                if tile_url:
                    folium.TileLayer(
                        tiles=tile_url,
                        attr="Google Earth Engine",
                        name=str(layer_name),
                        overlay=True,
                        control=True,
                        show=False,
                    ).add_to(m)

    except Exception as exc:
        st.warning(
            f"Satellite map overlays could not be loaded: {exc}"
        )


# --------------------------------------------------
# GREEN TREE-PLANTING MARKERS
# --------------------------------------------------
if not top.empty:
    planting_group = folium.FeatureGroup(
        name="Recommended Tree-Planting Locations",
        show=True,
    )

    for i, r in enumerate(top.itertuples(), start=1):
        popup_html = f"""
        <div style="width:230px; font-family:Arial,sans-serif;">
            <h4 style="color:#1b5e20; margin-bottom:8px;">
                🌳 Planting Site {i}
            </h4>
            <b>Priority Score:</b> {r.planting_score:.2f}<br>
            <b>Surface Temperature:</b> {r.lst:.1f} °C<br>
            <b>Current NDVI:</b> {r.ndvi_now:.2f}<br>
            <b>Vegetation Change:</b> {r.ndvi_change:.3f}
            <hr>
            <small>
                Candidate ranked by the project's planting-priority model.
                Verify land availability and local conditions before planting.
            </small>
        </div>
        """

        folium.CircleMarker(
            location=[r.lat, r.lon],
            radius=7,
            color="#1b5e20",
            weight=2,
            fill=True,
            fill_color="#43a047",
            fill_opacity=0.9,
            tooltip=f"🌳 Recommended Planting Site {i}",
            popup=folium.Popup(
                popup_html,
                max_width=300,
            ),
        ).add_to(planting_group)

    planting_group.add_to(m)


# --------------------------------------------------
# BLUE EV CHARGER MARKERS
# --------------------------------------------------
if show_ev:
    try:
        chargers = an.nearby_ev_chargers(
            lat,
            lon,
            radius_km,
        )

        if chargers is not None and not chargers.empty:
            ev_group = folium.FeatureGroup(
                name="EV Charging Stations",
                show=True,
            )

            for charger in chargers.itertuples():
                charger_lat = getattr(charger, "lat", None)
                charger_lon = getattr(charger, "lon", None)

                if charger_lat is None or charger_lon is None:
                    continue

                if pd.isna(charger_lat) or pd.isna(charger_lon):
                    continue

                charger_name = str(
                    getattr(charger, "name", "EV Charger")
                )

                folium.Marker(
                    location=[charger_lat, charger_lon],
                    tooltip=f"⚡ {charger_name}",
                    popup=folium.Popup(
                        f"""
                        <b>{html.escape(charger_name)}</b><br>
                        EV charging location
                        """,
                        max_width=250,
                    ),
                    icon=folium.Icon(
                        color="blue",
                        icon="flash",
                        prefix="glyphicon",
                    ),
                ).add_to(ev_group)

            ev_group.add_to(m)

    except Exception as exc:
        st.warning(
            f"EV charger locations could not be loaded: {exc}"
        )


# Layer controls
folium.LayerControl(collapsed=False).add_to(m)

# Display map
st_folium(
    m,
    height=550,
    use_container_width=True,
    returned_objects=[],
)

st.caption(
    "Map legend: 🔴 Study location | "
    "Heatmap = relative heat intensity | "
    "🟢 Green circles = recommended planting sites | "
    "🔵 Blue markers = EV charging stations."
)

st.divider()


# --------------------------------------------------
# PLANTING SITES TABLE
# --------------------------------------------------
st.subheader("🌱 Recommended Tree-Planting Sites")

if not top.empty:
    display_columns = [
        column
        for column in [
            "lat",
            "lon",
            "planting_score",
            "lst",
            "ndvi_now",
            "ndvi_change",
        ]
        if column in top.columns
    ]

    st.dataframe(
        top[display_columns].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

    csv_data = top[display_columns].to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "⬇️ Download Planting Sites (CSV)",
        data=csv_data,
        file_name="recommended_planting_sites.csv",
        mime="text/csv",
    )
else:
    st.info(
        "No planting sites are available for this study area."
    )

st.divider()


# --------------------------------------------------
# CHARTS
# --------------------------------------------------
st.subheader("📊 Data Analysis")

chart1, chart2 = st.columns(2)

with chart1:
    st.markdown("**Surface Temperature Distribution**")

    if "lst" in scored.columns:
        temperature_data = scored["lst"].dropna()

        if not temperature_data.empty:
            st.bar_chart(
                temperature_data.reset_index(drop=True)
            )
        else:
            st.info("No temperature values available.")
    else:
        st.info("Temperature data is unavailable.")

with chart2:
    st.markdown("**Vegetation Index (NDVI)**")

    if {"ndvi_now", "ndvi_change"}.issubset(scored.columns):
        vegetation_data = scored[
            ["ndvi_now", "ndvi_change"]
        ].dropna()

        if not vegetation_data.empty:
            st.line_chart(
                vegetation_data.reset_index(drop=True)
            )
        else:
            st.info("No vegetation values available.")
    else:
        st.info("Vegetation data is unavailable.")

st.divider()


# --------------------------------------------------
# CURRENT WEATHER
# --------------------------------------------------
if show_weather:
    st.subheader("🌦️ Current Weather")

    try:
        weather = an.current_weather(lat, lon)

        if isinstance(weather, dict):
            if weather:
                weather_cols = st.columns(
                    min(len(weather), 4)
                )

                for i, (key, value) in enumerate(weather.items()):
                    with weather_cols[i % len(weather_cols)]:
                        st.metric(
                            str(key).replace("_", " ").title(),
                            str(value),
                        )
            else:
                st.info("No weather data is available.")
        else:
            st.write(weather)

    except Exception as exc:
        st.warning(
            f"Weather data could not be loaded: {exc}"
        )

st.divider()


# --------------------------------------------------
# EV SUSTAINABILITY CALCULATOR
# --------------------------------------------------
st.subheader("⚡ EV Sustainability Calculator")

st.write(
    "Estimate annual petrol-vehicle CO₂ emissions based on "
    "your daily travel distance."
)

ev_col1, ev_col2 = st.columns(2)

with ev_col1:
    daily_km = st.number_input(
        "Daily travel distance (km)",
        min_value=1.0,
        max_value=500.0,
        value=30.0,
        step=1.0,
    )

with ev_col2:
    petrol_emission_factor = st.number_input(
        "Petrol emissions (kg CO₂/km)",
        min_value=0.01,
        max_value=1.0,
        value=0.192,
        step=0.001,
        format="%.3f",
    )

if st.button("Calculate EV Impact"):
    annual_distance = daily_km * 365

    annual_petrol_emissions = (
        annual_distance * petrol_emission_factor
    )

    st.metric(
        "Estimated annual petrol emissions",
        f"{annual_petrol_emissions:,.1f} kg CO₂",
    )

    st.caption(
        "This estimates petrol-vehicle emissions only. "
        "It does not subtract emissions from electricity used "
        "to charge an EV, so it is not a complete EV-versus-petrol comparison."
    )


# --------------------------------------------------
# METHODOLOGY AND LIMITATIONS
# --------------------------------------------------
with st.expander("ℹ️ Methodology and Limitations"):
    st.markdown(
        """
        **Features**
        
        - Looks up city coordinates using OpenStreetMap.
        - Displays a map centered on the selected city.
        - Shows relative heat intensity and planting candidates.
        - Displays EV charging locations when data is available.
        - Provides charts and a downloadable planting-site table.

        **Limitations**

        - Demo mode uses sample/synthetic data, not actual satellite
          measurements for the selected city.
        - Live mode requires working Google Earth Engine access and
          suitable satellite imagery.
        - The heatmap visualizes supplied heat values; it is not a
          direct measurement of air temperature.
        - Planting sites are model-based candidates. Verify land access,
          soil, water availability, local species, and permissions.
        - EV charger data depends on available map data.
        """
    )

st.caption(
    "Urban Heat, Tree Cover & EV Sustainability | "
    "Educational research prototype"
)
