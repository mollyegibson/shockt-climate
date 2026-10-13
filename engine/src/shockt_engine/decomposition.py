"""How much each dimension of a supply mix (origin, arrival coast, mode, ...) and each part of its
lanes' emissions (the international leg, the inland leg, ...) contributed to a change in the mix's
emissions per tonne."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from math import factorial

from shockt_engine.emissions import EmissionsError

Cell = tuple[str, ...]
"""One value per dimension, in the order the dimensions are given."""


@dataclass(frozen=True)
class MixCell:
    tonnes: float
    intensity: Mapping[str, float]
    """Component name (e.g. `international`, `inland`) → kg CO2e per tonne; a cell's emissions per
    tonne are their sum, and a component a cell lacks counts as 0."""

    @property
    def kg_co2e_per_t(self) -> float:
        return sum(self.intensity.values())


@dataclass(frozen=True)
class MixDecomposition:
    baseline: float
    window: float
    effects: dict[str, float]
    """Dimension or component name → its share of the change in kg CO2e per tonne. The effects
    sum to `window − baseline`."""


type Conditionals = list[dict[Cell, dict[str, float]]]
type Intensities = Mapping[Cell, Mapping[str, float]]


def _conditionals(cells: Mapping[Cell, MixCell], depth: int) -> Conditionals:
    """For each dimension, the share of each value within its parent cell (the values of the
    dimensions before it)."""
    levels: Conditionals = []
    for level in range(depth):
        tonnes: dict[Cell, dict[str, float]] = {}
        for cell, value in cells.items():
            parent = tonnes.setdefault(cell[:level], {})
            parent[cell[level]] = parent.get(cell[level], 0.0) + value.tonnes
        levels.append(
            {
                parent: {v: t / sum(children.values()) for v, t in children.items()}
                for parent, children in tonnes.items()
            }
        )
    return levels


def _mix(
    shares: Sequence[tuple[Mapping[Cell, dict[str, float]], Mapping[Cell, dict[str, float]]]],
    components: Mapping[str, tuple[Intensities, Intensities]],
    parent: Cell = (),
) -> float:
    """The mix's emissions per tonne with each level's shares and each component's intensities
    taken from the first source given, or the second where the first lacks the cell."""
    level = len(parent)
    if level == len(shares):
        total = 0.0
        for name, (chosen, fallback) in components.items():
            source = chosen if parent in chosen else fallback
            total += source[parent].get(name, 0.0)
        return total
    chosen_shares, fallback_shares = shares[level]
    values = chosen_shares.get(parent)
    if values is None:
        values = fallback_shares[parent]
    return sum(share * _mix(shares, components, (*parent, v)) for v, share in values.items())


def mix_decomposition(
    baseline: Mapping[Cell, MixCell], window: Mapping[Cell, MixCell], dimensions: Sequence[str]
) -> MixDecomposition:
    """The change in a mix's emissions per tonne from `baseline` to `window`, split between its
    dimensions and the components of its cells' intensities. Each factor is either at its
    baseline or its window value: a dimension's shares of each value within its parent cell (the
    values of the dimensions before it), or one component of the cells' emissions per tonne. A
    factor's effect is its Shapley value: the change from switching it to its window value,
    averaged over every order of switching the factors, so the effects sum to the whole change.
    Where one side lacks a parent cell or a cell (an origin new in the window, say), the other
    side's value is used."""
    depth = len(dimensions)
    components = sorted(
        {name for cells in (baseline, window) for c in cells.values() for name in c.intensity}
    )
    if depth == 0 or len(set(dimensions)) != depth:
        raise EmissionsError("dimensions must be distinct names")
    if set(dimensions) & set(components):
        raise EmissionsError("a dimension and an intensity component can't share a name")
    for name, cells in (("baseline", baseline), ("window", window)):
        if any(len(cell) != depth for cell in cells):
            raise EmissionsError(f"every {name} cell needs one value per dimension")
        if any(c.tonnes < 0 for c in cells.values()):
            raise EmissionsError(f"the {name} mix has negative tonnes")
        if sum(c.tonnes for c in cells.values()) <= 0:
            raise EmissionsError(f"the {name} mix needs positive tonnes")
    base_cells = {k: v for k, v in baseline.items() if v.tonnes > 0}
    win_cells = {k: v for k, v in window.items() if v.tonnes > 0}
    base, win = _conditionals(base_cells, depth), _conditionals(win_cells, depth)
    base_i = {k: v.intensity for k, v in base_cells.items()}
    win_i = {k: v.intensity for k, v in win_cells.items()}
    factors = [*dimensions, *components]
    n = len(factors)

    def mix(switched: frozenset[str]) -> float:
        shares = [
            (win[i], base[i]) if d in switched else (base[i], win[i])
            for i, d in enumerate(dimensions)
        ]
        parts = {c: (win_i, base_i) if c in switched else (base_i, win_i) for c in components}
        return _mix(shares, parts)

    values = {
        frozenset(subset): mix(frozenset(subset))
        for size in range(n + 1)
        for subset in combinations(factors, size)
    }
    effects = {}
    for factor in factors:
        others = [f for f in factors if f != factor]
        effects[factor] = sum(
            factorial(size)
            * factorial(n - size - 1)
            / factorial(n)
            * (values[frozenset(subset) | {factor}] - values[frozenset(subset)])
            for size in range(n)
            for subset in combinations(others, size)
        )
    return MixDecomposition(
        baseline=values[frozenset()], window=values[frozenset(factors)], effects=effects
    )
