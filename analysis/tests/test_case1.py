from datetime import date
from pathlib import Path

import polars as pl
import pytest
from shockt_engine import Window

from shockt_analysis import case1

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

    assert case1.load_windows(path) == [Window("baseline", date(2024, 1, 1), date(2025, 1, 1))]


def test_with_window_leaves_months_outside_every_window_null() -> None:
    windowed = case1.with_window(supply_frame(), WINDOWS)

    assert windowed.filter(pl.col("month") == date(2024, 4, 1))["window"].item() is None
    assert windowed.filter(pl.col("month") == date(2024, 3, 1))["window"].unique().to_list() == [
        "response"
    ]


def test_window_shares_are_within_each_window() -> None:
    monthly = case1.monthly_supply(supply_frame(), ["847150"], ["TWN", "MEX"])

    shares = case1.window_shares(monthly, WINDOWS, ["origin_group"])

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

    mix = case1.mix_by_month(supply_frame(), ["847150"], WINDOWS, lanes)

    march = mix.filter(pl.col("month") == date(2024, 3, 1))
    assert march["kg_co2e_per_t"].item() == pytest.approx((30 * 12_000 + 10 * 200) / 40)
    assert march["measured_share"].item() == pytest.approx(1.0)
