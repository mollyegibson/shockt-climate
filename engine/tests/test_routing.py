import pytest

from shockt_engine import (
    EdgeDistance,
    Factor,
    FeederEdge,
    Node,
    RouteDistances,
    RouteOptions,
    deduplicate_port_clusters,
    enumerate_routes,
    load_leg_factors,
)


def _factor(
    variant: str,
    mode: str,
    source: str = "uk_desnz",
    *,
    vehicle_type: str | None = None,
    size_class: str | None = None,
    haul: str | None = None,
    radiative_forcing: bool | None = None,
    ttw: float = 0.01,
    wtt: float = 0.005,
) -> Factor:
    return Factor(
        source=source,
        source_row_id=variant,
        mode=mode,
        variant=variant,
        vehicle_type=vehicle_type,
        size_class=size_class,
        haul=haul,
        radiative_forcing=radiative_forcing,
        ttw_kg_co2e_per_tkm=ttw,
        wtt_kg_co2e_per_tkm=wtt,
        wtw_kg_co2e_per_tkm=ttw + wtt,
    )


FACTORS = [
    _factor(
        "Container ship / Average",
        "ocean",
        vehicle_type="container_ship",
        size_class="average",
        ttw=0.0131,
        wtt=0.0027,
    ),
    _factor(
        "Freight flights / International / With RF",
        "air",
        vehicle_type="freight_flight",
        haul="international",
        radiative_forcing=True,
        ttw=0.4927,
        wtt=0.1094,
    ),
    _factor(
        "Medium- and Heavy-Duty Truck",
        "truck",
        source="epa_hub",
        vehicle_type="medium_heavy_duty_truck",
        ttw=0.0892,
        wtt=0.0181,
    ),
    _factor(
        "Rail",
        "rail",
        source="epa_hub",
        vehicle_type="rail",
        ttw=0.0245,
        wtt=0.0033,
    ),
]

CHOICES = load_leg_factors()

NODES: dict[str, Node] = {
    "departure_port:BGD_CTG": Node("departure_port", "Chittagong", "BGD", 22.33, 91.80, "BGD_CTG"),
    "departure_port:CHN_SHA": Node("departure_port", "Shanghai", "CHN", 31.23, 121.47, "CHN_SHA"),
    "departure_port:SGP_SIN": Node("departure_port", "Singapore", "SGP", 1.26, 103.84, "SGP_SIN"),
    "arrival_seaport:LA": Node("arrival_seaport", "Los Angeles", "USA", 33.74, -118.27, "LA"),
    "arrival_seaport:NY": Node("arrival_seaport", "New York", "USA", 40.68, -74.04, "NY"),
    "departure_airport:BGD_DAC": Node("departure_airport", "Dhaka", "BGD", 23.84, 90.40, "BGD_DAC"),
    "air_gateway:LAX": Node("air_gateway", "LAX", "USA", 33.94, -118.41, "LAX"),
    "destination_state:TX": Node("destination_state", "Texas (Waco)", "USA", 31.55, -97.15, "TX"),
    "destination_state:CA": Node(
        "destination_state", "California (LA)", "USA", 34.05, -118.24, "CA"
    ),
    "mexico_plant:P1": Node("mexico_plant", "Factory A", "MEX", 25.67, -100.31, "1"),
    "border_crossing:LRD": Node("border_crossing", "Laredo", "USA", 27.50, -99.51, "LRD"),
}

SEA_DISTANCES: dict[tuple[str, str], dict[str, EdgeDistance]] = {
    ("departure_port:CHN_SHA", "arrival_seaport:LA"): {
        "open": EdgeDistance(km=11000.0, duration_h=None, passages=("panama",)),
        "panama_closed": EdgeDistance(km=14000.0, duration_h=None, passages=()),
    },
    ("departure_port:CHN_SHA", "arrival_seaport:NY"): {
        "open": EdgeDistance(km=19000.0, duration_h=None, passages=("panama",)),
    },
    ("departure_port:SGP_SIN", "arrival_seaport:LA"): {
        "open": EdgeDistance(km=14500.0, duration_h=None, passages=()),
    },
    ("departure_port:SGP_SIN", "arrival_seaport:NY"): {
        "open": EdgeDistance(km=15500.0, duration_h=None, passages=("babalmandab", "suez")),
        "red_sea_closed": EdgeDistance(km=21000.0, duration_h=None, passages=("south_africa",)),
    },
}

DISTANCES = RouteDistances(
    sea=SEA_DISTANCES,
    air={
        ("departure_airport:BGD_DAC", "air_gateway:LAX"): EdgeDistance(km=13500.0, duration_h=None),
    },
    road={
        ("arrival_seaport:LA", "destination_state:TX"): EdgeDistance(km=2200.0, duration_h=22.5),
        ("arrival_seaport:LA", "destination_state:CA"): EdgeDistance(km=50.0, duration_h=0.8),
        ("arrival_seaport:NY", "destination_state:TX"): EdgeDistance(km=2700.0, duration_h=27.0),
        ("air_gateway:LAX", "destination_state:TX"): EdgeDistance(km=2200.0, duration_h=22.5),
        ("air_gateway:LAX", "destination_state:CA"): EdgeDistance(km=50.0, duration_h=0.8),
        ("mexico_plant:P1", "border_crossing:LRD"): EdgeDistance(km=300.0, duration_h=4.5),
        ("border_crossing:LRD", "destination_state:TX"): EdgeDistance(km=500.0, duration_h=6.0),
    },
    rail={
        ("arrival_seaport:LA", "destination_state:TX"): EdgeDistance(km=2400.0, duration_h=None),
        ("border_crossing:LRD", "destination_state:TX"): EdgeDistance(km=550.0, duration_h=None),
    },
    feeder={
        ("departure_port:BGD_CTG", "departure_port:SGP_SIN"): FeederEdge(
            km=3200.0, duration_h=138.0, hub_has_us_voyages=True
        ),
    },
)


def test_direct_vessel_route_scores_correctly() -> None:
    """Shanghai → LA → TX via open scenario."""
    routes = enumerate_routes("CHN", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    vessel = [r for r in routes if r.mode == "vessel"]
    sha_la = [
        r
        for r in vessel
        if r.legs[0].from_node == "departure_port:CHN_SHA"
        and r.legs[0].to_node == "arrival_seaport:LA"
    ]
    assert len(sha_la) == 1
    route = sha_la[0]

    assert len(route.legs) == 2
    ocean, inland = route.legs

    assert ocean.network == "sea"
    assert ocean.km == 11000.0
    assert ocean.ttw_kg_co2e_per_tkm == 0.0131
    assert ocean.wtt_kg_co2e_per_tkm == 0.0027
    assert ocean.passages == ("panama",)
    assert ocean.duration_h == pytest.approx(11000.0 / 23.15, rel=1e-4)

    assert inland.network == "road"
    assert inland.km == 2200.0
    assert inland.duration_h == 22.5

    expected_ttw = 11000.0 * 0.0131 + 2200.0 * 0.0892
    expected_wtt = 11000.0 * 0.0027 + 2200.0 * 0.0181
    assert route.total_ttw_kg_co2e_per_t == pytest.approx(expected_ttw, rel=1e-6)
    assert route.total_wtt_kg_co2e_per_t == pytest.approx(expected_wtt, rel=1e-6)
    assert route.total_wtw_kg_co2e_per_t == pytest.approx(expected_ttw + expected_wtt, rel=1e-6)
    assert route.passages == ("panama",)
    assert route.scenario == "open"


def test_feeder_route_through_hub() -> None:
    """Bangladesh → Singapore (feeder) → LA → TX."""
    routes = enumerate_routes("BGD", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    feeder_routes = [r for r in routes if r.mode == "vessel" and len(r.legs) == 3]
    assert len(feeder_routes) >= 1

    route = feeder_routes[0]
    feeder_leg, mainline_leg, inland_leg = route.legs

    assert feeder_leg.from_node == "departure_port:BGD_CTG"
    assert feeder_leg.to_node == "departure_port:SGP_SIN"
    assert feeder_leg.km == 3200.0
    assert feeder_leg.duration_h == 138.0
    assert feeder_leg.factor_mode == "ocean"
    assert feeder_leg.passages == ()

    assert mainline_leg.from_node == "departure_port:SGP_SIN"
    assert mainline_leg.factor_mode == "ocean"
    assert mainline_leg.passages in (("babalmandab", "suez"), ())


def test_air_route() -> None:
    """Dhaka → LAX → TX."""
    routes = enumerate_routes("BGD", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    air = [r for r in routes if r.mode == "air"]
    assert len(air) == 1
    route = air[0]

    assert len(route.legs) == 2
    flight, truck = route.legs

    assert flight.network == "air"
    assert flight.km == 13500.0
    assert flight.ttw_kg_co2e_per_tkm == 0.4927
    assert flight.duration_h == pytest.approx(13500.0 / 850.0, rel=1e-4)

    assert truck.network == "road"
    assert truck.km == 2200.0


def test_mexico_truck_route() -> None:
    """Mexico plant → Laredo → TX."""
    routes = enumerate_routes("MEX", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    truck = [r for r in routes if r.mode == "truck"]
    assert len(truck) == 1
    route = truck[0]

    assert len(route.legs) == 2
    plant_leg, cx_leg = route.legs

    assert plant_leg.from_node == "mexico_plant:P1"
    assert plant_leg.to_node == "border_crossing:LRD"
    assert plant_leg.km == 300.0

    assert cx_leg.from_node == "border_crossing:LRD"
    assert cx_leg.to_node == "destination_state:TX"
    assert cx_leg.km == 500.0


def test_mexico_rail_route() -> None:
    """Mexico plant → Laredo (truck) → TX (rail)."""
    routes = enumerate_routes(
        "MEX",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        options=RouteOptions(inland_mode="truck"),
    )

    rail = [r for r in routes if r.mode == "rail"]
    assert len(rail) == 1
    route = rail[0]

    plant_leg, cx_leg = route.legs
    assert plant_leg.network == "road"
    assert plant_leg.factor_mode == "truck"
    assert cx_leg.network == "rail"
    assert cx_leg.factor_mode == "rail"
    assert route.total_duration_h is None


def test_mode_filter() -> None:
    routes = enumerate_routes(
        "CHN",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        options=RouteOptions(modes=frozenset({"air"})),
    )
    assert all(r.mode == "air" for r in routes)


def test_scenario_changes_distances() -> None:
    """Panama closed reroutes Shanghai → LA."""
    open_routes = enumerate_routes("CHN", "TX", NODES, DISTANCES, FACTORS, CHOICES)
    closed_routes = enumerate_routes(
        "CHN",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        options=RouteOptions(scenario="panama_closed"),
    )

    sha_la_open = [
        r
        for r in open_routes
        if r.mode == "vessel"
        and r.legs[0].from_node == "departure_port:CHN_SHA"
        and r.legs[0].to_node == "arrival_seaport:LA"
    ]
    sha_la_closed = [
        r
        for r in closed_routes
        if r.mode == "vessel"
        and r.legs[0].from_node == "departure_port:CHN_SHA"
        and r.legs[0].to_node == "arrival_seaport:LA"
    ]

    assert len(sha_la_open) == 1
    assert len(sha_la_closed) == 1
    assert sha_la_open[0].legs[0].km == 11000.0
    assert sha_la_closed[0].legs[0].km == 14000.0
    assert sha_la_closed[0].total_wtw_kg_co2e_per_t > sha_la_open[0].total_wtw_kg_co2e_per_t


def test_routes_sorted_by_emissions() -> None:
    routes = enumerate_routes("CHN", "TX", NODES, DISTANCES, FACTORS, CHOICES)
    emissions = [r.total_wtw_kg_co2e_per_t for r in routes]
    assert emissions == sorted(emissions)


def test_total_duration_null_when_any_leg_null() -> None:
    """Vessel route with rail inland has null duration (rail duration is null)."""
    routes = enumerate_routes(
        "CHN",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        options=RouteOptions(inland_mode="rail"),
    )
    vessel = [r for r in routes if r.mode == "vessel"]
    assert len(vessel) > 0
    for r in vessel:
        assert r.legs[-1].duration_h is None
        assert r.total_duration_h is None


def test_cycle_prevention_skips_hub_equal_to_seaport() -> None:
    """A feeder route where hub == arrival_seaport would be a cycle — must be skipped."""
    routes = enumerate_routes("BGD", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    for r in routes:
        node_ids = [leg.from_node for leg in r.legs] + [r.legs[-1].to_node]
        assert len(node_ids) == len(set(node_ids)), f"cycle in {node_ids}"


def test_origin_node_filter() -> None:
    routes = enumerate_routes(
        "CHN",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        origin_node="departure_port:CHN_SHA",
    )
    for r in routes:
        if r.mode == "vessel":
            assert r.legs[0].from_node == "departure_port:CHN_SHA"


def test_hs6_filters_mexico_plants() -> None:
    crossing_plants = {"847150": {"border_crossing:LRD": "mexico_plant:P1"}}
    routes = enumerate_routes(
        "MEX",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        crossing_plants=crossing_plants,
        hs6="847150",
    )
    truck = [r for r in routes if r.mode == "truck"]
    assert len(truck) == 1
    assert truck[0].legs[0].from_node == "mexico_plant:P1"


def test_hs6_with_no_matching_plants_returns_empty() -> None:
    crossing_plants = {"999999": {"border_crossing:OTHER": "mexico_plant:OTHER"}}
    routes = enumerate_routes(
        "MEX",
        "TX",
        NODES,
        DISTANCES,
        FACTORS,
        CHOICES,
        crossing_plants=crossing_plants,
        hs6="999999",
    )
    truck = [r for r in routes if r.mode == "truck"]
    assert len(truck) == 0


def test_port_cluster_deduplication() -> None:
    close_nodes = {
        "departure_port:A": Node("departure_port", "Port A", "CHN", 31.23, 121.47, "A"),
        "departure_port:B": Node("departure_port", "Port B", "CHN", 31.231, 121.471, "B"),
        "departure_port:C": Node("departure_port", "Port C", "CHN", 25.0, 110.0, "C"),
    }
    voyages = {"departure_port:A": 100, "departure_port:B": 200, "departure_port:C": 50}
    result = deduplicate_port_clusters(
        close_nodes,
        ["departure_port:A", "departure_port:B", "departure_port:C"],
        voyages,
    )
    assert "departure_port:B" in result
    assert "departure_port:A" not in result
    assert "departure_port:C" in result
    assert len(result) == 2


def test_passage_union_across_legs() -> None:
    """A feeder route's passages are the union of its legs' passages."""
    routes = enumerate_routes("BGD", "TX", NODES, DISTANCES, FACTORS, CHOICES)

    feeder_to_ny = [
        r
        for r in routes
        if r.mode == "vessel" and len(r.legs) == 3 and r.legs[1].to_node == "arrival_seaport:NY"
    ]
    if feeder_to_ny:
        route = feeder_to_ny[0]
        assert "babalmandab" in route.passages
        assert "suez" in route.passages
