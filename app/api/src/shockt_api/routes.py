"""The /routes endpoint: enumerate and score freight routes."""

from fastapi import APIRouter, Query
from shockt_engine import (
    LegFactor,
    Route,
    RouteOptions,
    deduplicate_port_clusters,
    enumerate_routes,
    load_leg_factors,
)
from shockt_engine.factors import Mode
from shockt_engine.lanes import LaneMode

from shockt_api.db import CachedData
from shockt_api.schemas import (
    ComparisonRoute,
    FactorInfo,
    LegResponse,
    QueryEcho,
    RouteResponse,
    RoutesResponse,
)

router = APIRouter()

_factor_choices = load_leg_factors()


def _get_data() -> CachedData:
    """Placeholder replaced by main.py lifespan with the real cached data."""
    raise RuntimeError("cached data not initialized")


def init_routes(data: CachedData) -> None:
    """Inject the cached data into this module. Called once at startup."""
    global _get_data
    _cached = data

    def _get_data() -> CachedData:
        return _cached


def _route_to_response(
    route: Route,
    nodes: dict[str, object],
    cargo_t: float | None,
) -> RouteResponse:
    legs = []
    for leg in route.legs:
        from_node_obj = nodes[leg.from_node]
        to_node_obj = nodes[leg.to_node]
        legs.append(
            LegResponse(
                name=leg.name,
                from_node=leg.from_node,
                to_node=leg.to_node,
                from_name=from_node_obj.name,
                to_name=to_node_obj.name,
                from_lat=from_node_obj.lat,
                from_lon=from_node_obj.lon,
                to_lat=to_node_obj.lat,
                to_lon=to_node_obj.lon,
                network=leg.network,
                mode=leg.factor_mode,
                km=round(leg.km, 1),
                duration_h=round(leg.duration_h, 1) if leg.duration_h is not None else None,
                ttw_kg_co2e_per_tkm=round(leg.ttw_kg_co2e_per_tkm, 6),
                wtt_kg_co2e_per_tkm=round(leg.wtt_kg_co2e_per_tkm, 6),
                wtw_kg_co2e_per_tkm=round(leg.wtw_kg_co2e_per_tkm, 6),
                wtw_kg_co2e_per_t=round(leg.wtw_kg_co2e_per_t, 1),
                passages=list(leg.passages),
            )
        )
    total_wtw_co2e = None
    if cargo_t is not None:
        total_wtw_co2e = round(route.total_wtw_kg_co2e_per_t * cargo_t, 1)

    return RouteResponse(
        legs=legs,
        total_wtw_kg_co2e_per_t=round(route.total_wtw_kg_co2e_per_t, 1),
        total_ttw_kg_co2e_per_t=round(route.total_ttw_kg_co2e_per_t, 1),
        total_wtt_kg_co2e_per_t=round(route.total_wtt_kg_co2e_per_t, 1),
        total_wtw_kg_co2e=total_wtw_co2e,
        total_km=round(route.total_km, 1),
        total_duration_h=(
            round(route.total_duration_h, 1) if route.total_duration_h is not None else None
        ),
        passages=list(route.passages),
        scenario=route.scenario,
    )


def _node_path(route: Route) -> tuple[str, ...]:
    """The full node path for scenario matching: all from/to nodes in order."""
    path: list[str] = []
    for leg in route.legs:
        if not path or path[-1] != leg.from_node:
            path.append(leg.from_node)
        path.append(leg.to_node)
    return tuple(path)


def _route_category(route: Route) -> str:
    """Classify a route into its response bucket."""
    if route.mode == "vessel":
        return "vessel_feeder" if len(route.legs) == 3 else "vessel_direct"
    return route.mode


def _build_factor_info(data: CachedData) -> dict[str, FactorInfo]:
    result: dict[str, FactorInfo] = {}
    for mode_name in ("ocean", "air", "truck", "rail"):
        choice = _factor_choices.for_mode(mode_name)
        from shockt_engine import select_factor

        factor = select_factor(data.factors, mode_name, choice)
        result[mode_name] = FactorInfo(
            source=factor.source,
            vehicle_type=factor.vehicle_type or "",
            size_class=factor.size_class,
            ttw=round(factor.ttw_kg_co2e_per_tkm or 0.0, 6),
            wtt=round(factor.wtt_kg_co2e_per_tkm or 0.0, 6),
            wtw=round(factor.wtw_kg_co2e_per_tkm or 0.0, 6),
        )
    return result


def _dedup_ports(data: CachedData, origin_country: str) -> dict[str, object]:
    """Return a filtered nodes dict with deduplicated departure ports."""
    dep_ports = [
        nid
        for nid, n in data.nodes.items()
        if n.kind == "departure_port" and n.iso3 == origin_country
    ]
    kept = deduplicate_port_clusters(data.nodes, dep_ports, data.node_voyages)
    excluded = set(dep_ports) - set(kept)
    if not excluded:
        return data.nodes
    return {nid: n for nid, n in data.nodes.items() if nid not in excluded}


@router.get("/routes")
def get_routes(
    origin: str,
    destination: str,
    cargo_t: float | None = None,
    modes: str | None = None,
    inland_mode: str = "truck",
    scenario: str = "open",
    compare_scenario: str | None = None,
    hs6: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
) -> RoutesResponse:
    data = _get_data()

    origin_country: str
    origin_node: str | None = None
    if len(origin) == 3 and origin.isalpha():
        origin_country = origin.upper()
    else:
        node = data.nodes.get(origin)
        if node is None:
            origin_country = origin
        else:
            origin_country = node.iso3
            origin_node = origin

    destination_state = destination.upper()
    destination_node: str | None = None
    if not (len(destination) == 2 and destination.isalpha()):
        if destination in data.nodes:
            destination_node = destination
            destination_state = data.nodes[destination].source_key

    active_modes: frozenset[LaneMode] | None = None
    mode_list: list[str]
    if modes:
        mode_list = [m.strip() for m in modes.split(",")]
        active_modes = frozenset(mode_list)
    else:
        mode_list = ["vessel", "air", "truck", "rail"]

    vehicle_overrides: dict[Mode, LegFactor] = {}
    options = RouteOptions(
        scenario=scenario,
        modes=active_modes,
        inland_mode=inland_mode,
        vehicle_overrides=vehicle_overrides,
    )

    nodes = _dedup_ports(data, origin_country)

    all_routes = enumerate_routes(
        origin_country=origin_country,
        destination_state=destination_state,
        nodes=nodes,
        distances=data.distances,
        factors=data.factors,
        factor_choices=_factor_choices,
        crossing_plants=data.crossing_plants,
        options=options,
        origin_node=origin_node,
        destination_node=destination_node,
        hs6=hs6,
    )

    comparison = None
    if compare_scenario:
        compare_options = RouteOptions(
            scenario=compare_scenario,
            modes=active_modes,
            inland_mode=inland_mode,
            vehicle_overrides=vehicle_overrides,
        )
        compare_routes = enumerate_routes(
            origin_country=origin_country,
            destination_state=destination_state,
            nodes=nodes,
            distances=data.distances,
            factors=data.factors,
            factor_choices=_factor_choices,
            crossing_plants=data.crossing_plants,
            options=compare_options,
            origin_node=origin_node,
            destination_node=destination_node,
            hs6=hs6,
        )
        comparison = _build_comparison(
            all_routes, compare_routes, nodes, cargo_t, limit, scenario, compare_scenario
        )

    buckets: dict[str, list[RouteResponse]] = {
        "vessel_direct": [],
        "vessel_feeder": [],
        "air": [],
        "truck": [],
        "rail": [],
    }
    for route in all_routes:
        cat = _route_category(route)
        if len(buckets[cat]) < limit:
            buckets[cat].append(_route_to_response(route, nodes, cargo_t))

    return RoutesResponse(
        vessel_direct=buckets["vessel_direct"],
        vessel_feeder=buckets["vessel_feeder"],
        air=buckets["air"],
        truck=buckets["truck"],
        rail=buckets["rail"],
        comparison=comparison,
        factors=_build_factor_info(data),
        commodity=None,
        query=QueryEcho(
            origin=origin,
            destination=destination,
            cargo_t=cargo_t,
            scenario=scenario,
            modes=mode_list,
            inland_mode=inland_mode,
        ),
    )


def _build_comparison(
    primary_routes: list[Route],
    compare_routes: list[Route],
    nodes: dict[str, object],
    cargo_t: float | None,
    limit: int,
    primary_scenario: str,
    compare_scenario: str,
) -> dict[str, list[ComparisonRoute]]:
    """Match routes by full node path, apply limit, compute deltas."""
    compare_by_path: dict[tuple[str, ...], Route] = {}
    for r in compare_routes:
        compare_by_path[_node_path(r)] = r

    result: dict[str, list[ComparisonRoute]] = {
        "vessel_direct": [],
        "vessel_feeder": [],
        "air": [],
        "truck": [],
        "rail": [],
    }

    for route in primary_routes:
        cat = _route_category(route)
        if len(result[cat]) >= limit:
            continue
        path = _node_path(route)
        matched = compare_by_path.pop(path, None)

        primary_resp = _route_to_response(route, nodes, cargo_t)
        if matched:
            compare_resp = _route_to_response(matched, nodes, cargo_t)
            delta = round(matched.total_wtw_kg_co2e_per_t - route.total_wtw_kg_co2e_per_t, 1)
            result[cat].append(
                ComparisonRoute(
                    primary=primary_resp,
                    compare=compare_resp,
                    delta_wtw_kg_co2e_per_t=delta,
                )
            )
        else:
            result[cat].append(
                ComparisonRoute(
                    primary=primary_resp,
                    compare=None,
                    delta_wtw_kg_co2e_per_t=None,
                    note=f"Route not available under {compare_scenario}",
                )
            )

    for _path, route in compare_by_path.items():
        cat = _route_category(route)
        if len(result[cat]) >= limit:
            continue
        compare_resp = _route_to_response(route, nodes, cargo_t)
        result[cat].append(
            ComparisonRoute(
                primary=None,
                compare=compare_resp,
                delta_wtw_kg_co2e_per_t=None,
                note=f"Route not available under {primary_scenario}",
            )
        )

    return result
