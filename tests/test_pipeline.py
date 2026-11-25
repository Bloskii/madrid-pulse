import pytest
from src.schemas import TrafficReading, AirStation
from src.cleaners import parse_and_validate_traffic, parse_and_validate_air
from src.geo_utils import haversine_km, map_stations_to_traffic


def test_traffic_valid_utm_conversion():
    """Verifica que un sensor sano transforma correctamente UTM a GPS."""
    raw = {
        "timestamp": "16/11/2026 10:25:02",
        "id": "3409",
        "descripcion": "SEPULVEDA N-S",
        "intensidad": "450",
        "ocupacion": "12",
        "carga": "18",
        "nivel_servicio": "0",
        "error": "N",
        "lat": "4472588,47",
        "lon": "436004,10",
    }
    reading = TrafficReading.from_raw_xml(raw)
    assert reading is not None
    assert reading.sensor_id == "3409"
    assert reading.intensity == 450
    assert 40.3 < reading.latitude < 40.5
    assert -3.8 < reading.longitude < -3.6


def test_traffic_discard_broken_sensor():
    """Verifica que sensores con error='S' o intensidad negativa se descartan."""
    raw_error = {
        "timestamp": "16/11/2026 10:25:02",
        "id": "9999",
        "intensidad": "100",
        "ocupacion": "10",
        "carga": "10",
        "nivel_servicio": "0",
        "error": "S",
        "lat": "4472588,47",
        "lon": "436004,10",
    }
    assert TrafficReading.from_raw_xml(raw_error) is None

    raw_negative = {**raw_error, "error": "N", "intensidad": "-1"}
    assert TrafficReading.from_raw_xml(raw_negative) is None


def test_parse_xml_traffic_filters_bad_nodes():
    """Simula un XML real con un nodo sano y otro corrupto."""
    xml_sample = b"""<?xml version="1.0" encoding="UTF-8"?>
    <pms>
        <fecha_hora>16/11/2026 10:25:02</fecha_hora>
        <pm>
            <idelem>1001</idelem>
            <descripcion>M-30 KM 5</descripcion>
            <intensidad>1200</intensidad>
            <ocupacion>25</ocupacion>
            <carga>30</carga>
            <nivelServicio>1</nivelServicio>
            <error>N</error>
            <st_x>440123,45</st_x>
            <st_y>4474123,45</st_y>
        </pm>
        <pm>
            <idelem>1002</idelem>
            <intensidad>-1</intensidad>
            <error>S</error>
        </pm>
    </pms>
    """
    results = parse_and_validate_traffic(xml_sample)
    assert len(results) == 1
    assert results[0].sensor_id == "1001"


def test_parse_air_quality_latest_valid_hour():
    """Verifica que extrae la última hora marcada con 'V' e ignora las 'N'."""
    csv_sample = (
        "PROVINCIA;MUNICIPIO;ESTACION;MAGNITUD;ANO;MES;DIA;"
        "H01;V01;H02;V02;H03;V03\n"
        "28;79;11;8;2026;11;25;32.5;V;48.0;V;0.0;N\n"
    )
    results = parse_and_validate_air(csv_sample)
    assert len(results) == 1
    assert results[0].station_code == "28079011"
    assert results[0].pollutant == "NO2"
    assert results[0].value == 48.0


def test_haversine_and_spatial_join():
    """Verifica el filtrado por radio de 1 km entre estación y sensores."""
    station = AirStation(
        station_code="28079004",
        name="Plaza de España",
        latitude=40.4238,
        longitude=-3.7122,
    )
    near_sensor = TrafficReading(
        sensor_id="1",
        timestamp="2026-11-25T10:00:00",
        description="Gran Vía",
        intensity=800,
        occupancy=20,
        load=25,
        service_level=1,
        latitude=40.4210,  # ~350 metros de Plaza de España
        longitude=-3.7085,
    )
    far_sensor = TrafficReading(
        sensor_id="2",
        timestamp="2026-11-25T10:00:00",
        description="Barajas",
        intensity=500,
        occupancy=10,
        load=15,
        service_level=0,
        latitude=40.4722,  # >6 km de distancia
        longitude=-3.5777,
    )

    assert haversine_km(station.latitude, station.longitude, near_sensor.latitude, near_sensor.longitude) < 1.0
    mapping = map_stations_to_traffic([station], [near_sensor, far_sensor], radius_km=1.0)
    assert [s.sensor_id for s in mapping["28079004"]] == ["1"]