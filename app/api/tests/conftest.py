"""Test fixtures: a throwaway Postgres container seeded with the core schema and minimal test data,
plus an httpx TestClient wired to the FastAPI app."""

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import tuple_row
from starlette.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

# ---------------------------------------------------------------------------
# Database container
# ---------------------------------------------------------------------------

POSTGRES_IMAGE = "postgres:17"


def _seed_schema(conn: psycopg.Connection[tuple]) -> None:
    """Create the core schema and minimal tables the API reads from."""
    conn.execute("create schema if not exists core")

    conn.execute("""
        create table core.dim_country (
            census_cty_code text primary key,
            iso3 text,
            iso2 text,
            country_name text
        )
    """)

    conn.execute("""
        create table core.dim_nodes (
            node_id text primary key,
            kind text not null,
            name text not null,
            iso3 text,
            lat double precision,
            lon double precision,
            source_key text
        )
    """)

    conn.execute("""
        create table core.dim_departure_ports (
            start_port_id text primary key,
            port_name text,
            iso3 text,
            lon double precision,
            lat double precision,
            container_voyages bigint default 0,
            feeder_voyages bigint default 0,
            feeder_origin_voyages bigint default 0,
            is_us_departure boolean default false,
            is_feeder_hub boolean default false,
            is_feeder_origin boolean default false
        )
    """)

    conn.execute("""
        create table core.distances_sea (
            from_node_id text,
            to_node_id text,
            scenario text,
            km numeric,
            duration_h numeric,
            passages text,
            source text
        )
    """)

    conn.execute("""
        create table core.distances_air (
            from_node_id text,
            to_node_id text,
            km numeric,
            source text
        )
    """)

    conn.execute("""
        create table core.distances_road (
            from_node_id text,
            to_node_id text,
            km numeric,
            duration_h numeric,
            source text
        )
    """)

    conn.execute("""
        create table core.distances_rail (
            from_node_id text,
            to_node_id text,
            km numeric,
            from_snap_km numeric,
            to_snap_km numeric,
            source text
        )
    """)

    conn.execute("""
        create table core.agg_feeder_hub_shares_monthly (
            year_month date,
            origin_iso3 text,
            origin_port_id text,
            hub_port_id text,
            hub_iso3 text,
            hub_has_us_voyages boolean,
            weighted_mean_distance_km numeric,
            share numeric
        )
    """)

    conn.execute("""
        create table core.ref_emission_factors (
            source text,
            source_row_id text,
            mode text,
            variant text,
            vehicle_type text,
            size_class text,
            haul text,
            radiative_forcing boolean,
            ttw_kg_co2e_per_tkm numeric,
            wtt_kg_co2e_per_tkm numeric,
            wtw_kg_co2e_per_tkm numeric
        )
    """)

    conn.execute("""
        create table core.map_crossing_plant (
            hs6 text,
            port_code text,
            plant_id text
        )
    """)

    conn.execute("""
        create table core.dim_hs (
            hs6 text,
            hs10 text primary key,
            description text
        )
    """)

    conn.execute("""
        create table core.fct_node_weights_monthly (
            month date,
            node_id text,
            census_cty_code text,
            hs6 text,
            mode text,
            lane_coast_region text,
            weight_t numeric,
            weight_t_low numeric,
            weight_t_high numeric,
            weight_basis text
        )
    """)

    conn.commit()


def _seed_test_data(conn: psycopg.Connection[tuple]) -> None:
    """Insert minimal realistic data for test scenarios."""
    # Countries
    conn.execute(
        "insert into core.dim_country (census_cty_code, iso3, iso2, country_name) values "
        "('5010', 'BGD', 'BD', 'Bangladesh'), "
        "('5700', 'CHN', 'CN', 'China'), "
        "('2010', 'MEX', 'MX', 'Mexico')"
    )

    # Nodes: departure ports, seaports, airports, gateways, states, crossings, plants
    nodes = [
        ("departure_port:BGD_100", "departure_port", "Chittagong", "BGD", 22.33, 91.80, "BGD_100"),
        ("departure_port:BGD_101", "departure_port", "Mongla", "BGD", 22.49, 89.60, "BGD_101"),
        ("departure_port:CHN_200", "departure_port", "Shanghai", "CHN", 31.23, 121.47, "CHN_200"),
        ("arrival_seaport:2704", "arrival_seaport", "Los Angeles", "USA", 33.74, -118.27, "2704"),
        ("arrival_seaport:0401", "arrival_seaport", "New York", "USA", 40.68, -74.04, "0401"),
        ("departure_airport:DAC", "departure_airport", "Dhaka", "BGD", 23.84, 90.40, "DAC"),
        ("air_gateway:LAX", "air_gateway", "Los Angeles", "USA", 33.94, -118.41, "LAX"),
        ("destination_state:TX", "destination_state", "Texas", "USA", 31.0, -100.0, "TX"),
        ("destination_state:CA", "destination_state", "California", "USA", 36.78, -119.42, "CA"),
        ("border_crossing:2304", "border_crossing", "Laredo", "MEX", 27.50, -99.51, "2304"),
        (
            "mexico_plant:plant_1",
            "mexico_plant",
            "Monterrey Factory",
            "MEX",
            25.67,
            -100.31,
            "plant_1",
        ),
    ]
    for node_id, kind, name, iso3, lat, lon, source_key in nodes:
        conn.execute(
            "insert into core.dim_nodes (node_id, kind, name, iso3, lat, lon, source_key) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (node_id, kind, name, iso3, lat, lon, source_key),
        )

    # Departure ports
    conn.execute(
        "insert into core.dim_departure_ports "
        "(start_port_id, port_name, iso3, lon, lat, container_voyages, is_us_departure) values "
        "('BGD_100', 'Chittagong', 'BGD', 91.80, 22.33, 50, true), "
        "('BGD_101', 'Mongla', 'BGD', 89.60, 22.49, 10, true), "
        "('CHN_200', 'Shanghai', 'CHN', 121.47, 31.23, 200, true)"
    )

    # Sea distances (two scenarios)
    bgd_100, bgd_ny = "departure_port:BGD_100", "arrival_seaport:0401"
    bgd_la = "arrival_seaport:2704"
    chn_200 = "departure_port:CHN_200"
    bsg = "babalmandab|suez|gibraltar"
    sea_rows = [
        (bgd_100, bgd_la, "open", 18950, bsg),
        (bgd_100, bgd_ny, "open", 15500, bsg),
        (bgd_100, bgd_la, "suez_closed", 22400, "babalmandab|gibraltar"),
        (chn_200, bgd_la, "open", 11600, ""),
        (chn_200, bgd_ny, "open", 19200, "panama"),
        (chn_200, bgd_ny, "panama_closed", 22100, "suez|gibraltar"),
    ]
    for from_id, to_id, scenario, km, passages in sea_rows:
        duration_h = km / 23.15
        conn.execute(
            "insert into core.distances_sea "
            "(from_node_id, to_node_id, scenario, km, duration_h, passages, source) "
            "values (%s, %s, %s, %s, %s, %s, 'test')",
            (from_id, to_id, scenario, km, duration_h, passages),
        )

    # Air distances
    conn.execute(
        "insert into core.distances_air (from_node_id, to_node_id, km, source) values "
        "('departure_airport:DAC', 'air_gateway:LAX', 13300, 'test')"
    )

    # Road distances
    road_rows = [
        ("arrival_seaport:2704", "destination_state:TX", 2200, 22.5),
        ("arrival_seaport:2704", "destination_state:CA", 50, 0.8),
        ("arrival_seaport:0401", "destination_state:TX", 2800, 28.0),
        ("air_gateway:LAX", "destination_state:TX", 2200, 22.5),
        ("air_gateway:LAX", "destination_state:CA", 50, 0.8),
        ("border_crossing:2304", "destination_state:TX", 250, 3.5),
        ("mexico_plant:plant_1", "border_crossing:2304", 220, 3.0),
    ]
    for from_id, to_id, km, duration_h in road_rows:
        conn.execute(
            "insert into core.distances_road (from_node_id, to_node_id, km, duration_h, source) "
            "values (%s, %s, %s, %s, 'test')",
            (from_id, to_id, km, duration_h),
        )

    # Emission factors
    factors = [
        (
            "uk_desnz",
            "uk_1",
            "ocean",
            "container_ship_avg",
            "container_ship",
            "average",
            None,
            None,
            0.0131,
            0.0027,
            0.0158,
        ),
        (
            "uk_desnz",
            "uk_2",
            "air",
            "freight_flight_int",
            "freight_flight",
            None,
            "international",
            True,
            0.4927,
            0.1094,
            0.6021,
        ),
        (
            "epa_hub",
            "epa_1",
            "truck",
            "mhd_truck",
            "medium_heavy_duty_truck",
            None,
            None,
            None,
            0.0892,
            0.0181,
            0.1073,
        ),
        (
            "epa_hub",
            "epa_2",
            "rail",
            "rail_freight",
            "rail",
            None,
            None,
            None,
            0.0245,
            0.0033,
            0.0278,
        ),
    ]
    for row in factors:
        conn.execute(
            "insert into core.ref_emission_factors "
            "(source, source_row_id, mode, variant, vehicle_type, size_class, haul, "
            "radiative_forcing, ttw_kg_co2e_per_tkm, wtt_kg_co2e_per_tkm, wtw_kg_co2e_per_tkm) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            row,
        )

    # Crossing-plant mapping
    conn.execute(
        "insert into core.map_crossing_plant (hs6, port_code, plant_id) values "
        "('841810', '2304', 'plant_1')"
    )

    conn.commit()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A throwaway Postgres container for the test session."""
    with PostgresContainer(POSTGRES_IMAGE, driver=None) as postgres:
        url = postgres.get_connection_url()
        with psycopg.connect(url, row_factory=tuple_row) as conn:
            _seed_schema(conn)
            _seed_test_data(conn)
        yield url


@pytest.fixture(scope="session")
def client(database_url: str) -> Iterator[TestClient]:
    """Starlette TestClient wired to the FastAPI app with test data loaded."""
    import os

    os.environ["DATABASE_URL"] = database_url

    from shockt_api.main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
