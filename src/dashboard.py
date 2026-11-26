import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st
from src.analytics import fetch_latest_metrics_with_anomalies
from src.config import settings

st.set_page_config(
    page_title="Madrid Pulse | Tráfico & Calidad del Aire",
    page_icon="📡",
    layout="wide",
)

st.title("📡 Madrid Pulse — Monitorización Ambiental y de Tráfico en Tiempo Real")
st.caption(
    "Pipeline end-to-end: Madrid Open Data → Redpanda (Kafka) → Haversine Spatial Join (1 km) → TimescaleDB"
)


@st.cache_data(ttl=60)
def load_latest_data(z_thresh: float) -> pd.DataFrame:
    return fetch_latest_metrics_with_anomalies(z_threshold=z_thresh)


@st.cache_data(ttl=60)
def load_station_history(station_code: str, pollutant: str) -> pd.DataFrame:
    query = """
        SELECT timestamp, pollutant_value, avg_traffic_intensity, avg_traffic_occupancy
        FROM station_metrics
        WHERE station_code = %s AND pollutant = %s
        ORDER BY timestamp ASC
        LIMIT 500;
    """
    with psycopg.connect(settings.DATABASE_URL) as conn:
        return pd.read_sql_query(query, conn, params=(station_code, pollutant))


# --- Barra lateral de controles ---
st.sidebar.header("⚙️ Filtros y Alertas")
z_threshold = st.sidebar.slider(
    "Umbral de anomalía (|Z-score| 24h)",
    min_value=1.0,
    max_value=4.0,
    value=2.0,
    step=0.25,
)

if st.sidebar.button("🔄 Actualizar datos ahora"):
    st.cache_data.clear()

df = load_latest_data(z_threshold)

if df.empty:
    st.warning(
        "No hay datos en TimescaleDB todavía. Ejecuta `python -m src.producer` y `python -m src.consumer` primero."
    )
    st.stop()

pollutants = sorted(df["pollutant"].unique().tolist())
default_idx = pollutants.index("NO2") if "NO2" in pollutants else 0
selected_pollutant = st.sidebar.selectbox("Contaminante", pollutants, index=default_idx)

df_poll = df[df["pollutant"] == selected_pollutant].copy()

# --- KPIs superiores ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Estaciones activas", len(df_poll))
col2.metric(
    f"Media {selected_pollutant} (µg/m³)",
    f"{df_poll['pollutant_value'].mean():.1f}",
)
col3.metric(
    "Intensidad media tráfico (<1 km)",
    f"{df_poll['avg_traffic_intensity'].mean():.0f} veh/h",
)
anomalies_count = int(df_poll["is_anomaly"].sum())
col4.metric(
    "Alertas anómalas activas",
    anomalies_count,
    delta="Revisar picos" if anomalies_count > 0 else "Normal",
    delta_color="inverse" if anomalies_count > 0 else "normal",
)

st.divider()

# --- Mapa geoespacial + Correlación Tráfico vs Contaminación ---
left_col, right_col = st.columns([1.3, 1])

with left_col:
    st.subheader(f"🗺️ Mapa de {selected_pollutant} y Sensores Cercanos")
    df_poll["status"] = df_poll["is_anomaly"].map(
        {True: "🚨 Anomalía", False: "✅ Normal"}
    )
    fig_map = px.scatter_map(
        df_poll,
        lat="latitude",
        lon="longitude",
        color="pollutant_value",
        size="avg_traffic_intensity",
        hover_name="station_name",
        hover_data={
            "pollutant_value": ":.1f",
            "avg_traffic_intensity": ":.0f",
            "nearby_sensors_count": True,
            "z_score": ":.2f",
            "status": True,
            "latitude": False,
            "longitude": False,
        },
        color_continuous_scale="YlOrRd",
        size_max=22,
        zoom=10.5,
        center={"lat": 40.4168, "lon": -3.7038},
        map_style="carto-positron",
        height=470,
        labels={
            "pollutant_value": f"{selected_pollutant} (µg/m³)",
            "avg_traffic_intensity": "Tráfico medio (veh/h)",
            "nearby_sensors_count": "Sensores <1km",
            "z_score": "Z-score 24h",
        },
    )
    fig_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig_map, use_container_width=True)

with right_col:
    st.subheader(f"📈 Tráfico (<1 km) vs {selected_pollutant}")
    fig_scatter = px.scatter(
        df_poll,
        x="avg_traffic_intensity",
        y="pollutant_value",
        color="status",
        hover_name="station_name",
        size="nearby_sensors_count",
        color_discrete_map={"🚨 Anomalía": "#E63946", "✅ Normal": "#2A9D8F"},
        height=470,
        labels={
            "avg_traffic_intensity": "Intensidad media tráfico (veh/h)",
            "pollutant_value": f"{selected_pollutant} (µg/m³)",
            "status": "Estado",
        },
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# --- Serie temporal por estación ---
st.subheader("⏱️ Evolución Temporal por Estación")
station_names = df_poll["station_name"].tolist()
selected_station_name = st.selectbox("Selecciona una estación", station_names)
station_row = df_poll[df_poll["station_name"] == selected_station_name].iloc[0]

df_hist = load_station_history(station_row["station_code"], selected_pollutant)

if len(df_hist) > 1:
    fig_ts = px.line(
        df_hist,
        x="timestamp",
        y=["pollutant_value", "avg_traffic_intensity"],
        markers=True,
        labels={"value": "Valor medido", "timestamp": "Hora", "variable": "Métrica"},
    )
    st.plotly_chart(fig_ts, use_container_width=True)
else:
    st.info(
        "Solo hay 1 captura temporal almacenada para esta estación. Ejecuta el pipeline varias veces (o en bucle) para visualizar la curva de evolución horaria."
    )

# --- Tabla detallada ---
with st.expander("📋 Ver tabla completa de métricas"):
    st.dataframe(
        df_poll[
            [
                "station_name",
                "pollutant_value",
                "rolling_mean_24h",
                "z_score",
                "is_anomaly",
                "nearby_sensors_count",
                "avg_traffic_intensity",
                "avg_traffic_occupancy",
                "timestamp",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )