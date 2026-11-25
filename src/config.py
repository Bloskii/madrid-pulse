import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Endpoints oficiales del Portal de Datos Abiertos de Madrid
    TRAFFIC_URL: str = os.getenv(
        "TRAFFIC_URL",
        "https://informo.madrid.es/informo/tmadrid/pm.xml",
    )
    AIR_QUALITY_URL: str = os.getenv(
        "AIR_QUALITY_URL",
        "https://datos.madrid.es/egob/catalogo/212531-10515086-calidad-aire-tiempo-real.csv",
    )
    AIR_STATIONS_URL: str = os.getenv(
        "AIR_STATIONS_URL",
        "https://datos.madrid.es/egob/catalogo/212629-1-estaciones-control-aire.csv",
    )

    # Configuración de peticiones HTTP
    HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "35.0"))
    USER_AGENT: str = "MadridPulse-DataPipeline/1.0 (UPM-Student-Portfolio)"

    # Parámetros geoespaciales y de negocio
    SEARCH_RADIUS_KM: float = float(os.getenv("SEARCH_RADIUS_KM", "1.0"))
    POLLUTANTS_OF_INTEREST: tuple[int, ...] = (8, 9, 10, 14)  # NO2, PM2.5, PM10, O3
    
    # Streaming y Base de Datos
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    TOPIC_TRAFFIC: str = "traffic.raw"
    TOPIC_AIR_QUALITY: str = "air_quality.raw"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://madrid_user:madrid_password@localhost:5432/madrid_pulse",
    )


settings = Settings()