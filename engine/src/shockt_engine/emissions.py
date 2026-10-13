"""Leg distances averaged over the places a lane uses, and emissions per tonne of a lane and of a
supply mix. Distances are km, factors kg CO2e per tonne-km, intensities kg CO2e per tonne."""

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass


class EmissionsError(Exception):
    """A distance or intensity can't be formed from the values given."""


@dataclass(frozen=True)
class LegDistance:
    km: float
    covered_share: float
    """Share of the leg's weight on node pairs that have a distance; the rest is left out."""


def pair_weighted_distance(
    distances: Mapping[tuple[str, str], float], pair_weights: Mapping[tuple[str, str], float]
) -> LegDistance:
    """A leg's distance averaged over node pairs with known weights. Pairs with no distance are
    left out and the rest renormalised."""
    total = sum(pair_weights.values())
    if total <= 0:
        raise EmissionsError("a leg needs positive pair weights")
    covered = 0.0
    weighted_km = 0.0
    for pair, weight in pair_weights.items():
        km = distances.get(pair)
        if km is None:
            continue
        covered += weight / total
        weighted_km += weight / total * km
    if covered <= 0:
        raise EmissionsError("no node pair of the leg has a distance")
    return LegDistance(km=weighted_km / covered, covered_share=covered)


def weighted_leg_distance(
    distances: Mapping[tuple[str, str], float],
    origin_weights: Mapping[str, float],
    destination_weights: Mapping[str, float],
) -> LegDistance:
    """A leg's distance averaged over its node pairs when no source links its origins to its
    destinations: each pair's weight is the product of the two ends' weights, as if independent."""
    if sum(origin_weights.values()) <= 0 or sum(destination_weights.values()) <= 0:
        raise EmissionsError("a leg needs positive weights at both ends")
    pair_weights = {
        (origin, destination): w_origin * w_destination
        for origin, w_origin in origin_weights.items()
        for destination, w_destination in destination_weights.items()
    }
    return pair_weighted_distance(distances, pair_weights)


@dataclass(frozen=True)
class SeaLegDistance:
    km: float
    observed_share: float
    """Share of the arrival weight whose distance was observed rather than modelled."""
    covered_share: float


def sea_leg_distance(
    observed: Mapping[str, float],
    modelled: Mapping[tuple[str, str], float],
    departure_weights: Mapping[str, float],
    arrival_weights: Mapping[str, float],
) -> SeaLegDistance:
    """A sea leg's distance averaged over arrival ports. A port with an observed distance (from
    the origin's voyages) uses it; otherwise the modelled distances from the origin's departure
    ports, averaged by the departure weights. Arrival ports with neither are left out."""
    arrival_total = sum(arrival_weights.values())
    if arrival_total <= 0:
        raise EmissionsError("a sea leg needs positive arrival weights")
    covered = observed_weight = weighted_km = 0.0
    for port, weight in arrival_weights.items():
        share = weight / arrival_total
        if port in observed:
            km = observed[port]
            observed_weight += share
        else:
            to_port = {(d, port): w for d, w in departure_weights.items()}
            if not any(pair in modelled for pair in to_port) or sum(to_port.values()) <= 0:
                continue
            km = pair_weighted_distance(modelled, to_port).km
        covered += share
        weighted_km += share * km
    if covered <= 0:
        raise EmissionsError("no arrival port of the sea leg has a distance")
    return SeaLegDistance(
        km=weighted_km / covered, observed_share=observed_weight / covered, covered_share=covered
    )


@dataclass(frozen=True)
class Leg:
    km: float
    kg_co2e_per_tkm: float


def lane_intensity(legs: Iterable[Leg]) -> float:
    """Emissions per tonne of a lane: the sum over its legs of distance × factor."""
    return sum(leg.km * leg.kg_co2e_per_tkm for leg in legs)


def mix_intensity[K: Hashable](
    lane_shares: Mapping[K, float], lane_intensities: Mapping[K, float]
) -> float:
    """Emissions per tonne of a supply mix: each lane's share of tonnage × its intensity. Shares
    must sum to 1, and every lane with a share needs an intensity."""
    total = sum(lane_shares.values())
    if abs(total - 1) > 1e-9:
        raise EmissionsError(f"lane shares sum to {total}, not 1")
    missing = [k for k, s in lane_shares.items() if s > 0 and k not in lane_intensities]
    if missing:
        raise EmissionsError(f"lanes with a share but no intensity: {missing}")
    return sum(s * lane_intensities[k] for k, s in lane_shares.items() if s > 0)


def break_even_km(advantage_kg_per_t: float, kg_co2e_per_tkm: float) -> float:
    """How far a tonne must travel at `kg_co2e_per_tkm` to emit `advantage_kg_per_t`: the
    component leg that would cancel a route's advantage."""
    if kg_co2e_per_tkm <= 0:
        raise EmissionsError("a break-even distance needs a positive factor")
    return advantage_kg_per_t / kg_co2e_per_tkm
