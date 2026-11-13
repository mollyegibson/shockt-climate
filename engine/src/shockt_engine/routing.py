"""Route enumeration for the calculator: individual freight routes between specific nodes, ranked by
carbon footprint. Unlike `lanes` (which computes tonnage-weighted averages for a country's trade
flow), this module enumerates every concrete route and scores each one independently."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

from shockt_engine.factors import Factor, LegFactor, LegFactors, Mode, select_factor
from shockt_engine.lanes import InlandMode, LaneMode, Network

SEA_SPEED_KMH = 23.15
AIR_SPEED_KMH = 850.0


@dataclass(frozen=True)
class Node:
    kind: str
    name: str
    iso3: str
    lat: float
    lon: float
    source_key: str


@dataclass(frozen=True)
class EdgeDistance:
    km: float
    duration_h: float | None
    passages: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeederEdge:
    """Origin port -> hub port, from agg_feeder_hub_shares_monthly."""

    km: float
    duration_h: float | None
    hub_has_us_voyages: bool


@dataclass(frozen=True)
class RouteDistances:
    sea: Mapping[tuple[str, str], Mapping[str, EdgeDistance]]
    air: Mapping[tuple[str, str], EdgeDistance]
    road: Mapping[tuple[str, str], EdgeDistance]
    rail: Mapping[tuple[str, str], EdgeDistance]
    feeder: Mapping[tuple[str, str], FeederEdge]


@dataclass(frozen=True)
class RouteLeg:
    name: str
    from_node: str
    to_node: str
    network: Network
    factor_mode: Mode
    km: float
    duration_h: float | None
    ttw_kg_co2e_per_tkm: float
    wtt_kg_co2e_per_tkm: float
    passages: tuple[str, ...]

    @property
    def wtw_kg_co2e_per_tkm(self) -> float:
        return self.ttw_kg_co2e_per_tkm + self.wtt_kg_co2e_per_tkm

    @property
    def wtw_kg_co2e_per_t(self) -> float:
        return self.km * self.wtw_kg_co2e_per_tkm


@dataclass(frozen=True)
class Route:
    mode: LaneMode
    legs: tuple[RouteLeg, ...]
    total_km: float
    total_duration_h: float | None
    total_ttw_kg_co2e_per_t: float
    total_wtt_kg_co2e_per_t: float
    total_wtw_kg_co2e_per_t: float
    passages: tuple[str, ...]
    scenario: str


@dataclass(frozen=True)
class RouteOptions:
    scenario: str = "open"
    modes: frozenset[LaneMode] | None = None
    inland_mode: InlandMode = "truck"
    vehicle_overrides: Mapping[Mode, LegFactor] = field(default_factory=dict)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _resolve_factor(
    factor_rows: list[Factor],
    mode: Mode,
    choices: LegFactors,
    overrides: Mapping[Mode, LegFactor],
) -> tuple[float, float]:
    """Returns (ttw, wtt) for the given mode."""
    choice = overrides.get(mode, choices.for_mode(mode))
    f = select_factor(factor_rows, mode, choice)
    assert f.ttw_kg_co2e_per_tkm is not None
    assert f.wtt_kg_co2e_per_tkm is not None
    return f.ttw_kg_co2e_per_tkm, f.wtt_kg_co2e_per_tkm


def _build_route(mode: LaneMode, legs: list[RouteLeg], scenario: str) -> Route:
    total_km = sum(leg.km for leg in legs)
    total_duration_h: float | None = None
    if all(leg.duration_h is not None for leg in legs):
        total_duration_h = sum(leg.duration_h for leg in legs)  # type: ignore[arg-type]
    total_ttw = sum(leg.km * leg.ttw_kg_co2e_per_tkm for leg in legs)
    total_wtt = sum(leg.km * leg.wtt_kg_co2e_per_tkm for leg in legs)
    all_passages: list[str] = []
    for leg in legs:
        for p in leg.passages:
            if p not in all_passages:
                all_passages.append(p)
    return Route(
        mode=mode,
        legs=tuple(legs),
        total_km=total_km,
        total_duration_h=total_duration_h,
        total_ttw_kg_co2e_per_t=total_ttw,
        total_wtt_kg_co2e_per_t=total_wtt,
        total_wtw_kg_co2e_per_t=total_ttw + total_wtt,
        passages=tuple(all_passages),
        scenario=scenario,
    )


def deduplicate_port_clusters(
    nodes: Mapping[str, Node],
    port_ids: list[str],
    voyages: Mapping[str, int],
    threshold_km: float = 5.0,
) -> list[str]:
    """Keep one representative per port cluster (haversine < threshold_km)."""
    sorted_ports = sorted(port_ids, key=lambda p: voyages.get(p, 0), reverse=True)
    kept: list[str] = []
    for port in sorted_ports:
        node = nodes[port]
        if any(
            _haversine_km(node.lat, node.lon, nodes[k].lat, nodes[k].lon) < threshold_km
            for k in kept
        ):
            continue
        kept.append(port)
    return kept


def enumerate_routes(
    origin_country: str,
    destination_state: str,
    nodes: Mapping[str, Node],
    distances: RouteDistances,
    factors: Iterable[Factor],
    factor_choices: LegFactors,
    crossing_plants: Mapping[str, Mapping[str, str]] | None = None,
    options: RouteOptions | None = None,
    origin_node: str | None = None,
    destination_node: str | None = None,
    hs6: str | None = None,
) -> list[Route]:
    """Enumerate all freight routes from an origin country to a US destination state."""
    if options is None:
        options = RouteOptions()

    scenario = options.scenario
    factor_rows = list(factors)

    mode_factors: dict[Mode, tuple[float, float]] = {}
    for mode in ("ocean", "air", "truck", "rail"):
        mode_factors[mode] = _resolve_factor(
            factor_rows, mode, factor_choices, options.vehicle_overrides
        )

    departure_ports = [
        nid for nid, n in nodes.items() if n.kind == "departure_port" and n.iso3 == origin_country
    ]
    departure_airports = [
        nid
        for nid, n in nodes.items()
        if n.kind == "departure_airport" and n.iso3 == origin_country
    ]
    arrival_seaports = [nid for nid, n in nodes.items() if n.kind == "arrival_seaport"]
    air_gateways = [nid for nid, n in nodes.items() if n.kind == "air_gateway"]
    dest_nodes = [
        nid
        for nid, n in nodes.items()
        if n.kind == "destination_state" and n.source_key == destination_state
    ]
    border_crossings = [nid for nid, n in nodes.items() if n.kind == "border_crossing"]

    if destination_node:
        dest_nodes = [d for d in dest_nodes if d == destination_node]
    if origin_node:
        departure_ports = [p for p in departure_ports if p == origin_node]
        departure_airports = [a for a in departure_airports if a == origin_node]

    routes: list[Route] = []
    active_modes = options.modes

    # Vessel routes (direct and feeder)
    if active_modes is None or "vessel" in active_modes:
        inland_network: Network = "road" if options.inland_mode == "truck" else "rail"
        inland_mode: Mode = options.inland_mode
        inland_ttw, inland_wtt = mode_factors[inland_mode]
        ocean_ttw, ocean_wtt = mode_factors["ocean"]

        for dest in dest_nodes:
            for seaport in arrival_seaports:
                inland_edge = (distances.road if inland_network == "road" else distances.rail).get(
                    (seaport, dest)
                )
                if inland_edge is None:
                    continue

                inland_leg = RouteLeg(
                    name=f"{nodes[seaport].name} → {nodes[dest].name}",
                    from_node=seaport,
                    to_node=dest,
                    network=inland_network,
                    factor_mode=inland_mode,
                    km=inland_edge.km,
                    duration_h=inland_edge.duration_h,
                    ttw_kg_co2e_per_tkm=inland_ttw,
                    wtt_kg_co2e_per_tkm=inland_wtt,
                    passages=(),
                )

                # Direct routes
                for dep in departure_ports:
                    sea_scenarios = distances.sea.get((dep, seaport))
                    if sea_scenarios is None:
                        continue
                    sea_edge = sea_scenarios.get(scenario)
                    if sea_edge is None:
                        continue

                    ocean_leg = RouteLeg(
                        name=f"{nodes[dep].name} → {nodes[seaport].name}",
                        from_node=dep,
                        to_node=seaport,
                        network="sea",
                        factor_mode="ocean",
                        km=sea_edge.km,
                        duration_h=sea_edge.km / SEA_SPEED_KMH,
                        ttw_kg_co2e_per_tkm=ocean_ttw,
                        wtt_kg_co2e_per_tkm=ocean_wtt,
                        passages=sea_edge.passages,
                    )
                    routes.append(_build_route("vessel", [ocean_leg, inland_leg], scenario))

                # Feeder routes
                for dep in departure_ports:
                    for (orig, hub), feeder_edge in distances.feeder.items():
                        if orig != dep or not feeder_edge.hub_has_us_voyages:
                            continue
                        hub_sea = distances.sea.get((hub, seaport))
                        if hub_sea is None:
                            continue
                        hub_edge = hub_sea.get(scenario)
                        if hub_edge is None:
                            continue
                        if hub in {dep, seaport, dest}:
                            continue

                        feeder_leg = RouteLeg(
                            name=f"{nodes[dep].name} → {nodes[hub].name}",
                            from_node=dep,
                            to_node=hub,
                            network="sea",
                            factor_mode="ocean",
                            km=feeder_edge.km,
                            duration_h=feeder_edge.duration_h,
                            ttw_kg_co2e_per_tkm=ocean_ttw,
                            wtt_kg_co2e_per_tkm=ocean_wtt,
                            passages=(),
                        )
                        mainline_leg = RouteLeg(
                            name=f"{nodes[hub].name} → {nodes[seaport].name}",
                            from_node=hub,
                            to_node=seaport,
                            network="sea",
                            factor_mode="ocean",
                            km=hub_edge.km,
                            duration_h=hub_edge.km / SEA_SPEED_KMH,
                            ttw_kg_co2e_per_tkm=ocean_ttw,
                            wtt_kg_co2e_per_tkm=ocean_wtt,
                            passages=hub_edge.passages,
                        )
                        routes.append(
                            _build_route("vessel", [feeder_leg, mainline_leg, inland_leg], scenario)
                        )

    # Air routes
    if active_modes is None or "air" in active_modes:
        air_ttw, air_wtt = mode_factors["air"]
        truck_ttw, truck_wtt = mode_factors["truck"]
        for dest in dest_nodes:
            for gw in air_gateways:
                gw_road = distances.road.get((gw, dest))
                if gw_road is None:
                    continue

                gw_leg = RouteLeg(
                    name=f"{nodes[gw].name} → {nodes[dest].name}",
                    from_node=gw,
                    to_node=dest,
                    network="road",
                    factor_mode="truck",
                    km=gw_road.km,
                    duration_h=gw_road.duration_h,
                    ttw_kg_co2e_per_tkm=truck_ttw,
                    wtt_kg_co2e_per_tkm=truck_wtt,
                    passages=(),
                )

                for dep in departure_airports:
                    air_edge = distances.air.get((dep, gw))
                    if air_edge is None:
                        continue

                    air_leg = RouteLeg(
                        name=f"{nodes[dep].name} → {nodes[gw].name}",
                        from_node=dep,
                        to_node=gw,
                        network="air",
                        factor_mode="air",
                        km=air_edge.km,
                        duration_h=air_edge.km / AIR_SPEED_KMH,
                        ttw_kg_co2e_per_tkm=air_ttw,
                        wtt_kg_co2e_per_tkm=air_wtt,
                        passages=(),
                    )
                    routes.append(_build_route("air", [air_leg, gw_leg], scenario))

    # Mexico truck/rail routes
    if origin_country == "MEX":
        plant_crossing_map: Mapping[str, str] | None = None
        if hs6 and crossing_plants:
            plant_crossing_map = crossing_plants.get(hs6)

        if active_modes is None or "truck" in active_modes:
            truck_ttw, truck_wtt = mode_factors["truck"]
            for dest in dest_nodes:
                for cx in border_crossings:
                    cx_road = distances.road.get((cx, dest))
                    if cx_road is None:
                        continue

                    cx_leg = RouteLeg(
                        name=f"{nodes[cx].name} → {nodes[dest].name}",
                        from_node=cx,
                        to_node=dest,
                        network="road",
                        factor_mode="truck",
                        km=cx_road.km,
                        duration_h=cx_road.duration_h,
                        ttw_kg_co2e_per_tkm=truck_ttw,
                        wtt_kg_co2e_per_tkm=truck_wtt,
                        passages=(),
                    )

                    plants = _plants_for_crossing(
                        cx, nodes, distances, plant_crossing_map, origin_node
                    )
                    for plant in plants:
                        plant_road = distances.road.get((plant, cx))
                        if plant_road is None:
                            continue
                        plant_leg = RouteLeg(
                            name=f"{nodes[plant].name} → {nodes[cx].name}",
                            from_node=plant,
                            to_node=cx,
                            network="road",
                            factor_mode="truck",
                            km=plant_road.km,
                            duration_h=plant_road.duration_h,
                            ttw_kg_co2e_per_tkm=truck_ttw,
                            wtt_kg_co2e_per_tkm=truck_wtt,
                            passages=(),
                        )
                        routes.append(_build_route("truck", [plant_leg, cx_leg], scenario))

        if active_modes is None or "rail" in active_modes:
            rail_ttw, rail_wtt = mode_factors["rail"]
            truck_ttw, truck_wtt = mode_factors["truck"]
            for dest in dest_nodes:
                for cx in border_crossings:
                    cx_rail = distances.rail.get((cx, dest))
                    if cx_rail is None:
                        continue

                    cx_leg = RouteLeg(
                        name=f"{nodes[cx].name} → {nodes[dest].name}",
                        from_node=cx,
                        to_node=dest,
                        network="rail",
                        factor_mode="rail",
                        km=cx_rail.km,
                        duration_h=cx_rail.duration_h,
                        ttw_kg_co2e_per_tkm=rail_ttw,
                        wtt_kg_co2e_per_tkm=rail_wtt,
                        passages=(),
                    )

                    plants = _plants_for_crossing(
                        cx, nodes, distances, plant_crossing_map, origin_node
                    )
                    for plant in plants:
                        plant_road = distances.road.get((plant, cx))
                        if plant_road is None:
                            continue
                        plant_leg = RouteLeg(
                            name=f"{nodes[plant].name} → {nodes[cx].name}",
                            from_node=plant,
                            to_node=cx,
                            network="road",
                            factor_mode="truck",
                            km=plant_road.km,
                            duration_h=plant_road.duration_h,
                            ttw_kg_co2e_per_tkm=truck_ttw,
                            wtt_kg_co2e_per_tkm=truck_wtt,
                            passages=(),
                        )
                        routes.append(_build_route("rail", [plant_leg, cx_leg], scenario))

    routes.sort(key=lambda r: r.total_wtw_kg_co2e_per_t)
    return routes


def _plants_for_crossing(
    crossing: str,
    nodes: Mapping[str, Node],
    distances: RouteDistances,
    plant_crossing_map: Mapping[str, str] | None,
    origin_node: str | None,
) -> list[str]:
    """Plants that serve a given border crossing, filtered by HS6 map and origin_node."""
    if plant_crossing_map is not None:
        plant_id = plant_crossing_map.get(crossing)
        if plant_id is None:
            return []
        plants = [plant_id]
    else:
        plants = [
            nid
            for nid, n in nodes.items()
            if n.kind == "mexico_plant" and (nid, crossing) in distances.road
        ]
    if origin_node:
        plants = [p for p in plants if p == origin_node]
    return plants
