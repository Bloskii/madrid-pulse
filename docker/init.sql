CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS station_metrics (
    timestamp TIMESTAMPTZ NOT NULL,
    station_code VARCHAR(16) NOT NULL,
    station_name TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    pollutant VARCHAR(16) NOT NULL,
    pollutant_value DOUBLE PRECISION NOT NULL,
    nearby_sensors_count INTEGER NOT NULL,
    avg_traffic_intensity DOUBLE PRECISION NOT NULL,
    avg_traffic_occupancy DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (timestamp, station_code, pollutant)
);

-- Convertimos la tabla normal de PostgreSQL en una Hypertable particionada por tiempo
SELECT create_hypertable('station_metrics', 'timestamp', if_not_exists => TRUE);