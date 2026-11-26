import pandas as pd
import psycopg
from src.config import settings


def fetch_latest_metrics_with_anomalies(
    z_threshold: float = 2.0,
) -> pd.DataFrame:
    """
    Consulta TimescaleDB calculando la media móvil y desviación estándar de 24h
    por estación y contaminante para detectar picos anómalos (Z-score).
    """
    query = """
        WITH windowed_stats AS (
            SELECT
                timestamp,
                station_code,
                station_name,
                latitude,
                longitude,
                pollutant,
                pollutant_value,
                nearby_sensors_count,
                avg_traffic_intensity,
                avg_traffic_occupancy,
                AVG(pollutant_value) OVER (
                    PARTITION BY station_code, pollutant
                    ORDER BY timestamp
                    RANGE BETWEEN INTERVAL '24 hours' PRECEDING AND CURRENT ROW
                ) AS rolling_mean_24h,
                STDDEV(pollutant_value) OVER (
                    PARTITION BY station_code, pollutant
                    ORDER BY timestamp
                    RANGE BETWEEN INTERVAL '24 hours' PRECEDING AND CURRENT ROW
                ) AS rolling_std_24h,
                ROW_NUMBER() OVER (
                    PARTITION BY station_code, pollutant
                    ORDER BY timestamp DESC
                ) AS rn
            FROM station_metrics
        )
        SELECT
            timestamp,
            station_code,
            station_name,
            latitude,
            longitude,
            pollutant,
            pollutant_value,
            nearby_sensors_count,
            avg_traffic_intensity,
            avg_traffic_occupancy,
            ROUND(rolling_mean_24h::numeric, 2) AS rolling_mean_24h,
            CASE
                WHEN rolling_std_24h IS NULL OR rolling_std_24h = 0 THEN 0.0
                ELSE ROUND(((pollutant_value - rolling_mean_24h) / rolling_std_24h)::numeric, 2)
            END AS z_score
        FROM windowed_stats
        WHERE rn = 1
        ORDER BY pollutant, pollutant_value DESC;
    """
    with psycopg.connect(settings.DATABASE_URL) as conn:
        df = pd.read_sql_query(query, conn)

    if not df.empty:
        df["z_score"] = df["z_score"].astype(float)
        df["is_anomaly"] = df["z_score"].abs() >= z_threshold

    return df


if __name__ == "__main__":
    df_latest = fetch_latest_metrics_with_anomalies()
    print(f"Estaciones/contaminantes analizados: {len(df_latest)}")
    print(
        df_latest[
            [
                "station_name",
                "pollutant",
                "pollutant_value",
                "avg_traffic_intensity",
                "z_score",
                "is_anomaly",
            ]
        ].head(10).to_string(index=False)
    )