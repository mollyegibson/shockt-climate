"""Rail distances along the shortest track of the BTS North American Rail Network, between node
pairs on rail legs: each crossing with rail freight and each arrival seaport, and the destination
states their freight goes to.

The network's lines and nodes are fetched from their ArcGIS FeatureServer layers page by page,
archived as one gzipped JSON bundle, and parsed from it. Lines are kept when their `NET` code is
in `track_classes`; each line joins its from and to rail nodes, weighted by its length in km. Only
the largest connected part of the network is used. Each node of a pair snaps to the nearest rail
node; a pair whose end is farther than `max_snap_km` from track gets no rail distance. Shortest
track is not necessarily the route a railroad runs (plan section 6.3).
"""

import csv
import gzip
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import networkx as nx
from geographiclib.geodesic import Geodesic

from shockt import http
from shockt.config import RailDistancesConfig
from shockt.reference.node_pairs import Node, NodePair

DATASET = "reference_rail_network"
COLUMNS = (
    "from_node_id",
    "to_node_id",
    "km",
    "from_snap_km",
    "to_snap_km",
    "network_version",
    "source",
)
LINE_FIELDS = ("OBJECTID", "FRFRANODE", "TOFRANODE", "KM", "NET")
NODE_FIELDS = ("OBJECTID", "FRANODEID")


class RailDistanceError(Exception):
    """The rail network layers didn't parse into a usable network."""


@dataclass(frozen=True)
class RailNetwork:
    graph: nx.Graph
    coordinates: dict[int, tuple[float, float]]
    """Rail node id → (lat, lon), for the nodes in the graph."""
    version: str


@dataclass(frozen=True)
class RailDistance:
    from_node_id: str
    to_node_id: str
    km: float
    from_snap_km: float
    to_snap_km: float
    network_version: str


def _layer(
    client: httpx.Client, url: str, fields: Sequence[str], page_size: int, geometry: bool
) -> dict[str, object]:
    """Every feature of one layer, paged by OBJECTID, with the layer's last-edited time."""
    info = http.get(client, url, {"f": "json"}).json()
    edited = info.get("editingInfo", {}).get("dataLastEditDate")
    if edited is None:
        raise RailDistanceError(f"layer {url} reports no dataLastEditDate")
    pages = []
    last = 0
    while True:
        params = {
            "where": f"OBJECTID > {last}",
            "outFields": ",".join(fields),
            "orderByFields": "OBJECTID",
            "resultRecordCount": str(page_size),
            "returnGeometry": "true" if geometry else "false",
            "f": "json",
        }
        if geometry:
            params["outSR"] = "4326"
        page = http.get(client, f"{url}/query", params).json()
        if "error" in page:
            raise RailDistanceError(f"ArcGIS error from {url}: {page['error']}")
        features = page.get("features", [])
        if not features:
            break
        pages.append(page)
        last = features[-1]["attributes"]["OBJECTID"]
    return {"url": url, "data_last_edited": edited, "pages": pages}


def fetch_bundle(
    client: httpx.Client,
    config: RailDistancesConfig,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> bytes:
    """Every line and node of the network, with each layer's last-edited time, gzipped."""
    bundle = {
        "fetched_at": now().isoformat(timespec="seconds"),
        "lines": _layer(client, config.lines_url, LINE_FIELDS, config.page_size, geometry=False),
        "nodes": _layer(client, config.nodes_url, NODE_FIELDS, config.page_size, geometry=True),
    }
    return gzip.compress(json.dumps(bundle).encode())


def _edited(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).date().isoformat()


def parse_bundle(bundle: bytes, track_classes: Sequence[str]) -> RailNetwork:
    """The largest connected network of the kept track classes, from an archived bundle."""
    data = json.loads(gzip.decompress(bundle))
    classes = set(track_classes)
    graph = nx.Graph()
    for page in data["lines"]["pages"]:
        for feature in page["features"]:
            a = feature["attributes"]
            if a["NET"] not in classes:
                continue
            u, v, km = int(a["FRFRANODE"]), int(a["TOFRANODE"]), float(a["KM"])
            if graph.has_edge(u, v) and graph[u][v]["km"] <= km:
                continue
            graph.add_edge(u, v, km=km)
    if graph.number_of_nodes() == 0:
        raise RailDistanceError(f"no lines in track classes {sorted(classes)}")
    largest = max(nx.connected_components(graph), key=len)
    graph = graph.subgraph(largest).copy()
    coordinates: dict[int, tuple[float, float]] = {}
    for page in data["nodes"]["pages"]:
        for feature in page["features"]:
            node = int(feature["attributes"]["FRANODEID"])
            if node in graph:
                coordinates[node] = (feature["geometry"]["y"], feature["geometry"]["x"])
    missing = graph.number_of_nodes() - len(coordinates)
    if missing:
        raise RailDistanceError(f"{missing} rail nodes on kept lines have no coordinates")
    version = (
        f"lines edited {_edited(data['lines']['data_last_edited'])}, "
        f"nodes edited {_edited(data['nodes']['data_last_edited'])}"
    )
    return RailNetwork(graph, coordinates, version)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return float(Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)["s12"]) / 1000


def snap(network: RailNetwork, node: Node) -> tuple[int, float]:
    """The nearest rail node to `node` and its distance in km. Candidates are ranked by a flat-earth
    distance, which orders nearby points correctly; the chosen one is measured on the ellipsoid."""
    scale = math.cos(math.radians(node.lat)) ** 2
    nearest = min(
        network.coordinates.items(),
        key=lambda item: (item[1][0] - node.lat) ** 2 + scale * (item[1][1] - node.lon) ** 2,
    )
    rail_node, (lat, lon) = nearest
    return rail_node, _km(node.lat, node.lon, lat, lon)


def measure(
    network: RailNetwork, pairs: Sequence[NodePair], max_snap_km: float
) -> tuple[list[RailDistance], list[NodePair]]:
    """Shortest track for each pair, and the pairs left out for an end too far from track."""
    snapped = {
        node.node_id: snap(network, node)
        for pair in pairs
        for node in (pair.origin, pair.destination)
    }
    by_origin: dict[str, list[NodePair]] = {}
    for pair in pairs:
        by_origin.setdefault(pair.origin.node_id, []).append(pair)
    rows, too_far = [], []
    for origin_id, origin_pairs in by_origin.items():
        origin_rail, origin_snap = snapped[origin_id]
        if origin_snap > max_snap_km:
            too_far.extend(origin_pairs)
            continue
        lengths = nx.single_source_dijkstra_path_length(network.graph, origin_rail, weight="km")
        for pair in origin_pairs:
            rail_node, destination_snap = snapped[pair.destination.node_id]
            if destination_snap > max_snap_km or rail_node not in lengths:
                too_far.append(pair)
                continue
            rows.append(
                RailDistance(
                    origin_id,
                    pair.destination.node_id,
                    lengths[rail_node],
                    origin_snap,
                    destination_snap,
                    network.version,
                )
            )
    return rows, too_far


def write_seed(rows: Sequence[RailDistance], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    r.from_node_id,
                    r.to_node_id,
                    f"{r.km:.1f}",
                    f"{r.from_snap_km:.1f}",
                    f"{r.to_snap_km:.1f}",
                    r.network_version,
                    "BTS North American Rail Network, shortest track",
                ]
            )
