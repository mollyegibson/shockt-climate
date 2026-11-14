"""Database access for the route calculator API.

Connects as shockt_app (read-only on core). On startup the API loads distances, nodes and factors
into memory — they total ~35K rows and change only when the offline pipeline runs.
"""

from dataclasses import dataclass

import psycopg
from psycopg.rows import tuple_row
from shockt_engine import EdgeDistance, Factor, FeederEdge, Node, RouteDistances

# ---------------------------------------------------------------------------
# Cached data loaded at startup
# ---------------------------------------------------------------------------


@dataclass
class CachedData:
    """All the data the route calculator needs, loaded once at startup."""

    nodes: dict[str, Node]
    distances: RouteDistances
    factors: list[Factor]
    crossing_plants: dict[str, dict[str, str]]
    node_voyages: dict[str, int]


def _load_nodes(conn: psycopg.Connection[tuple]) -> dict[str, Node]:
    rows = conn.execute(
        "select node_id, kind, name, iso3, lat, lon, source_key from core.dim_nodes"
    ).fetchall()
    return {
        r[0]: Node(kind=r[1], name=r[2], iso3=r[3], lat=r[4], lon=r[5], source_key=r[6])
        for r in rows
    }


def _load_sea_distances(
    conn: psycopg.Connection[tuple],
) -> dict[tuple[str, str], dict[str, EdgeDistance]]:
    rows = conn.execute(
        "select from_node_id, to_node_id, scenario, km, duration_h, passages "
        "from core.distances_sea"
    ).fetchall()
    sea: dict[tuple[str, str], dict[str, EdgeDistance]] = {}
    for from_id, to_id, scenario, km, duration_h, passages in rows:
        key = (from_id, to_id)
        passage_tuple = tuple(passages.split("|")) if passages else ()
        sea.setdefault(key, {})[scenario] = EdgeDistance(
            km=float(km),
            duration_h=float(duration_h) if duration_h else None,
            passages=passage_tuple,
        )
    return sea


_EDGE_SQL: dict[str, str] = {
    "distances_air": "select from_node_id, to_node_id, km from core.distances_air",
    "distances_road": ("select from_node_id, to_node_id, km, duration_h from core.distances_road"),
    "distances_rail": "select from_node_id, to_node_id, km from core.distances_rail",
}


def _load_edge_distances(
    conn: psycopg.Connection[tuple], table: str
) -> dict[tuple[str, str], EdgeDistance]:
    sql = _EDGE_SQL[table]
    has_duration = table in ("distances_road",)
    rows = conn.execute(sql).fetchall()
    if has_duration:
        return {
            (r[0], r[1]): EdgeDistance(km=float(r[2]), duration_h=float(r[3]) if r[3] else None)
            for r in rows
        }
    return {(r[0], r[1]): EdgeDistance(km=float(r[2]), duration_h=None) for r in rows}


def _load_feeder_edges(
    conn: psycopg.Connection[tuple],
) -> dict[tuple[str, str], FeederEdge]:
    rows = conn.execute(
        "select "
        "  'departure_port:' || origin_port_id as origin_node, "
        "  'departure_port:' || hub_port_id as hub_node, "
        "  weighted_mean_distance_km, "
        "  hub_has_us_voyages "
        "from core.agg_feeder_hub_shares_monthly "
        "where year_month = (select max(year_month) from core.agg_feeder_hub_shares_monthly)"
    ).fetchall()
    result: dict[tuple[str, str], FeederEdge] = {}
    for origin_node, hub_node, km, hub_has_us in rows:
        result[(origin_node, hub_node)] = FeederEdge(
            km=float(km),
            duration_h=float(km) / 23.15 if km else None,
            hub_has_us_voyages=hub_has_us,
        )
    return result


def _to_float(v: object) -> float | None:
    return float(v) if v is not None else None


def _load_factors(conn: psycopg.Connection[tuple]) -> list[Factor]:
    rows = conn.execute(
        "select source, source_row_id, mode, variant, vehicle_type, size_class, "
        "haul, radiative_forcing, ttw_kg_co2e_per_tkm, wtt_kg_co2e_per_tkm, wtw_kg_co2e_per_tkm "
        "from core.ref_emission_factors"
    ).fetchall()
    return [
        Factor(
            source=r[0],
            source_row_id=r[1],
            mode=r[2],
            variant=r[3],
            vehicle_type=r[4],
            size_class=r[5],
            haul=r[6],
            radiative_forcing=r[7],
            ttw_kg_co2e_per_tkm=_to_float(r[8]),
            wtt_kg_co2e_per_tkm=_to_float(r[9]),
            wtw_kg_co2e_per_tkm=_to_float(r[10]),
        )
        for r in rows
    ]


def _load_crossing_plants(
    conn: psycopg.Connection[tuple],
) -> dict[str, dict[str, str]]:
    """Load map_crossing_plant: {hs6: {crossing_node_id: plant_node_id}}."""
    rows = conn.execute(
        "select hs6, "
        "  'border_crossing:' || port_code as crossing_node, "
        "  'mexico_plant:' || plant_id as plant_node "
        "from core.map_crossing_plant"
    ).fetchall()
    result: dict[str, dict[str, str]] = {}
    for hs6, crossing_node, plant_node in rows:
        result.setdefault(hs6, {})[crossing_node] = plant_node
    return result


def _load_node_voyages(
    conn: psycopg.Connection[tuple],
) -> dict[str, int]:
    """Voyage counts per departure port, for port cluster dedup."""
    rows = conn.execute(
        "select 'departure_port:' || start_port_id, container_voyages "
        "from core.dim_departure_ports "
        "where container_voyages > 0"
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def load_cached_data(database_url: str) -> CachedData:
    """Connect to the database and load all data the calculator needs."""
    with psycopg.connect(database_url, row_factory=tuple_row) as conn:
        nodes = _load_nodes(conn)
        sea = _load_sea_distances(conn)
        air = _load_edge_distances(conn, "distances_air")
        road = _load_edge_distances(conn, "distances_road")
        rail = _load_edge_distances(conn, "distances_rail")
        feeder = _load_feeder_edges(conn)
        factors = _load_factors(conn)
        crossing_plants = _load_crossing_plants(conn)
        node_voyages = _load_node_voyages(conn)

    return CachedData(
        nodes=nodes,
        distances=RouteDistances(sea=sea, air=air, road=road, rail=rail, feeder=feeder),
        factors=factors,
        crossing_plants=crossing_plants,
        node_voyages=node_voyages,
    )


# ---------------------------------------------------------------------------
# Per-request queries (node search, commodity context)
# ---------------------------------------------------------------------------


def search_nodes(
    conn: psycopg.Connection[tuple],
    q: str,
    kind: str | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    """Search nodes by name, country name or ISO code."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    sql = (
        "select n.node_id, n.kind, n.name, n.iso3, n.lat, n.lon "
        "from core.dim_nodes n "
        "left join core.dim_country c on c.iso3 = n.iso3 "
        "where (n.name ilike %(pattern)s or n.iso3 ilike %(pattern)s "
        "  or c.country_name ilike %(pattern)s)"
    )
    params: dict[str, object] = {"pattern": pattern, "limit": limit}
    if kind:
        sql += " and n.kind = %(kind)s"
        params["kind"] = kind
    sql += " order by n.name limit %(limit)s"
    rows = conn.execute(sql, params).fetchall()
    return [
        {"node_id": r[0], "kind": r[1], "name": r[2], "iso3": r[3], "lat": r[4], "lon": r[5]}
        for r in rows
    ]


def list_countries(conn: psycopg.Connection[tuple]) -> list[dict[str, object]]:
    """Countries with departure nodes, plus which modes are available."""
    rows = conn.execute(
        "select distinct n.iso3, c.country_name "
        "from core.dim_nodes n "
        "join core.dim_country c on c.iso3 = n.iso3 "
        "where n.kind in ('departure_port', 'departure_airport', 'mexico_plant') "
        "order by c.country_name"
    ).fetchall()

    result = []
    for iso3, name in rows:
        modes: list[str] = []
        if iso3 == "MEX":
            modes.extend(["vessel", "air", "truck", "rail"])
        else:
            modes.extend(["vessel", "air"])
        result.append({"iso3": iso3, "name": name, "modes": modes})
    return result


def commodity_context(conn: psycopg.Connection[tuple], hs6: str) -> dict[str, object] | None:
    """HS code description and top arrival ports by tonnage."""
    desc_row = conn.execute(
        "select description from core.dim_hs where hs6 = %(hs6)s",
        {"hs6": hs6},
    ).fetchone()
    if desc_row is None:
        return None

    port_rows = conn.execute(
        "select w.node_id, n.name, sum(w.weight_t) as total_t "
        "from core.fct_node_weights_monthly w "
        "join core.dim_nodes n on n.node_id = w.node_id "
        "where w.hs6 = %(hs6)s and n.kind = 'arrival_seaport' "
        "group by w.node_id, n.name "
        "order by total_t desc "
        "limit 10",
        {"hs6": hs6},
    ).fetchall()

    return {
        "hs6": hs6,
        "description": desc_row[0],
        "top_ports": [{"node_id": r[0], "name": r[1], "weight_t": float(r[2])} for r in port_rows],
    }
