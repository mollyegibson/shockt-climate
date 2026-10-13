from datetime import date

import pytest

from shockt_engine import ShockDatingError, months_outside_range, passage_used


def months(*values: float, start: date = date(2023, 1, 1)) -> dict[date, float]:
    """`values` for consecutive months from `start`."""
    series = {}
    month = start
    for value in values:
        series[month] = value
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return series


def test_a_run_below_the_baseline_range_is_a_window() -> None:
    series = months(10, 12, 11, 9, 8, 11, 12)

    result = months_outside_range(
        series, date(2023, 1, 1), date(2023, 3, 1), side="below", max_gap=0
    )

    assert (result.baseline_low, result.baseline_high) == (10, 12)
    assert result.runs == ((date(2023, 4, 1), date(2023, 5, 1)),)


def test_a_gap_up_to_max_gap_doesnt_end_a_run() -> None:
    series = months(10, 12, 11, 9, 11, 8, 11, 11, 7)

    bridged = months_outside_range(
        series, date(2023, 1, 1), date(2023, 3, 1), side="below", max_gap=1
    )
    split = months_outside_range(
        series, date(2023, 1, 1), date(2023, 3, 1), side="below", max_gap=0
    )

    assert bridged.runs == (
        (date(2023, 4, 1), date(2023, 6, 1)),
        (date(2023, 9, 1), date(2023, 9, 1)),
    )
    assert len(split.runs) == 3


def test_an_open_run_ends_at_the_last_month() -> None:
    series = months(10, 12, 13, 14, 15)

    result = months_outside_range(
        series, date(2023, 1, 1), date(2023, 2, 1), side="above", max_gap=0
    )

    assert result.runs == ((date(2023, 3, 1), date(2023, 5, 1)),)


def test_baseline_months_are_never_in_a_run() -> None:
    series = months(10, 5, 12, 11)

    result = months_outside_range(
        series, date(2023, 1, 1), date(2023, 2, 1), side="below", max_gap=0
    )

    assert result.runs == ()


def test_a_missing_month_fails() -> None:
    series = months(10, 12, 11)
    del series[date(2023, 2, 1)]

    with pytest.raises(ShockDatingError, match="2023-02"):
        months_outside_range(series, date(2023, 1, 1), date(2023, 1, 1), "below", max_gap=0)


def test_a_passage_is_used_when_closing_it_lengthens_the_route() -> None:
    assert passage_used(open_km=18_000, closed_km=24_000, tolerance_km=1)
    assert not passage_used(open_km=18_000, closed_km=18_000.5, tolerance_km=1)


def test_closing_a_passage_cant_shorten_a_route() -> None:
    with pytest.raises(ShockDatingError):
        passage_used(open_km=18_000, closed_km=17_000, tolerance_km=1)
