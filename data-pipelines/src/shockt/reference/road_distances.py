"""Road distances by heavy goods vehicle from the openrouteservice matrix endpoint, between node
pairs on truck legs: each Mexican plant and its crossing, and each crossing, arrival seaport or air
gateway and the destination states its freight goes to.

Each family of pairs is requested as a grid of at most `max_cells_per_request` origins ×
destinations per request. Every
request and response is archived as one JSON bundle, and the seed is parsed from that bundle. Each
row carries the OpenStreetMap date the route was computed on, from the response's
`metadata.engine`. The rate-limit headers are checked after each request, and the run stops before
it would exceed the remaining quota.
"""

import csv
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from shockt import http
from shockt.config import RoadDistancesConfig
from shockt.reference.node_pairs import Node, NodePair

DATASET = "reference_road_distances"
COLUMNS = (
    "from_node_id",
    "to_node_id",
    "km",
    "duration_h",
    "osm_date",
    "graph_date",
    "engine_version",
    "source",
)


class RoadDistanceError(Exception):
    """A matrix response was malformed, or the quota would run out."""


@dataclass(frozen=True)
class MatrixRequest:
    origins: tuple[Node, ...]
    destinations: tuple[Node, ...]

    def body(self) -> dict[str, object]:
        locations = [[n.lon, n.lat] for n in (*self.origins, *self.destinations)]
        return {
            "locations": locations,
            "sources": list(range(len(self.origins))),
            "destinations": list(range(len(self.origins), len(locations))),
            "metrics": ["distance", "duration"],
            "units": "km",
        }


@dataclass(frozen=True)
class RoadDistance:
    from_node_id: str
    to_node_id: str
    km: float
    duration_h: float | None
    osm_date: str
    graph_date: str
    engine_version: str


def plan_requests(pairs: Sequence[NodePair], max_cells: int) -> list[MatrixRequest]:
    """Requests covering every pair: the grid of all the pairs' origins × all their destinations,
    with the origins split so each request stays within `max_cells`. The grid has cells no pair
    needs; that costs nothing, while a request per origin would use far more of the quota."""
    origins = sorted({p.origin for p in pairs}, key=lambda n: n.node_id)
    destinations = tuple(sorted({p.destination for p in pairs}, key=lambda n: n.node_id))
    if not destinations:
        return []
    if len(destinations) > max_cells:
        raise RoadDistanceError(f"{len(destinations)} destinations exceed {max_cells} cells")
    per_request = max_cells // len(destinations)
    return [
        MatrixRequest(tuple(origins[start : start + per_request]), destinations)
        for start in range(0, len(origins), per_request)
    ]


def fetch_bundle(
    client: httpx.Client,
    config: RoadDistancesConfig,
    api_key: str,
    requests: Sequence[MatrixRequest],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> bytes:
    """Send every request and return them with their responses as one JSON bundle."""
    exchanges = []
    for index, request in enumerate(requests):
        response = http.post_json(
            client,
            config.matrix_url,
            request.body(),
            headers={"Authorization": api_key},
            secrets=(api_key,),
        )
        exchanges.append({"request": request.body(), "response": response.json()})
        remaining = response.headers.get("x-ratelimit-remaining")
        still_to_send = len(requests) - index - 1
        if remaining is not None and int(remaining) < still_to_send:
            raise RoadDistanceError(
                f"openrouteservice quota has {remaining} requests left, "
                f"{still_to_send} still needed"
            )
    bundle = {
        "url": config.matrix_url,
        "fetched_at": now().isoformat(timespec="seconds"),
        "exchanges": exchanges,
    }
    return json.dumps(bundle).encode()


def parse_bundle(
    bundle: bytes, pairs: Sequence[NodePair], requests: Sequence[MatrixRequest]
) -> tuple[list[RoadDistance], list[NodePair]]:
    """Distances for `pairs` from an archived bundle of `requests`, and the pairs with no route."""
    exchanges = json.loads(bundle)["exchanges"]
    if len(exchanges) != len(requests):
        raise RoadDistanceError(
            f"bundle has {len(exchanges)} responses for {len(requests)} requests"
        )
    found: dict[tuple[str, str], RoadDistance] = {}
    for request, exchange in zip(requests, exchanges, strict=True):
        if exchange["request"] != request.body():
            raise RoadDistanceError("bundle's requests don't match the node pairs")
        response = exchange["response"]
        if "error" in response:
            raise RoadDistanceError(f"openrouteservice error: {response['error']}")
        engine = response["metadata"]["engine"]
        for i, origin in enumerate(request.origins):
            for j, destination in enumerate(request.destinations):
                km = response["distances"][i][j]
                if km is None:
                    continue
                seconds = response["durations"][i][j]
                found[(origin.node_id, destination.node_id)] = RoadDistance(
                    origin.node_id,
                    destination.node_id,
                    float(km),
                    None if seconds is None else float(seconds) / 3600,
                    engine["osm_date"],
                    engine["graph_date"],
                    engine["version"],
                )
    rows, missing = [], []
    for pair in pairs:
        row = found.get((pair.origin.node_id, pair.destination.node_id))
        if row is None:
            missing.append(pair)
        else:
            rows.append(row)
    return rows, missing


def write_seed(rows: Sequence[RoadDistance], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    r.from_node_id,
                    r.to_node_id,
                    f"{r.km:.1f}",
                    "" if r.duration_h is None else f"{r.duration_h:.2f}",
                    r.osm_date,
                    r.graph_date,
                    r.engine_version,
                    "openrouteservice driving-hgv",
                ]
            )
