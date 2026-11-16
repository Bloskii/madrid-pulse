import xml.etree.ElementTree as ET
from io import StringIO
import httpx
import pandas as pd
from src.config import settings


def fetch_traffic() -> pd.DataFrame:
    print("Descargando tráfico en tiempo real...")
    response = httpx.get(
        settings.TRAFFIC_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    fecha_hora = root.findtext("fecha_hora")
    records = []

    for pm in root.findall("pm"):
        records.append({
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
        })

    return pd.DataFrame(records)


def fetch_air_quality() -> pd.DataFrame:
    print("Descargando calidad del aire...")
    response = httpx.get(
        settings.AIR_QUALITY_URL,
        headers={"User-Agent": settings.USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()

    return pd.read_csv(StringIO(response.text), sep=";")


if __name__ == "__main__":
    df_traffic = fetch_traffic()
    print(f"\n--- TRÁFICO ({len(df_traffic)} sensores activos) ---")
    print(df_traffic.head(5))

    df_air = fetch_air_quality()
    print(f"\n--- CALIDAD DEL AIRE ({len(df_air)} filas) ---")
    print(df_air.head(5))