"""Node pairs the distance generators measure, read from `core`: pairs of nodes that carry freight
from the same origin country in `fct_node_weights_monthly`, with their coordinates from
`dim_nodes`. Reads as the transform login, which can read `core`."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from shockt.settings import Settings


@dataclass(frozen=True)
class Node:
    node_id: str
    lat: float
    lon: float
    name: str | None = None
    coast_region: str | None = None

    @property
    def offshore(self) -> bool:
        """Outside the contiguous US (the `coast_region` rule's `noncontiguous`): Hawaii, Puerto
        Rico and the Virgin Islands have no road or track to the mainland, and Alaska is reached
        by road only through Canada and not at all by rail."""
        return self.coast_region == "noncontiguous"

    def label(self) -> str:
        return f"{self.name} [{self.node_id}]" if self.name else self.node_id


@dataclass(frozen=True)
class NodePair:
    origin: Node
    destination: Node


def connect_core(settings: Settings) -> psycopg.Connection:
    """A read-only connection as the transform login (`DBT_DATABASE_URL`)."""
    if settings.dbt_database_url is None:
        raise ValueError("DBT_DATABASE_URL is not set; the distance generators read core")
    conn = psycopg.connect(settings.dbt_database_url.get_secret_value())
    conn.read_only = True
    return conn


_SHARED_ORIGIN = """
    with weights as (
        select distinct w.node_id, w.census_cty_code, w.mode, n.kind
        from core.fct_node_weights_monthly as w
        join core.dim_nodes as n using (node_id)
    ),
    pairs as (
        select distinct a.node_id as origin_id, b.node_id as destination_id
        from weights as a
        join weights as b using (census_cty_code)
        where a.kind = any(%(origin_kinds)s) and a.mode = any(%(origin_modes)s)
          and b.kind = any(%(destination_kinds)s) and b.mode = any(%(destination_modes)s)
    )
    select o.node_id, o.lat, o.lon, o.name, o.coast_region,
           d.node_id, d.lat, d.lon, d.name, d.coast_region
    from pairs
    join core.dim_nodes as o on o.node_id = pairs.origin_id
    join core.dim_nodes as d on d.node_id = pairs.destination_id
    order by 1, 4
"""


def shared_origin_pairs(
    conn: psycopg.Connection,
    origin_kinds: list[str],
    origin_modes: list[str],
    destination_kinds: list[str],
    destination_modes: list[str],
) -> list[NodePair]:
    """Pairs of an origin-kind node and a destination-kind node that carry freight, in the given
    modes, from at least one common origin country."""
    rows = conn.execute(
        _SHARED_ORIGIN,
        {
            "origin_kinds": origin_kinds,
            "origin_modes": origin_modes,
            "destination_kinds": destination_kinds,
            "destination_modes": destination_modes,
        },
    ).fetchall()
    return [NodePair(Node(*row[:5]), Node(*row[5:])) for row in rows]


def plant_crossing_pairs(conn: psycopg.Connection) -> list[NodePair]:
    """Each Mexican plant and the crossing whose leg starts at it (`map_crossing_plant`)."""
    rows = conn.execute(
        """
        select distinct p.node_id, p.lat, p.lon, p.name, p.coast_region,
               c.node_id, c.lat, c.lon, c.name, c.coast_region
        from core.map_crossing_plant as m
        join core.dim_nodes as p on p.node_id = 'mexico_plant:' || m.plant_id
        join core.dim_nodes as c on c.node_id = 'border_crossing:' || m.port_code
        order by 1, 4
        """
    ).fetchall()
    return [NodePair(Node(*row[:5]), Node(*row[5:])) for row in rows]


def report_unmeasured(pairs: Sequence[NodePair], measure: str) -> list[str]:
    """What to make of the pairs a generator couldn't measure, as lines to print. Pairs with an end
    outside the contiguous US are expected and counted by place; pairs within the contiguous US
    should always have a `measure`, so each is listed for action."""
    if not pairs:
        return [f"Every pair has a {measure}."]
    offshore = [p for p in pairs if p.origin.offshore or p.destination.offshore]
    mainland = [p for p in pairs if not (p.origin.offshore or p.destination.offshore)]
    lines = [f"No {measure} for {len(pairs):,} pairs."]
    if offshore:
        ends = [node for pair in offshore for node in (pair.origin, pair.destination)]
        counts = Counter(node.label() for node in ends if node.offshore)
        lines.append(
            f"  {len(offshore):,} have an end in Alaska, Hawaii, Puerto Rico or the Virgin "
            "Islands, which the road and rail networks reach poorly or not at all. Expected; "
            "no action. By place:"
        )
        lines += [f"    {label}: {n} pairs" for label, n in counts.most_common()]
    if mainland:
        lines.append(
            f"  {len(mainland):,} are within the contiguous US and should have a {measure}. "
            "Act on these: the node's point in core.dim_nodes is probably off the network."
        )
        lines += [f"    {p.origin.label()} -> {p.destination.label()}" for p in mainland]
    else:
        lines.append("  None is within the contiguous US, so nothing needs action.")
    return lines
