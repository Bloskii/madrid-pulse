import xml.etree.ElementTree as ET
from io import StringIO
import httpx
import pandas as pd

# Endpoints oficiales del Portal de Datos Abiertos de Madrid
TRAFFIC_URL = "https://informo.madrid.es/informo/tmadrid/pm.xml"
AIR_QUALITY_URL = "https://datos.madrid.es/egob/catalogo/212531-10515086-calidad-aire-tiempo-real.csv"


def fetch_traffic() -> pd.DataFrame:
    print("Descargando tráfico en tiempo real...")
    response = httpx.get(TRAFFIC_URL, timeout=15.0, follow_redirects=True)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    fecha_hora = root.findtext("fecha_hora")
    records = []

    for pm in root.findall("pm"):
        records.append({
            "timestamp": fecha_hora,
            "id": pm.findtext("idelem"),
            "descripcion": pm.findtext("descripcion"),
            "intensidad": pm.findtext("intensidad"),  # vehículos/hora
            "ocupacion": pm.findtext("ocupacion"),    # % ocupación
            "carga": pm.findtext("carga"),            # % carga vial
            "nivel_servicio": pm.findtext("nivelServicio"),
            "error": pm.findtext("error"),
            "lat": pm.findtext("st_y"),               # Coordenadas UTM (luego las pasamos a lat/lon)
            "lon": pm.findtext("st_x"),
        })

    return pd.DataFrame(records)


def fetch_air_quality() -> pd.DataFrame:
    print("Descargando calidad del aire...")
    headers = {"User-Agent": "Mozilla/5.0"}
    response = httpx.get(
        AIR_QUALITY_URL,
        headers=headers,
        timeout=15.0,
        follow_redirects=True,
    )
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text), sep=";")
    return df


if __name__ == "__main__":
    df_traffic = fetch_traffic()
    print(f"\n--- TRÁFICO ({len(df_traffic)} sensores activos) ---")
    print(df_traffic.head(5))

    df_air = fetch_air_quality()
    print(f"\n--- CALIDAD DEL AIRE ({len(df_air)} filas) ---")
    print(df_air.head(5))