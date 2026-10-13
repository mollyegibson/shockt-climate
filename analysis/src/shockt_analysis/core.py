"""Reads `core` (and the distance seeds and load manifest in `raw`) into data frames and plain
values for the engine, as the read-only analyst login. The only module that touches the
database."""

from collections.abc import Sequence

import polars as pl
import psycopg
from shockt_engine import Factor

from shockt_analysis.settings import Settings


def connect(settings: Settings) -> psycopg.Connection:
    conn = psycopg.connect(settings.analyst_database_url.get_secret_value())
    conn.read_only = True
    return conn


def frame(
    conn: psycopg.Connection, sql: str, params: dict[str, object] | None = None
) -> pl.DataFrame:
    cur = conn.execute(sql, params)
    columns = [d.name for d in cur.description or []]
    return pl.DataFrame(cur.fetchall(), schema=columns, orient="row", infer_schema_length=None)


def origins(conn: psycopg.Connection) -> pl.DataFrame:
    """The configured origin countries: Census code, ISO3, name and region."""
    return frame(
        conn,
        "select census_cty_code, iso3, cty_name, region from core.dim_country "
        "where region <> 'other'",
    )


def case_codes(conn: psycopg.Connection) -> pl.DataFrame:
    """The case HS prefixes and the cases each belongs to (`seed_hs_case_codes`)."""
    return frame(conn, "select hs_prefix, cases from raw.seed_hs_case_codes order by hs_prefix")


def supply(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly tonnage by origin, HS-6 and delivery mode, with a low and high: air and vessel as
    Census reports them (low = high), truck and rail from Mexico as estimated."""
    return frame(
        conn,
        """
        with mexico as (select census_cty_code from core.dim_country where iso3 = 'MEX'),
        reported as (
            select month, census_cty_code, hs6, mode, sum(weight_t) as weight_t
            from core.fct_imports_monthly
            where hs6 = any(%(hs6)s) and mode in ('air', 'vessel') and weight_t > 0
            group by month, census_cty_code, hs6, mode
        ),
        overland as (
            select o.month, m.census_cty_code, o.hs6, o.mode,
                sum(o.weight_t) as weight_t, sum(o.weight_t_low) as weight_t_low,
                sum(o.weight_t_high) as weight_t_high
            from core.fct_mexico_overland_monthly as o
            cross join mexico as m
            where o.hs6 = any(%(hs6)s) and o.weight_t > 0
            group by o.month, m.census_cty_code, o.hs6, o.mode
        ),
        rows as (
            select month, census_cty_code, hs6, mode, weight_t,
                weight_t as weight_t_low, weight_t as weight_t_high
            from reported
            union all
            select * from overland
        )
        select r.month, r.census_cty_code, c.iso3, c.cty_name, r.hs6, r.mode,
            r.weight_t::float8 as weight_t, r.weight_t_low::float8 as weight_t_low,
            r.weight_t_high::float8 as weight_t_high
        from rows as r
        join core.dim_country as c using (census_cty_code)
        where c.region <> 'other'
        order by r.month, c.iso3, r.hs6, r.mode
        """,
        {"hs6": list(hs6)},
    )


def node_weights(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Node weights by month, origin, HS-6 and mode, with each node's kind."""
    return frame(
        conn,
        """
        select w.month, w.node_id, n.kind, w.census_cty_code, w.hs6, w.mode,
            w.lane_coast_region, w.weight_t::float8 as weight_t
        from core.fct_node_weights_monthly as w
        join core.dim_nodes as n using (node_id)
        where w.hs6 = any(%(hs6)s)
        """,
        {"hs6": list(hs6)},
    )


def observed_sea(conn: psycopg.Connection) -> pl.DataFrame:
    """Observed sea distance by month, origin and US arrival seaport."""
    return frame(
        conn,
        """
        select month, origin_iso3, arrival_node_id, n_voyages,
            median_distance_km::float8 as median_distance_km
        from core.agg_observed_sea_distances_monthly
        """,
    )


def distances(
    conn: psycopg.Connection, seed: str, scenario: str | None = None
) -> dict[tuple[str, str], float]:
    """(from node, to node) → km from one distance seed; `scenario` selects a sea scenario."""
    if seed not in ("sea", "air", "road", "rail"):
        raise ValueError(f"no distance seed named {seed}")
    sql = f"select from_node_id, to_node_id, km::float8 from raw.seed_{seed}_distances"
    params: dict[str, object] = {}
    if seed == "sea":
        sql += " where scenario = %(scenario)s"
        params["scenario"] = scenario or "open"
    return {(a, b): km for a, b, km in conn.execute(sql, params).fetchall()}


def crossing_plants(conn: psycopg.Connection) -> pl.DataFrame:
    """For each crossing and HS-6, the node of the plant its Mexican leg starts at."""
    return frame(
        conn,
        """
        select 'border_crossing:' || port_code as crossing_node_id, hs6,
            'mexico_plant:' || plant_id as plant_node_id
        from core.map_crossing_plant
        """,
    )


def factors(conn: psycopg.Connection) -> list[Factor]:
    rows = conn.execute(
        """
        select source, source_row_id, mode, variant, vehicle_type, size_class, haul,
            radiative_forcing, wtw_kg_co2e_per_tkm
        from core.ref_emission_factors
        """
    ).fetchall()
    return [Factor(*row) for row in rows]


def current_loads(conn: psycopg.Connection, datasets: Sequence[str]) -> pl.DataFrame:
    """The current loads behind a result: per dataset, how many partitions and the latest load."""
    return frame(
        conn,
        """
        select dataset, count(*) as partitions, max(finished_at)::text as latest_load,
            string_agg(distinct code_version, ', ' order by code_version) as code_versions
        from raw.load_manifest
        where status = 'succeeded' and dataset = any(%(datasets)s)
        group by dataset
        order by dataset
        """,
        {"datasets": list(datasets)},
    )
