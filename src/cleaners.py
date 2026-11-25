import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import StringIO
import pandas as pd
from src.config import settings
from src.schemas import TrafficReading, AirQualityReading, POLLUTANT_MAP


def parse_and_validate_traffic(xml_bytes: bytes) -> list[TrafficReading]:
    """Parsea el XML de tráfico de Madrid y devuelve solo los sensores válidos."""
    root = ET.fromstring(xml_bytes)
    fecha_hora = root.findtext("fecha_hora")
    valid_readings: list[TrafficReading] = []

    for pm in root.findall("pm"):
        raw = {
            "timestamp": fecha_hora,
            "id": pm.findtext("idelem"),
            "descripcion": pm.findtext("descripcion"),
            "intensidad": pm.findtext("intensidad"),
            "ocupacion": pm.findtext("ocupacion"),
            "carga": pm.findtext("carga"),
            "nivel_servicio": pm.findtext("nivelServicio"),
            "error": pm.findtext("error"),
            "lat": pm.findtext("st_y"),
            "lon": pm.findtext("st_x"),
        }
        reading = TrafficReading.from_raw_xml(raw)
        if reading is not None:
            valid_readings.append(reading)

    return valid_readings


def parse_and_validate_air(csv_text: str) -> list[AirQualityReading]:
    """Extrae la última medición horaria válida ('V') de cada estación y contaminante."""
    df = pd.read_csv(StringIO(csv_text), sep=";")
    df = df[df["MAGNITUD"].isin(settings.POLLUTANTS_OF_INTEREST)]
    valid_readings: list[AirQualityReading] = []

    for _, row in df.iterrows():
        latest_hour = None
        latest_val = None

        # Recorremos las horas hacia atrás (24 -> 1) buscando el dato validado más reciente
        for h in range(24, 0, -1):
            if row.get(f"V{h:02d}") == "V":
                latest_hour = h
                latest_val = float(row[f"H{h:02d}"])
                break

        if latest_hour is None or latest_val is None:
            continue

        # En Madrid la hora 01 es de 00:00 a 01:00; la hora 24 es el cierre del día (00:00 del día siguiente)
        base_date = datetime(int(row["ANO"]), int(row["MES"]), int(row["DIA"]))
        ts = base_date + timedelta(hours=latest_hour)

        station_code = (
            f"{int(row['PROVINCIA']):02d}"
            f"{int(row['MUNICIPIO']):03d}"
            f"{int(row['ESTACION']):03d}"
        )

        try:
            reading = AirQualityReading(
                station_code=station_code,
                timestamp=ts,
                pollutant=POLLUTANT_MAP[int(row["MAGNITUD"])],
                value=latest_val,
            )
            valid_readings.append(reading)
        except ValueError:
            continue

    return valid_readings

if __name__ == "__main__":
    import httpx

    rt = httpx.get(
        settings.TRAFFIC_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    rt.raise_for_status()

    ra = httpx.get(
        settings.AIR_QUALITY_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    ra.raise_for_status()

    tc = parse_and_validate_traffic(rt.content)
    ac = parse_and_validate_air(ra.text)

    print(f"Tráfico limpio: {len(tc)} sensores | Aire limpio: {len(ac)} lecturas")
    print("\nMuestra tráfico:\n", tc[0].model_dump_json(indent=2))
    print("\nMuestra aire:\n", ac[0].model_dump_json(indent=2))