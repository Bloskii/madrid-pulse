import time
import httpx
from confluent_kafka import Producer
from src.config import settings
from src.cleaners import parse_and_validate_traffic, parse_and_validate_air


def delivery_report(err, msg) -> None:
    """Callback ejecutado por Kafka/Redpanda cuando confirma o falla la entrega."""
    if err is not None:
        print(f"[ERROR] Fallo entregando mensaje en {msg.topic()}: {err}")


def create_producer() -> Producer:
    return Producer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "client.id": "madrid-pulse-producer",
        "acks": "all",
    })


def fetch_with_retries(url: str, max_retries: int = 3) -> httpx.Response:
    """Descarga una URL con reintentos y espera exponencial ante timeouts del servidor."""
    headers = {"User-Agent": settings.USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=settings.HTTP_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response
        except (httpx.ReadTimeout, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            if attempt == max_retries:
                raise
            wait_sec = 2 ** attempt
            print(f"[WARN] Intento {attempt}/{max_retries} fallido para {url} ({exc}). Reintentando en {wait_sec}s...")
            time.sleep(wait_sec)
    raise RuntimeError("Unreachable")


def publish_snapshot(producer: Producer) -> tuple[int, int]:
    """Descarga, valida y publica una foto instantánea de tráfico y calidad del aire."""
    t_count = 0
    a_count = 0

    # 1. Tráfico -> Topic traffic.raw
    try:
        r_traffic = fetch_with_retries(settings.TRAFFIC_URL)
        traffic_readings = parse_and_validate_traffic(r_traffic.content)
        for reading in traffic_readings:
            producer.produce(
                topic=settings.TOPIC_TRAFFIC,
                key=reading.sensor_id.encode("utf-8"),
                value=reading.model_dump_json().encode("utf-8"),
                callback=delivery_report,
            )
        t_count = len(traffic_readings)
    except Exception as exc:
        print(f"[ERROR] No se pudo ingerir tráfico: {exc}")

    # 2. Calidad del aire -> Topic air_quality.raw
    try:
        r_air = fetch_with_retries(settings.AIR_QUALITY_URL)
        air_readings = parse_and_validate_air(r_air.text)
        for reading in air_readings:
            key = f"{reading.station_code}_{reading.pollutant}".encode("utf-8")
            producer.produce(
                topic=settings.TOPIC_AIR_QUALITY,
                key=key,
                value=reading.model_dump_json().encode("utf-8"),
                callback=delivery_report,
            )
        a_count = len(air_readings)
    except Exception as exc:
        print(f"[ERROR] No se pudo ingerir calidad del aire: {exc}")

    producer.flush()
    return t_count, a_count


def run_loop(interval_seconds: int = 300) -> None:
    """Ejecuta la ingesta en bucle continuo (por defecto cada 5 minutos)."""
    producer = create_producer()
    print(f"Productor conectado a {settings.KAFKA_BOOTSTRAP_SERVERS}. Ctrl+C para detener.")

    while True:
        t_count, a_count = publish_snapshot(producer)
        print(f"[OK] Publicados {t_count} eventos de tráfico y {a_count} de calidad del aire.")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    prod = create_producer()
    t_sent, a_sent = publish_snapshot(prod)
    print(f"Prueba completada: {t_sent} mensajes en '{settings.TOPIC_TRAFFIC}' y {a_sent} en '{settings.TOPIC_AIR_QUALITY}'.")