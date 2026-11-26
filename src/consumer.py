import json
import httpx
import psycopg
from confluent_kafka import Consumer, KafkaError
from src.config import settings
from src.schemas import TrafficReading, AirQualityReading, AirStation
from src.geo_utils import parse_air_stations, haversine_km


def load_air_stations() -> dict[str, AirStation]:
    """Descarga el catálogo de estaciones de aire una vez al arrancar el consumidor."""
    r = httpx.get(
        settings.AIR_STATIONS_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    r.raise_for_status()
    stations = parse_air_stations(r.text)
    return {s.station_code: s for s in stations}


def insert_station_metric(
    conn: psycopg.Connection,
    station: AirStation,
    air: AirQualityReading,
    nearby_sensors: list[TrafficReading],
) -> None:
    """Inserta o actualiza la métrica cruzada en la hypertable de TimescaleDB."""
    count = len(nearby_sensors)
    avg_intensity = sum(s.intensity for s in nearby_sensors) / count if count else 0.0
    avg_occupancy = sum(s.occupancy for s in nearby_sensors) / count if count else 0.0

    query = """
        INSERT INTO station_metrics (
            timestamp, station_code, station_name, latitude, longitude,
            pollutant, pollutant_value, nearby_sensors_count,
            avg_traffic_intensity, avg_traffic_occupancy
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp, station_code, pollutant)
        DO UPDATE SET
            pollutant_value = EXCLUDED.pollutant_value,
            nearby_sensors_count = EXCLUDED.nearby_sensors_count,
            avg_traffic_intensity = EXCLUDED.avg_traffic_intensity,
            avg_traffic_occupancy = EXCLUDED.avg_traffic_occupancy;
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                air.timestamp,
                station.station_code,
                station.name,
                station.latitude,
                station.longitude,
                air.pollutant,
                air.value,
                count,
                round(avg_intensity, 2),
                round(avg_occupancy, 2),
            ),
        )
    conn.commit()


def run_consumer(max_idle_polls: int | None = None) -> int:
    """Consume eventos de Redpanda, realiza el join espacial y persiste en TimescaleDB."""
    stations = load_air_stations()
    latest_traffic: dict[str, TrafficReading] = {}
    pending_air: list[AirQualityReading] = []

    consumer = Consumer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "madrid-pulse-enricher-v2",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([settings.TOPIC_TRAFFIC, settings.TOPIC_AIR_QUALITY])

    print("Consumidor escuchando en Redpanda... (Ctrl+C para detener)")
    idle_polls = 0
    received_any = False
    saved_rows = 0

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                if received_any:
                    idle_polls += 1
                    if max_idle_polls is not None and idle_polls >= max_idle_polls:
                        break
                continue

            received_any = True
            idle_polls = 0
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    print(f"[ERROR Kafka] {msg.error()}")
                continue

            payload = json.loads(msg.value().decode("utf-8"))

            if msg.topic() == settings.TOPIC_TRAFFIC:
                reading = TrafficReading(**payload)
                latest_traffic[reading.sensor_id] = reading
            elif msg.topic() == settings.TOPIC_AIR_QUALITY:
                pending_air.append(AirQualityReading(**payload))

        print(f"Leídos de Redpanda -> Tráfico: {len(latest_traffic)} sensores | Aire: {len(pending_air)} lecturas")

        # Cruce geoespacial y guardado en TimescaleDB
        if pending_air and latest_traffic:
            traffic_list = list(latest_traffic.values())
            with psycopg.connect(settings.DATABASE_URL) as conn:
                for air in pending_air:
                    station = stations.get(air.station_code)
                    if not station:
                        continue
                    nearby = [
                        s for s in traffic_list
                        if haversine_km(station.latitude, station.longitude, s.latitude, s.longitude)
                        <= settings.SEARCH_RADIUS_KM
                    ]
                    insert_station_metric(conn, station, air, nearby)
                    saved_rows += 1

    finally:
        consumer.close()

    return saved_rows


if __name__ == "__main__":
    rows = run_consumer(max_idle_polls=3)
    print(f"Procesamiento completado: {rows} filas guardadas/actualizadas en TimescaleDB.")