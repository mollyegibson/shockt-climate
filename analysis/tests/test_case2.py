from datetime import date

import polars as pl
import pytest
from shockt_engine import Window

from shockt_analysis import case2


def transits(rows: list[tuple[date, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "month": m,
                "chokepoint_id": "chokepoint2",
                "chokepoint_name": "Panama Canal",
                "days_reported": days,
                "n_total": n,
                "n_container": n,
            }
            for m, days, n in rows
        ]
    )


def test_daily_series_is_per_reported_day_and_drops_a_partial_last_month() -> None:
    frame = transits(
        [(date(2024, 1, 1), 31, 310), (date(2024, 2, 1), 29, 290), (date(2024, 3, 1), 4, 40)]
    )

    series = case2.daily_series(frame, "chokepoint2", "n_total")

    assert series == {date(2024, 1, 1): 10.0, date(2024, 2, 1): 10.0}


def test_daily_series_fails_on_a_partial_month_in_the_middle() -> None:
    frame = transits([(date(2024, 1, 1), 20, 200), (date(2024, 2, 1), 29, 290)])

    with pytest.raises(ValueError, match="2024-01"):
        case2.daily_series(frame, "chokepoint2", "n_total")


def test_runs_after_starts_by_are_reported_not_windows() -> None:
    days = [31, 28, 31, 30, 31, 30]
    values = [10, 10, 5, 10, 10, 5]
    frame = transits(
        [
            (date(2023, i + 1, 1), d, v * d)
            for i, (d, v) in enumerate(zip(days, values, strict=True))
        ]
    )
    case = case2.CaseWindows(
        baseline=Window("baseline", date(2023, 1, 1), date(2023, 2, 1)),
        rules=(case2.ShockRule("drought", "chokepoint2", "n_total", "below", 0, date(2023, 4, 1)),),
    )

    windows, found = case2.shock_windows(frame, case)

    assert windows == [Window("drought", date(2023, 3, 1), date(2023, 3, 1))]
    assert found["drought"]["later_runs"] == [["2023-06", "2023-06"]]


def test_passage_flags_mark_pairs_a_closure_lengthens() -> None:
    flags = case2.passage_flags(
        {("kao", "nyc"): 20_000.0, ("bom", "nyc"): 16_000.0},
        {"panama": {("kao", "nyc"): 24_000.0, ("bom", "nyc"): 16_000.0}},
        tolerance_km=1.0,
    )

    used = dict(zip(flags["departure"], flags["uses_panama"], strict=True))
    assert used == {"kao": True, "bom": False}


def test_quarter_share_is_the_coasts_share_of_the_states_tonnage() -> None:
    frame = pl.DataFrame(
        {
            "quarter": [date(2024, 1, 1)] * 3,
            "state": ["VA", "VA", "CA"],
            "unlading_coast_region": ["west", "east", "west"],
            "weight_t": [1.0, 3.0, 9.0],
        }
    )

    assert case2.quarter_share(frame, ["VA"], "west") == {date(2024, 1, 1): 0.25}
