"""The legs of a lane and its emissions per tonne. A lane is an origin and a delivery mode into the
US; its legs run from where the freight leaves to the state it's bound for:

- air: departure airport → US air gateway (air), gateway → destination state (truck)
- vessel: departure port → US seaport (ocean), seaport → destination state (truck, or rail)
- truck: Mexican plant → border crossing (truck), crossing → destination state (truck)
- rail: Mexican plant → border crossing (truck), crossing → destination state (rail)

Each leg's distance is averaged over the nodes the lane uses, weighted by their tonnage. The plant
→ crossing leg uses the known plant for each crossing; the other legs treat their two ends as
independent, since no source links them.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from shockt_engine.emissions import (
    EmissionsError,
    Leg,
    lane_intensity,
    pair_weighted_distance,
    sea_leg_distance,
    weighted_leg_distance,
)
from shockt_engine.factors import Mode

LaneMode = Literal["air", "vessel", "truck", "rail"]
InlandMode = Literal["truck", "rail"]
Network = Literal["sea", "air", "road", "rail"]

NodeWeights = Mapping[str, float]
"""Node id → tonnes."""


@dataclass(frozen=True)
class LaneInputs:
    """What a lane's legs need, for one origin, group of HS codes and window."""

    weights: Mapping[str, NodeWeights]
    """Node kind (`departure_port`, `air_gateway`, ...) → node weights, in the lane's mode."""
    distances: Mapping[Network, Mapping[tuple[str, str], float]]
    """Network → (from node, to node) → km."""
    factors: Mapping[Mode, float]
    """Factor mode → kg CO2e per tonne-km."""
    observed_sea: Mapping[str, float] = field(default_factory=dict)
    """Arrival seaport → observed km from the origin's voyages."""
    crossing_plants: Mapping[str, str] = field(default_factory=dict)
    """Border crossing node → the plant node its Mexican leg starts at."""


@dataclass(frozen=True)
class LegResult:
    name: str
    factor_mode: Mode
    km: float
    kg_co2e_per_tkm: float
    covered_share: float
    observed_share: float | None = None

    @property
    def kg_co2e_per_t(self) -> float:
        return self.km * self.kg_co2e_per_tkm


@dataclass(frozen=True)
class LaneResult:
    mode: LaneMode
    legs: tuple[LegResult, ...]
    missing_legs: tuple[str, ...]
    """Legs left out because the lane has no node for them (e.g. no plant for a code)."""

    @property
    def kg_co2e_per_t(self) -> float:
        return lane_intensity(Leg(leg.km, leg.kg_co2e_per_tkm) for leg in self.legs)


def _weights(inputs: LaneInputs, kind: str) -> NodeWeights:
    weights = inputs.weights.get(kind, {})
    return {node: w for node, w in weights.items() if w > 0}


def _independent_leg(
    inputs: LaneInputs, name: str, network: Network, mode: Mode, origin: str, destination: str
) -> LegResult:
    distance = weighted_leg_distance(
        inputs.distances[network], _weights(inputs, origin), _weights(inputs, destination)
    )
    return LegResult(name, mode, distance.km, inputs.factors[mode], distance.covered_share)


def _plant_leg(inputs: LaneInputs) -> LegResult | None:
    crossings = _weights(inputs, "border_crossing")
    pairs = {
        (inputs.crossing_plants[c], c): w
        for c, w in crossings.items()
        if c in inputs.crossing_plants
    }
    if not pairs:
        return None
    distance = pair_weighted_distance(inputs.distances["road"], pairs)
    covered = sum(pairs.values()) / sum(crossings.values()) * distance.covered_share
    return LegResult("plant → crossing", "truck", distance.km, inputs.factors["truck"], covered)


def lane_legs(mode: LaneMode, inputs: LaneInputs, inland: InlandMode = "truck") -> LaneResult:
    """The legs of a lane in `mode`, with their distances and factors. `inland` is how vessel
    freight travels from the seaport to the destination state; air freight goes by truck."""
    if inland == "rail" and mode != "vessel":
        raise EmissionsError(f"only vessel lanes have a rail inland leg, not {mode}")
    legs: list[LegResult] = []
    missing: list[str] = []
    if mode == "air":
        legs.append(
            _independent_leg(
                inputs, "airport → gateway", "air", "air", "departure_airport", "air_gateway"
            )
        )
        legs.append(
            _independent_leg(
                inputs, "gateway → state", "road", "truck", "air_gateway", "destination_state"
            )
        )
    elif mode == "vessel":
        sea = sea_leg_distance(
            inputs.observed_sea,
            inputs.distances["sea"],
            _weights(inputs, "departure_port"),
            _weights(inputs, "arrival_seaport"),
        )
        legs.append(
            LegResult(
                "port → seaport",
                "ocean",
                sea.km,
                inputs.factors["ocean"],
                sea.covered_share,
                sea.observed_share,
            )
        )
        legs.append(
            _independent_leg(
                inputs,
                "seaport → state",
                "road" if inland == "truck" else "rail",
                inland,
                "arrival_seaport",
                "destination_state",
            )
        )
    else:
        plant = _plant_leg(inputs)
        if plant is None:
            missing.append("plant → crossing")
        else:
            legs.append(plant)
        network: Network = "road" if mode == "truck" else "rail"
        factor_mode: Mode = "truck" if mode == "truck" else "rail"
        legs.append(
            _independent_leg(
                inputs,
                "crossing → state",
                network,
                factor_mode,
                "border_crossing",
                "destination_state",
            )
        )
    if not legs:
        raise EmissionsError(f"lane in {mode} has no legs")
    return LaneResult(mode, tuple(legs), tuple(missing))
