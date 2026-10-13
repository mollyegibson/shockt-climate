import pytest
from pydantic import ValidationError

from shockt_engine import (
    Factor,
    FactorSelectionError,
    LegFactor,
    load_leg_factors,
    select_factor,
    select_factors,
)


def factor(
    variant: str,
    mode: str,
    source: str = "uk_desnz",
    *,
    vehicle_type: str | None = None,
    size_class: str | None = None,
    haul: str | None = None,
    radiative_forcing: bool | None = None,
    wtw_kg_co2e_per_tkm: float | None = 1.0,
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
        wtw_kg_co2e_per_tkm=wtw_kg_co2e_per_tkm,
    )


FACTORS = [
    factor(
        "Container ship / Average", "ocean", vehicle_type="container_ship", size_class="average"
    ),
    factor(
        "Container ship / 8000+ TEU",
        "ocean",
        vehicle_type="container_ship",
        size_class="8000_plus_teu",
    ),
    factor(
        "Freight flights / International / With RF",
        "air",
        vehicle_type="freight_flight",
        haul="international",
        radiative_forcing=True,
    ),
    factor(
        "Freight flights / International / Without RF",
        "air",
        vehicle_type="freight_flight",
        haul="international",
        radiative_forcing=False,
    ),
    factor("Rail / Freight train", "rail", vehicle_type="rail"),
    factor(
        "Medium- and Heavy-Duty Truck",
        "truck",
        source="epa_hub",
        vehicle_type="medium_heavy_duty_truck",
    ),
    factor("Rail", "rail", source="epa_hub", vehicle_type="rail"),
]


def test_committed_leg_factors_name_exactly_one_factor_per_mode() -> None:
    chosen = select_factors(FACTORS, load_leg_factors())

    assert {mode: f.variant for mode, f in chosen.items()} == {
        "ocean": "Container ship / Average",
        "air": "Freight flights / International / With RF",
        "truck": "Medium- and Heavy-Duty Truck",
        "rail": "Rail",
    }


def test_settings_that_match_several_factors_fail() -> None:
    choice = LegFactor(source="uk_desnz", vehicle_type="freight_flight", haul="international")

    with pytest.raises(FactorSelectionError, match="With RF"):
        select_factor(FACTORS, "air", choice)


def test_settings_that_match_no_factor_fail() -> None:
    choice = LegFactor(source="uk_desnz", vehicle_type="container_ship", size_class="0_999_teu")

    with pytest.raises(FactorSelectionError, match="none"):
        select_factor(FACTORS, "ocean", choice)


def test_a_factor_without_a_well_to_wheel_value_is_never_chosen() -> None:
    blank = [
        factor("Rail", "rail", source="epa_hub", vehicle_type="rail", wtw_kg_co2e_per_tkm=None)
    ]

    with pytest.raises(FactorSelectionError):
        select_factor(blank, "rail", LegFactor(source="epa_hub", vehicle_type="rail"))


def test_leg_factors_reject_a_vehicle_type_outside_the_vocabulary() -> None:
    with pytest.raises(ValidationError, match="vehicle_type"):
        LegFactor.model_validate({"source": "uk_desnz", "vehicle_type": "container ship"})


def test_leg_factors_reject_a_size_class_that_is_not_a_token() -> None:
    with pytest.raises(ValidationError, match="size_class"):
        LegFactor.model_validate(
            {"source": "uk_desnz", "vehicle_type": "container_ship", "size_class": "8000+ TEU"}
        )
