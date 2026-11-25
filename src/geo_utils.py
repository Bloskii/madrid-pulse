import math
from io import StringIO
import pandas as pd
from src.config import settings
from src.schemas import AirStation, TrafficReading


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia en kilómetros entre dos puntos GPS sobre la superficie terrestre."""
    r = 6371.0  # Radio medio de la Tierra en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_air_stations(csv_text: str) -> list[AirStation]:
    """Parsea el catálogo oficial de estaciones de calidad del aire de Madrid."""
    df = pd.read_csv(StringIO(csv_text), sep=";")
    stations: list[AirStation] = []

    for _, row in df.iterrows():
        try:
            # El código en el catálogo viene como 28079004 (8 dígitos) o en columna CODIGO_CORTO
            if "CODIGO" in df.columns:
                raw_code = str(row["CODIGO"]).strip()
                # Nos quedamos con los 8 primeros dígitos (ej. 28079004)
                station_code = raw_code[:8]
            else:
                station_code = f"28079{int(row['CODIGO_CORTO']):03d}"

            stations.append(
                AirStation(
                    station_code=station_code,
                    name=str(row["ESTACION"]).strip(),
                    latitude=float(str(row["LATITUD"]).replace(",", ".")),
                    longitude=float(str(row["LONGITUD"]).replace(",", ".")),
                )
            )
        except (ValueError, KeyError, TypeError):
            continue

    return stations


def map_stations_to_traffic(
    stations: list[AirStation],
    traffic_sensors: list[TrafficReading],
    radius_km: float = settings.SEARCH_RADIUS_KM,
) -> dict[str, list[TrafficReading]]:
    """Asocia cada estación de aire con los sensores de tráfico dentro de `radius_km`."""
    mapping: dict[str, list[TrafficReading]] = {}

    for station in stations:
        nearby = [
            sensor
            for sensor in traffic_sensors
            if haversine_km(
                station.latitude, station.longitude, sensor.latitude, sensor.longitude
            )
            <= radius_km
        ]
        mapping[station.station_code] = nearby

    return mapping

if __name__ == "__main__":
    import httpx
    from src.cleaners import parse_and_validate_traffic

    r_stations = httpx.get(
        settings.AIR_STATIONS_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    r_stations.raise_for_status()

    r_traffic = httpx.get(
        settings.TRAFFIC_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    r_traffic.raise_for_status()

    stations = parse_air_stations(r_stations.text)
    traffic = parse_and_validate_traffic(r_traffic.content)
    station_traffic_map = map_stations_to_traffic(stations, traffic)

    print(f"Estaciones cargadas: {len(stations)}")
    for st in stations[:5]:
        nearby_sensors = station_traffic_map[st.station_code]
        avg_intensity = (
            sum(s.intensity for s in nearby_sensors) / len(nearby_sensors)
            if nearby_sensors
            else 0
        )
        print(
            f"- {st.name} ({st.station_code}): "
            f"{len(nearby_sensors)} sensores a <{settings.SEARCH_RADIUS_KM} km | "
            f"Intensidad media: {avg_intensity:.0f} veh/h"
        )