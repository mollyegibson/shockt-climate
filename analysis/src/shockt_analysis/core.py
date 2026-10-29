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
    """Node weights by month, origin, HS-6 and mode, with each node's kind and coast region."""
    return frame(
        conn,
        """
        select w.month, w.node_id, n.kind, n.coast_region, w.census_cty_code, w.hs6, w.mode,
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
            median_distance_km::float8 as median_distance_km,
            mean_duration_h::float8 as mean_duration_h
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


def factor_components(conn: psycopg.Connection) -> pl.DataFrame:
    """TTW, WTT and WTW components from the UK DESNZ emission factors."""
    return frame(
        conn,
        """
        select variant, ttw_kg_co2e_per_tkm, wtt_kg_co2e_per_tkm, wtw_kg_co2e_per_tkm
        from core.ref_emission_factors
        where source = 'uk_desnz'
            and ttw_kg_co2e_per_tkm is not null
            and wtt_kg_co2e_per_tkm is not null
        """,
    )


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


def chokepoint_transits(conn: psycopg.Connection) -> pl.DataFrame:
    """Monthly transits by chokepoint: all ship types and container ships, with the days
    PortWatch reported in the month."""
    return frame(
        conn,
        """
        select month, chokepoint_id, chokepoint_name, days_reported, n_total, n_container
        from core.fct_chokepoint_transits_monthly
        order by chokepoint_id, month
        """,
    )


def voyage_lanes(conn: psycopg.Connection) -> pl.DataFrame:
    """Container voyages by month, origin country and US coast region, with their distances."""
    return frame(
        conn,
        """
        select month, origin_iso3, origin_region, end_coast_region, n_voyages,
            total_distance_km::float8 as total_distance_km,
            median_distance_km::float8 as median_distance_km,
            mean_duration_h::float8 as mean_duration_h
        from core.agg_voyage_lanes_monthly
        """,
    )


def imports_by_port(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly air and vessel tonnage by origin, HS-6, US port and its coast region, for the
    configured origins."""
    return frame(
        conn,
        """
        select p.month, p.census_cty_code, c.iso3, c.region, p.hs6, p.mode, p.port_code,
            p.coast_region, p.weight_t::float8 as weight_t
        from core.fct_imports_port_monthly as p
        join core.dim_country as c using (census_cty_code)
        where p.hs6 = any(%(hs6)s) and p.mode in ('air', 'vessel') and p.weight_t > 0
            and c.region <> 'other'
        """,
        {"hs6": list(hs6)},
    )


def imports_by_state(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly air and vessel tonnage by origin, HS-6 and state of destination, for the
    configured origins."""
    return frame(
        conn,
        """
        select s.month, s.census_cty_code, c.iso3, c.region, s.hs6, s.mode, s.state,
            s.weight_t::float8 as weight_t
        from core.fct_imports_state_monthly as s
        join core.dim_country as c using (census_cty_code)
        where s.hs6 = any(%(hs6)s) and s.mode in ('air', 'vessel') and s.weight_t > 0
            and c.region <> 'other'
        """,
        {"hs6": list(hs6)},
    )


def state_port_vessel(conn: psycopg.Connection, region: str) -> pl.DataFrame:
    """All goods: quarterly vessel tonnage from one origin region by state of destination and
    the coast region of the port of unlading."""
    return frame(
        conn,
        """
        select q.quarter, q.state, q.unlading_coast_region, sum(q.weight_t)::float8 as weight_t
        from core.fct_imports_state_port_quarterly as q
        join core.dim_country as c using (census_cty_code)
        where q.mode = 'vessel' and c.region = %(region)s
        group by q.quarter, q.state, q.unlading_coast_region
        """,
        {"region": region},
    )


def eu_imports(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly EU imports from extra-EU partners, summed across reporters, by HS-6, partner and
    transport mode."""
    return frame(
        conn,
        """
        select month, hs6, partner, transport_mode,
            quantity_kg::float8 as quantity_kg, value_eur::float8 as value_eur,
            reporter_count
        from core.agg_eu_imports_mode_monthly
        where hs6 = any(%(hs6)s)
        order by month, hs6, partner, transport_mode
        """,
        {"hs6": list(hs6)},
    )


def ship_fuel_intensities(conn: psycopg.Connection) -> pl.DataFrame:
    """Per-ship annual fuel intensity from THETIS-MRV, with a flag for whether the ship appears
    in Climate TRACE voyage data."""
    return frame(
        conn,
        """
        select imo_number, reporting_year, ship_name, ship_type, port_of_registry,
            total_fuel_consumption_mt::float8 as total_fuel_consumption_mt,
            total_co2_mt::float8 as total_co2_mt,
            total_co2eq_mt::float8 as total_co2eq_mt,
            time_at_sea_hours::float8 as time_at_sea_hours,
            fuel_per_distance_kg_nm::float8 as fuel_per_distance_kg_nm,
            co2_per_distance_kg_nm::float8 as co2_per_distance_kg_nm,
            co2_per_transport_work_mass::float8 as co2_per_transport_work_mass,
            in_voyage_data
        from core.fct_ship_fuel_intensities
        """,
    )


def duties(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly duty by HS-10 and country: consumption value, dutiable value and calculated duty."""
    return frame(
        conn,
        """
        select d.month, d.hs10, d.hs6, d.census_cty_code, c.iso3, c.cty_name,
            d.consumption_value_usd::float8 as consumption_value_usd,
            d.dutiable_value_usd::float8 as dutiable_value_usd,
            d.calculated_duty_usd::float8 as calculated_duty_usd
        from core.fct_import_duties_monthly as d
        join core.dim_country as c using (census_cty_code)
        where d.hs6 = any(%(hs6)s) and c.region <> 'other'
        order by d.month, c.iso3, d.hs6
        """,
        {"hs6": list(hs6)},
    )


def oecd_maritime_emissions(conn: psycopg.Connection, ref_area: str = "W") -> pl.DataFrame:
    """Monthly OECD maritime CO₂ by vessel type for one ref_area (default: world aggregate)."""
    return frame(
        conn,
        """
        select o.time_period as month, o.vessel,
            o.obs_value * power(10, o.unit_mult) as co2_t
        from raw.oecd_maritime_emissions as o
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'oecd_maritime_emissions'
            and o.ref_area = %(ref_area)s
        order by o.vessel, o.time_period
        """,
        {"ref_area": ref_area},
    )


def cbam_default_values(conn: psycopg.Connection) -> pl.DataFrame:
    """All CBAM default emission values from the current load."""
    return frame(
        conn,
        """
        select c.country, c.sector, c.cn_code, c.description, c.production_route,
            c.direct_emissions, c.indirect_emissions, c.total_emissions
        from raw.cbam_default_values as c
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'cbam_default_values'
        """,
    )


def sbti_companies(conn: psycopg.Connection) -> pl.DataFrame:
    """All SBTi companies from the current load."""
    return frame(
        conn,
        """
        select s.company_name, s.location, s.region as sbti_region, s.sector,
            s.near_term_status, s.long_term_status, s.net_zero_status,
            s.net_zero_year
        from raw.sbti_companies as s
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'sbti_companies'
        """,
    )


def countries(conn: psycopg.Connection) -> pl.DataFrame:
    """All Census Schedule C countries: code, name, ISO3 and analysis region."""
    return frame(conn, "select census_cty_code, cty_name, iso3, region from core.dim_country")


def cbam_countries(conn: psycopg.Connection) -> pl.DataFrame:
    """Distinct countries in the current CBAM default values, with the number of CN codes each."""
    return frame(
        conn,
        """
        select c.country, count(distinct c.cn_code) as n_cn_codes
        from raw.cbam_default_values as c
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'cbam_default_values'
        group by c.country
        order by c.country
        """,
    )


def ceda_country_codes(conn: psycopg.Connection) -> pl.DataFrame:
    """Distinct (country_code, country) in the current Open CEDA factors."""
    return frame(
        conn,
        """
        select distinct c.country_code, c.country
        from raw.open_ceda_factors as c
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'open_ceda_factors'
        order by c.country_code
        """,
    )


def oecd_ref_areas(conn: psycopg.Connection) -> pl.DataFrame:
    """Distinct ref_area codes in the current OECD maritime emissions, with total observations."""
    return frame(
        conn,
        """
        select o.ref_area, count(*) as n_obs
        from raw.oecd_maritime_emissions as o
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'oecd_maritime_emissions'
        group by o.ref_area
        order by o.ref_area
        """,
    )


def sbti_locations(conn: psycopg.Connection) -> pl.DataFrame:
    """Distinct (location, region) in the current SBTi companies, with counts."""
    return frame(
        conn,
        """
        select c.location, c.region, count(*) as n_companies
        from raw.sbti_companies as c
        join raw.load_manifest as m using (load_id)
        where m.status = 'succeeded' and m.dataset = 'sbti_companies'
        group by c.location, c.region
        order by c.location
        """,
    )


def air_values(conn: psycopg.Connection, hs6: Sequence[str]) -> pl.DataFrame:
    """Monthly air value and shipping weight by origin and HS-6, from Census."""
    return frame(
        conn,
        """
        select month, census_cty_code, hs6, sum(value_usd)::float8 as value_usd,
            sum(weight_t)::float8 as weight_t
        from core.fct_imports_monthly
        where hs6 = any(%(hs6)s) and mode = 'air' and weight_t > 0
        group by month, census_cty_code, hs6
        """,
        {"hs6": list(hs6)},
    )
