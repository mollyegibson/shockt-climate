import csv
import gzip
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from shockt.config import RailDistancesConfig, RoadDistancesConfig
from shockt.reference import (
    air_distances,
    node_pairs,
    rail_distances,
    road_distances,
    sea_distances,
)
from shockt.reference.node_pairs import Node, NodePair

KAOHSIUNG = Node("departure_port:TWN_1", 22.57, 120.31)
SAVANNAH = Node("arrival_seaport:1703", 32.08, -81.09)
NOW = datetime(2026, 10, 13, tzinfo=UTC)


def read_seed(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_sea_scenarios_must_name_passages_searoute_has() -> None:
    with pytest.raises(sea_distances.SeaDistanceError, match="panamaa"):
        sea_distances.check_scenarios({"closed": ["panamaa"]}, sea_distances.known_passages())


def test_known_passages_come_from_searoute() -> None:
    assert {"panama", "babalmandab", "northwest"} <= sea_distances.known_passages()


def test_sea_distances_measure_every_pair_under_every_scenario(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def route(
        origin: list[float], destination: list[float], **kwargs: object
    ) -> Mapping[str, object]:
        restrictions = kwargs["restrictions"]
        assert isinstance(restrictions, list)
        calls.append(restrictions)
        closed = "panama" in restrictions
        return {
            "properties": {
                "length": 22876.3 if closed else 19812.7,
                "traversed_passages": ["suez", "malacca"] if closed else ["panama"],
            }
        }

    scenarios = {"open": ["northwest"], "panama_closed": ["northwest", "panama"]}
    rows = sea_distances.measure([NodePair(KAOHSIUNG, SAVANNAH)], scenarios, route)
    sea_distances.write_seed(rows, tmp_path / "seed.csv")

    assert calls == [["northwest"], ["northwest", "panama"]]
    seed = read_seed(tmp_path / "seed.csv")
    assert [(r["scenario"], r["km"], r["passages"]) for r in seed] == [
        ("open", "19812.7", "panama"),
        ("panama_closed", "22876.3", "malacca|suez"),
    ]
    assert seed[0]["source"].startswith("searoute ")


def test_air_distance_is_the_wgs84_geodesic(tmp_path: Path) -> None:
    pair = NodePair(Node("departure_airport:A", 0.0, 0.0), Node("air_gateway:B", 0.0, 1.0))

    rows = air_distances.measure([pair])
    air_distances.write_seed(rows, tmp_path / "seed.csv")

    assert rows[0].km == pytest.approx(111.3195, abs=1e-3)
    assert read_seed(tmp_path / "seed.csv")[0]["km"] == "111.3"


def nodes(prefix: str, count: int) -> list[Node]:
    return [Node(f"{prefix}:{i}", 30.0 + i, -100.0 - i) for i in range(count)]


def test_road_requests_cover_the_grid_within_the_cell_limit() -> None:
    origins, states = nodes("border_crossing", 5), nodes("destination_state", 3)
    pairs = [NodePair(o, s) for o in origins for s in states[:2]] + [
        NodePair(origins[0], states[2])
    ]

    requests = road_distances.plan_requests(pairs, max_cells=7)

    assert [len(r.origins) for r in requests] == [2, 2, 1]
    assert all(r.destinations == tuple(states) for r in requests)
    body = requests[0].body()
    assert body["sources"] == [0, 1]
    assert body["destinations"] == [2, 3, 4]


ROAD = RoadDistancesConfig(matrix_url="https://example.invalid/matrix", max_cells_per_request=10)
ENGINE = {"version": "9.10.0", "graph_date": "2026-09-23", "osm_date": "2026-09-13"}


def matrix_response(distances: list[list[float | None]]) -> dict[str, object]:
    return {
        "distances": distances,
        "durations": [[None if d is None else d * 40 for d in row] for row in distances],
        "metadata": {"engine": ENGINE},
    }


@respx.mock
def test_road_bundle_parses_distances_and_lists_pairs_without_a_route() -> None:
    crossing, other = (
        Node("border_crossing:2304", 27.5, -99.5),
        Node("border_crossing:2401", 31.7, -106.3),
    )
    texas, virginia = (
        Node("destination_state:TX", 31.0, -97.5),
        Node("destination_state:VA", 37.8, -77.3),
    )
    pairs = [NodePair(crossing, texas), NodePair(crossing, virginia), NodePair(other, texas)]
    requests = road_distances.plan_requests(pairs, ROAD.max_cells_per_request)
    route = respx.post(ROAD.matrix_url).mock(
        return_value=httpx.Response(
            200,
            json=matrix_response([[494.0, 2818.0], [None, 3233.0]]),
            headers={"x-ratelimit-remaining": "40"},
        )
    )

    with httpx.Client() as client:
        bundle = road_distances.fetch_bundle(client, ROAD, "secret-key", requests, lambda: NOW)
    rows, missing = road_distances.parse_bundle(bundle, pairs, requests)

    assert route.calls.last.request.headers["Authorization"] == "secret-key"
    assert b"secret-key" not in bundle
    assert [(r.from_node_id, r.to_node_id, r.km, r.osm_date) for r in rows] == [
        ("border_crossing:2304", "destination_state:TX", 494.0, "2026-09-13"),
        ("border_crossing:2304", "destination_state:VA", 2818.0, "2026-09-13"),
    ]
    assert missing == [NodePair(other, texas)]


@respx.mock
def test_road_fetch_stops_before_the_quota_runs_out() -> None:
    pairs = [
        NodePair(o, s) for o in nodes("arrival_seaport", 4) for s in nodes("destination_state", 5)
    ]
    requests = road_distances.plan_requests(pairs, max_cells=10)
    respx.post(ROAD.matrix_url).mock(
        return_value=httpx.Response(
            200, json=matrix_response([[1.0] * 5] * 2), headers={"x-ratelimit-remaining": "0"}
        )
    )

    with httpx.Client() as client, pytest.raises(road_distances.RoadDistanceError, match="quota"):
        road_distances.fetch_bundle(client, ROAD, "key", requests, lambda: NOW)


def test_road_bundle_must_match_the_requests() -> None:
    pairs = [NodePair(nodes("air_gateway", 1)[0], nodes("destination_state", 1)[0])]
    requests = road_distances.plan_requests(pairs, max_cells=10)
    bundle = json.dumps(
        {"exchanges": [{"request": {"locations": []}, "response": matrix_response([[1.0]])}]}
    ).encode()

    with pytest.raises(road_distances.RoadDistanceError, match="don't match"):
        road_distances.parse_bundle(bundle, pairs, requests)


RAIL = RailDistancesConfig(
    lines_url="https://example.invalid/lines",
    nodes_url="https://example.invalid/nodes",
    track_classes=["M"],
    page_size=100,
    max_snap_km=50,
)


def line(object_id: int, a: int, b: int, km: float, net: str = "M") -> dict[str, object]:
    return {
        "attributes": {"OBJECTID": object_id, "FRFRANODE": a, "TOFRANODE": b, "KM": km, "NET": net}
    }


def rail_node(object_id: int, node_id: int, lat: float, lon: float) -> dict[str, object]:
    return {
        "attributes": {"OBJECTID": object_id, "FRANODEID": node_id},
        "geometry": {"x": lon, "y": lat},
    }


def mock_layer(url: str, features: list[dict[str, object]]) -> None:
    respx.get(url, params={"f": "json"}).mock(
        return_value=httpx.Response(200, json={"editingInfo": {"dataLastEditDate": 1784743420808}})
    )
    respx.get(f"{url}/query").mock(
        side_effect=[
            httpx.Response(200, json={"features": features}),
            httpx.Response(200, json={"features": []}),
        ]
    )


@respx.mock
def test_rail_network_keeps_the_track_classes_and_its_largest_connected_part() -> None:
    mock_layer(
        RAIL.lines_url,
        [
            line(1, 10, 11, 100.0),
            line(2, 11, 12, 100.0),
            line(3, 10, 12, 500.0),
            line(4, 12, 13, 1.0, net="A"),
            line(5, 20, 21, 5.0),
        ],
    )
    mock_layer(
        RAIL.nodes_url,
        [
            rail_node(1, 10, 27.5, -99.5),
            rail_node(2, 11, 29.0, -98.0),
            rail_node(3, 12, 31.0, -97.5),
            rail_node(4, 13, 31.1, -97.4),
            rail_node(5, 20, 40.0, -80.0),
            rail_node(6, 21, 40.1, -80.1),
        ],
    )

    with httpx.Client() as client:
        bundle = rail_distances.fetch_bundle(client, RAIL, lambda: NOW)
    network = rail_distances.parse_bundle(bundle, RAIL.track_classes)
    crossing = Node("border_crossing:2304", 27.5, -99.5)
    texas = Node("destination_state:TX", 31.0, -97.5)
    nevada = Node("destination_state:NV", 39.0, -117.0)
    rows, too_far = rail_distances.measure(
        network, [NodePair(crossing, texas), NodePair(crossing, nevada)], RAIL.max_snap_km
    )

    assert sorted(network.graph.nodes) == [10, 11, 12]
    assert json.loads(gzip.decompress(bundle))["fetched_at"] == "2026-10-13T00:00:00+00:00"
    assert network.version == "lines edited 2026-07-22, nodes edited 2026-07-22"
    assert [(r.to_node_id, r.km, r.from_snap_km, r.to_snap_km) for r in rows] == [
        ("destination_state:TX", 200.0, 0.0, 0.0)
    ]
    assert too_far == [NodePair(crossing, nevada)]


def test_unmeasured_pairs_offshore_are_expected_and_mainland_ones_are_listed() -> None:
    hawaii = Node("destination_state:HI", 21.3, -157.8, "HI (Honolulu)", "noncontiguous")
    san_juan = Node("arrival_seaport:4909", 18.4, -66.1, "SAN JUAN, PR", "noncontiguous")
    seattle = Node("arrival_seaport:3001", 47.6, -122.3, "SEATTLE, WA", "west")
    nevada = Node("destination_state:NV", 36.2, -115.9, "NV (Pahrump)", "west")
    pairs = [NodePair(seattle, hawaii), NodePair(san_juan, nevada), NodePair(seattle, nevada)]

    lines = node_pairs.report_unmeasured(pairs, "road route")

    assert lines[0] == "No road route for 3 pairs."
    assert "2 have an end in Alaska, Hawaii" in lines[1]
    assert set(lines[2:4]) == {
        "    HI (Honolulu) [destination_state:HI]: 1 pairs",
        "    SAN JUAN, PR [arrival_seaport:4909]: 1 pairs",
    }
    assert "1 are within the contiguous US" in lines[4]
    assert lines[5] == (
        "    SEATTLE, WA [arrival_seaport:3001] -> NV (Pahrump) [destination_state:NV]"
    )


def test_unmeasured_pairs_all_offshore_need_no_action() -> None:
    alaska = Node("destination_state:AK", 61.2, -149.9, None, "noncontiguous")
    port = Node("arrival_seaport:2704", 34.1, -118.2, None, "west")

    lines = node_pairs.report_unmeasured([NodePair(port, alaska)], "road route")

    assert lines[-1] == "  None is within the contiguous US, so nothing needs action."
