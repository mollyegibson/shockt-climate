"""Shock windows found from a monthly series, and whether a route uses a passage."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal


class ShockDatingError(Exception):
    """Shock windows can't be found from the values given."""


@dataclass(frozen=True)
class OutsideRange:
    """The months after a baseline that fall outside its range, as runs of months."""

    baseline_low: float
    baseline_high: float
    runs: tuple[tuple[date, date], ...]
    """First and last month of each run, both included."""


def _next_month(month: date) -> date:
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def months_outside_range(
    series: Mapping[date, float],
    baseline_first: date,
    baseline_last: date,
    side: Literal["below", "above"],
    max_gap: int,
) -> OutsideRange:
    """The runs of months after the baseline whose value is below (or above) the lowest (highest)
    baseline value. Up to `max_gap` consecutive months back inside the range don't end a run; a run
    starts and ends on a month outside the range. The series must have every month from the
    baseline's first to its own last."""
    if max_gap < 0:
        raise ShockDatingError("max_gap can't be negative")
    if any(m.day != 1 for m in series):
        raise ShockDatingError("months must be the first of the month")
    if not series:
        raise ShockDatingError("the series is empty")
    month, last = baseline_first, max(series)
    while month <= last:
        if month not in series:
            raise ShockDatingError(f"the series has no value for {month:%Y-%m}")
        month = _next_month(month)
    baseline = [v for m, v in series.items() if baseline_first <= m <= baseline_last]
    if not baseline:
        raise ShockDatingError("the baseline has no months")
    low, high = min(baseline), max(baseline)

    def outside(value: float) -> bool:
        return value < low if side == "below" else value > high

    runs: list[tuple[date, date]] = []
    current: tuple[date, date] | None = None
    gap = 0
    for month in sorted(m for m in series if m > baseline_last):
        if outside(series[month]):
            current = (current[0], month) if current else (month, month)
            gap = 0
        elif current is not None:
            gap += 1
            if gap > max_gap:
                runs.append(current)
                current, gap = None, 0
    if current is not None:
        runs.append(current)
    return OutsideRange(baseline_low=low, baseline_high=high, runs=tuple(runs))


def passage_used(open_km: float, closed_km: float, tolerance_km: float) -> bool:
    """Whether a route uses a passage: closing it makes the route longer by more than
    `tolerance_km`. A closed route can't be shorter than the open one."""
    if tolerance_km < 0:
        raise ShockDatingError("tolerance_km can't be negative")
    if closed_km < open_km - tolerance_km:
        raise ShockDatingError(
            f"closing a passage shortened the route ({open_km} km open, {closed_km} km closed)"
        )
    return closed_km - open_km > tolerance_km
