from datetime import date

import pytest

from shockt.cli import _already_loaded
from shockt.months import MonthRange


def test_resolve_ends_at_the_current_month_when_no_end_is_set() -> None:
    months = MonthRange.resolve("2022-01", None, date(2026, 10, 12))

    assert months == MonthRange("2022-01", "2026-10")


def test_in_year_clips_the_range_to_one_calendar_year() -> None:
    months = MonthRange("2022-03", "2024-08")

    assert list(months.years()) == [2022, 2023, 2024]
    assert months.in_year(2022) == MonthRange("2022-03", "2022-12")
    assert months.in_year(2023) == MonthRange("2023-01", "2023-12")
    assert months.in_year(2024) == MonthRange("2024-01", "2024-08")


def test_contains_compares_by_month() -> None:
    months = MonthRange("2023-02", "2023-03")

    assert months.contains(date(2023, 3, 31))
    assert not months.contains(date(2023, 1, 31))
    assert not months.contains(date(2023, 4, 1))


@pytest.mark.parametrize(("first", "last"), [("2023-13", "2023-12"), ("2023-1", "2023-12")])
def test_malformed_months_are_rejected(first: str, last: str) -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        MonthRange(first, last)


def test_a_range_that_ends_before_it_starts_is_rejected() -> None:
    with pytest.raises(ValueError, match="after it ends"):
        MonthRange("2024-02", "2024-01")


def test_a_year_is_already_loaded_only_with_the_same_months_and_params() -> None:
    months = MonthRange("2023-01", "2023-12")
    loaded = {"first_month": "2023-01", "last_month": "2023-12", "origin_iso3": ["MEX", "TWN"]}

    assert _already_loaded(loaded, months, origin_iso3=["MEX", "TWN"])
    assert not _already_loaded(loaded, months, origin_iso3=["CHN", "MEX", "TWN"])
    assert not _already_loaded(loaded, MonthRange("2023-01", "2023-06"), origin_iso3=["MEX", "TWN"])
    assert not _already_loaded(None, months)
