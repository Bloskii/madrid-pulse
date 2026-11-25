from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from pyproj import Transformer

# Transformador cartográfico: ETRS89 / UTM zona 30N (EPSG:25830) -> GPS Lat/Lon (EPSG:4326)
_utm_to_latlon = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)

POLLUTANT_MAP = {
    8: "NO2",    # Dióxido de nitrógeno (principal indicador de emisiones de tráfico)
    9: "PM2.5",  # Partículas en suspensión < 2.5 micras
    10: "PM10",  # Partículas en suspensión < 10 micras
    14: "O3",    # Ozono troposférico
}


class TrafficReading(BaseModel):
    sensor_id: str
    timestamp: datetime
    description: str
    intensity: int = Field(ge=0, description="Vehículos/hora (descarta valores -1)")
    occupancy: int = Field(ge=0, le=100, description="Porcentaje de ocupación vial")
    load: int = Field(ge=0, le=100, description="Porcentaje de carga vial")
    service_level: int = Field(ge=0, le=3, description="0=Fluido, 1=Lento, 2=Retenciones, 3=Colapsado")
    latitude: float = Field(ge=40.0, le=41.0, description="Latitud dentro de Madrid")
    longitude: float = Field(ge=-4.2, le=-3.3, description="Longitud dentro de Madrid")

    @classmethod
    def from_raw_xml(cls, raw: dict) -> Optional["TrafficReading"]:
        # 1. Descartar sensores averiados o en mantenimiento
        if raw.get("error") != "N":
            return None

        try:
            # 2. Convertir coma decimal española ("4472588,47") a float y proyectar a GPS
            utm_x = float(raw["lon"].replace(",", "."))
            utm_y = float(raw["lat"].replace(",", "."))
            lon, lat = _utm_to_latlon.transform(utm_x, utm_y)

            # 3. Parsear fecha formato "dd/mm/yyyy HH:MM:SS"
            ts = datetime.strptime(raw["timestamp"], "%d/%m/%Y %H:%M:%S")

            return cls(
                sensor_id=str(raw["id"]).strip(),
                timestamp=ts,
                description=(raw.get("descripcion") or "Sin descripción").strip(),
                intensity=int(raw["intensidad"]),
                occupancy=int(raw["ocupacion"]),
                load=int(raw["carga"]),
                service_level=int(raw["nivel_servicio"]),
                latitude=round(lat, 6),
                longitude=round(lon, 6),
            )
        except (ValueError, TypeError, KeyError):
            # Si algún campo viene corrupto o fuera de rango, se descarta el evento sin romper el pipeline
            return None


class AirQualityReading(BaseModel):
    station_code: str
    timestamp: datetime
    pollutant: str
    value: float = Field(ge=0.0, description="Concentración en µg/m³")

    @field_validator("pollutant")
    @classmethod
    def check_known_pollutant(cls, v: str) -> str:
        if v not in POLLUTANT_MAP.values():
            raise ValueError(f"Contaminante no monitorizado: {v}")
        return v

class AirStation(BaseModel):
    station_code: str
    name: str
    latitude: float = Field(ge=40.0, le=41.0)
    longitude: float = Field(ge=-4.2, le=-3.3)