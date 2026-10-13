"""Sea distances between departure ports and US arrival seaports, for every scenario in
`distances.sea.scenarios` (config/sources.yaml), measured by `searoute` on its maritime network.

Each scenario closes the passages it names. The `open` distances are the fallback where a port has
no observed voyages (`agg_observed_sea_distances_monthly`); the others are the counterfactual
distances with a passage closed. Each row records the passages the route crosses and the
`searoute` version.
"""

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import searoute
from searoute.classes.passages import Passage

from shockt.reference.node_pairs import NodePair

COLUMNS = ("from_node_id", "to_node_id", "scenario", "km", "passages", "source")
Router = Callable[..., Mapping[str, object]]


class SeaDistanceError(Exception):
    """A scenario names a passage `searoute` doesn't have."""


@dataclass(frozen=True)
class SeaDistance:
    from_node_id: str
    to_node_id: str
    scenario: str
    km: float
    passages: tuple[str, ...]


def known_passages() -> set[str]:
    """Passage names `searoute` can close."""
    return {
        value
        for key, value in vars(Passage).items()
        if not key.startswith("_") and isinstance(value, str)
    }


def check_scenarios(scenarios: Mapping[str, Sequence[str]], passages: set[str]) -> None:
    unknown = sorted({p for closed in scenarios.values() for p in closed} - passages)
    if unknown:
        raise SeaDistanceError(
            f"searoute has no passage named {unknown}; it has {sorted(passages)}"
        )


def measure(
    pairs: Sequence[NodePair],
    scenarios: Mapping[str, Sequence[str]],
    route: Router = searoute.searoute,
) -> list[SeaDistance]:
    """The route length and passages crossed for every pair under every scenario."""
    rows = []
    for pair in pairs:
        for scenario, closed in scenarios.items():
            feature = route(
                [pair.origin.lon, pair.origin.lat],
                [pair.destination.lon, pair.destination.lat],
                units="km",
                restrictions=list(closed),
                return_passages=True,
            )
            properties = feature["properties"]
            if not isinstance(properties, Mapping):
                raise SeaDistanceError(f"searoute returned no properties for {pair}")
            rows.append(
                SeaDistance(
                    pair.origin.node_id,
                    pair.destination.node_id,
                    scenario,
                    float(properties["length"]),
                    tuple(sorted(properties.get("traversed_passages") or ())),
                )
            )
    return rows


def write_seed(rows: Sequence[SeaDistance], path: Path) -> None:
    source = f"searoute {version('searoute')}"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    r.from_node_id,
                    r.to_node_id,
                    r.scenario,
                    f"{r.km:.1f}",
                    "|".join(r.passages),
                    source,
                ]
            )
