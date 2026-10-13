"""Which emission factor each mode's legs use: the choice in `config/leg_factors.yaml`, applied to
the factors `core.ref_emission_factors` publishes. A mode whose settings match no factor, or more
than one, is an error, so a changed workbook or a typo can't silently pick the wrong number."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ENGINE_ROOT = Path(__file__).resolve().parents[2]
LEG_FACTORS_FILE = ENGINE_ROOT / "config" / "leg_factors.yaml"

Mode = Literal["ocean", "air", "truck", "rail"]
VehicleType = Literal[
    "container_ship",
    "bulk_carrier",
    "general_cargo",
    "ropax_ferry",
    "refrigerated_cargo",
    "roro_ferry",
    "vehicle_carrier",
    "chemical_tanker",
    "crude_tanker",
    "lng_tanker",
    "lpg_tanker",
    "products_tanker",
    "freight_flight",
    "rail",
    "hgv",
    "hgv_refrigerated",
    "van",
    "medium_heavy_duty_truck",
    "aircraft",
    "waterborne_craft",
]
"""The `vehicle_type` values `core.ref_emission_factors` gives the UK and EPA factors."""


class FactorSelectionError(Exception):
    """A mode's settings match no emission factor, or more than one."""


class LegFactor(BaseModel):
    """Which factor a mode's legs use, by the factor's attributes; an attribute left out doesn't
    narrow the match."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["uk_desnz", "epa_hub"]
    vehicle_type: VehicleType
    size_class: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    haul: Literal["domestic_uk", "short_haul_uk", "long_haul_uk", "international"] | None = None
    radiative_forcing: bool | None = None


class LegFactors(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ocean: LegFactor
    air: LegFactor
    truck: LegFactor
    rail: LegFactor

    def for_mode(self, mode: Mode) -> LegFactor:
        choice: LegFactor = getattr(self, mode)
        return choice


@dataclass(frozen=True)
class Factor:
    """One row of `core.ref_emission_factors`: kg CO2e per tonne-km, well-to-wheel."""

    source: str
    source_row_id: str
    mode: str
    variant: str
    vehicle_type: str | None
    size_class: str | None
    haul: str | None
    radiative_forcing: bool | None
    wtw_kg_co2e_per_tkm: float | None


def load_leg_factors(path: Path = LEG_FACTORS_FILE) -> LegFactors:
    return LegFactors.model_validate(yaml.safe_load(path.read_text()))


def _matches(factor: Factor, mode: Mode, choice: LegFactor) -> bool:
    return (
        factor.mode == mode
        and factor.source == choice.source
        and factor.vehicle_type == choice.vehicle_type
        and (choice.size_class is None or factor.size_class == choice.size_class)
        and (choice.haul is None or factor.haul == choice.haul)
        and (
            choice.radiative_forcing is None or factor.radiative_forcing == choice.radiative_forcing
        )
        and factor.wtw_kg_co2e_per_tkm is not None
    )


def select_factor(factors: Iterable[Factor], mode: Mode, choice: LegFactor) -> Factor:
    """The one factor with a well-to-wheel value that `choice` names for `mode`."""
    matches = [f for f in factors if _matches(f, mode, choice)]
    if len(matches) != 1:
        found = [f.variant for f in matches] or "none"
        settings = choice.model_dump(exclude_none=True)
        raise FactorSelectionError(f"{mode}: {settings} matches {found}")
    return matches[0]


def select_factors(factors: Iterable[Factor], choices: LegFactors) -> Mapping[Mode, Factor]:
    """The factor each mode uses; fails on the first mode that matches none or several."""
    rows = list(factors)
    modes: tuple[Mode, ...] = ("ocean", "air", "truck", "rail")
    return {mode: select_factor(rows, mode, choices.for_mode(mode)) for mode in modes}
