from datetime import date
from pathlib import Path

import polars as pl
import pytest
from shockt_engine import Window

from shockt_analysis import cases

WINDOWS = [
    Window("baseline", date(2024, 1, 1), date(2024, 2, 1)),
    Window("response", date(2024, 3, 1), date(2024, 3, 1)),
]


def supply_frame() -> pl.DataFrame:
    rows = [
        (date(2024, 1, 1), "5830", "TWN", "847150", "air", 10.0),
        (date(2024, 1, 1), "2010", "MEX", "847150", "truck", 30.0),
        (date(2024, 2, 1), "2010", "MEX", "847150", "truck", 30.0),
        (date(2024, 3, 1), "5830", "TWN", "847150", "air", 30.0),
        (date(2024, 3, 1), "2010", "MEX", "847150", "truck", 10.0),
        (date(2024, 3, 1), "5490", "THA", "847150", "air", 0.0),
        (date(2024, 4, 1), "5830", "TWN", "847150", "air", 99.0),
    ]
    return pl.DataFrame(
        rows, schema=["month", "census_cty_code", "iso3", "hs6", "mode", "weight_t"], orient="row"
    ).with_columns(
        pl.col("weight_t").alias("weight_t_low"), pl.col("weight_t").alias("weight_t_high")
    )


def test_load_windows_reads_months(tmp_path: Path) -> None:
    path = tmp_path / "windows.yaml"
    path.write_text(
        "windows:\n  - id: baseline\n    first_month: 2024-01\n    last_month: 2025-01\n"
    )

    assert cases.load_windows(path) == [Window("baseline", date(2024, 1, 1), date(2025, 1, 1))]


def test_with_window_leaves_months_outside_every_window_null() -> None:
    windowed = cases.with_window(supply_frame(), WINDOWS)

    assert windowed.filter(pl.col("month") == date(2024, 4, 1))["window"].item() is None
    assert windowed.filter(pl.col("month") == date(2024, 3, 1))["window"].unique().to_list() == [
        "response"
    ]


def test_window_shares_are_within_each_window() -> None:
    monthly = cases.monthly_supply(supply_frame(), ["847150"], ["TWN", "MEX"])

    shares = cases.window_shares(monthly, WINDOWS, ["origin_group"])

    baseline = dict(
        shares.filter(pl.col("window") == "baseline").select("origin_group", "share").iter_rows()
    )
    assert baseline == pytest.approx({"TWN": 10 / 70, "MEX": 60 / 70})


def test_mix_by_month_weights_lanes_by_tonnes() -> None:
    lanes = pl.DataFrame(
        {
            "window": ["baseline", "baseline", "response", "response"],
            "iso3": ["TWN", "MEX", "TWN", "MEX"],
            "mode": ["air", "truck", "air", "truck"],
            "kg_co2e_per_t": [12_000.0, 200.0, 12_000.0, 200.0],
        }
    )

    mix = cases.mix_by_month(supply_frame(), ["847150"], WINDOWS, lanes)

    march = mix.filter(pl.col("month") == date(2024, 3, 1))
    assert march["kg_co2e_per_t"].item() == pytest.approx((30 * 12_000 + 10 * 200) / 40)
    assert march["measured_share"].item() == pytest.approx(1.0)


def test_international_legs_are_the_engines_first_leg_of_each_mode() -> None:
    """Each lane mode's first leg reaches the US border; the engine names them."""
    from shockt_engine import LaneInputs, lane_legs

    weights = {
        "departure_airport": {"a": 1.0},
        "air_gateway": {"g": 1.0},
        "departure_port": {"p": 1.0},
        "arrival_seaport": {"s": 1.0},
        "border_crossing": {"x": 1.0},
        "destination_state": {"d": 1.0},
    }
    inputs = LaneInputs(
        weights=weights,
        distances={
            "air": {("a", "g"): 1.0},
            "sea": {("p", "s"): 1.0},
            "road": {("g", "d"): 1.0, ("s", "d"): 1.0, ("x", "d"): 1.0, ("m", "x"): 1.0},
            "rail": {("x", "d"): 1.0},
        },
        factors={"air": 1.0, "ocean": 1.0, "truck": 1.0, "rail": 1.0},
        crossing_plants={"x": "m"},
    )
    for mode in ("air", "vessel", "truck", "rail"):
        legs = lane_legs(mode, inputs).legs
        assert legs[0].name in cases.INTERNATIONAL_LEGS
        assert all(leg.name not in cases.INTERNATIONAL_LEGS for leg in legs[1:])


def test_leg_frame_parts_split_border_and_inland_legs() -> None:
    legs = pl.DataFrame(
        {"leg": ["port → seaport", "seaport → state"], "kg_co2e_per_t": [400.0, 150.0]}
    )

    assert cases.leg_frame_parts(legs) == {"international": 400.0, "inland": 150.0}


def test_reweight_air_recomputes_only_the_suspect_months() -> None:
    supply = supply_frame()
    air = pl.DataFrame(
        {
            "month": [date(2024, 1, 1), date(2024, 3, 1)],
            "census_cty_code": ["5830", "5830"],
            "hs6": ["847150", "847150"],
            "value_usd": [4_000.0, 12_000.0],
            "weight_t": [10.0, 0.03],
        }
    )

    suspect = cases.suspect_air_months(air, 395, 410)
    reweighted = cases.reweight_air(supply, suspect, 200.0)

    assert suspect["month"].to_list() == [date(2024, 3, 1)]
    march = reweighted.filter((pl.col("month") == date(2024, 3, 1)) & (pl.col("iso3") == "TWN"))
    assert march["weight_t"].to_list() == [pytest.approx(0.06)]
    assert reweighted["weight_t"].sum() == pytest.approx(supply["weight_t"].sum() - 30 + 0.06)


def test_reweight_air_fails_for_an_origin_without_a_ratio() -> None:
    suspect = pl.DataFrame(
        {
            "month": [date(2024, 3, 1)],
            "census_cty_code": ["5830"],
            "hs6": ["847150"],
            "value_usd": [1.0],
        }
    )
    ratios = pl.DataFrame({"census_cty_code": ["2010"], "usd_per_kg": [300.0]})

    with pytest.raises(ValueError, match="5830"):
        cases.reweight_air(supply_frame(), suspect, ratios)


def test_reweight_air_uses_the_default_for_an_origin_without_a_ratio() -> None:
    suspect = pl.DataFrame(
        {
            "month": [date(2024, 3, 1)],
            "census_cty_code": ["5830"],
            "hs6": ["847150"],
            "value_usd": [6_000.0],
        }
    )
    ratios = pl.DataFrame({"census_cty_code": ["2010"], "usd_per_kg": [300.0]})

    reweighted = cases.reweight_air(supply_frame(), suspect, ratios, default=200.0)

    march = reweighted.filter((pl.col("month") == date(2024, 3, 1)) & (pl.col("iso3") == "TWN"))
    assert march["weight_t"].to_list() == [pytest.approx(0.03)]
