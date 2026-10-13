"""Air distances between departure airports and US air gateways: the geodesic on the WGS84
ellipsoid from `geographiclib`, with no uplift, since the UK air factors already include the 8%
DESNZ adds for indirect flight paths and circling (plan question 12)."""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from geographiclib.geodesic import Geodesic

from shockt.reference.node_pairs import NodePair

COLUMNS = ("from_node_id", "to_node_id", "km", "source")


@dataclass(frozen=True)
class AirDistance:
    from_node_id: str
    to_node_id: str
    km: float


def measure(pairs: Sequence[NodePair]) -> list[AirDistance]:
    rows = []
    for pair in pairs:
        line = Geodesic.WGS84.Inverse(
            pair.origin.lat, pair.origin.lon, pair.destination.lat, pair.destination.lon
        )
        rows.append(AirDistance(pair.origin.node_id, pair.destination.node_id, line["s12"] / 1000))
    return rows


def write_seed(rows: Sequence[AirDistance], path: Path) -> None:
    source = f"geodesic, WGS84, geographiclib {version('geographiclib')}"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow([r.from_node_id, r.to_node_id, f"{r.km:.1f}", source])
