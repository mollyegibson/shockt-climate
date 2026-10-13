"""Shares of tonnage, diversion rates between windows, and summaries of monthly values by window."""

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date


class ShareError(Exception):
    """Shares can't be formed from the values given."""


def shares[K: Hashable](values: Mapping[K, float]) -> dict[K, float]:
    """Each key's share of the total."""
    total = sum(values.values())
    if total <= 0:
        raise ShareError(f"shares need a positive total, got {total}")
    return {key: value / total for key, value in values.items()}


def share_change[K: Hashable](
    baseline: Mapping[K, float], window: Mapping[K, float]
) -> dict[K, float]:
    """Each category's change in share from `baseline` to `window`; a category missing from one
    side has a share of 0 there."""
    return {key: window.get(key, 0.0) - baseline.get(key, 0.0) for key in {*baseline, *window}}


def diversion_rate(s_from_baseline: float, s_to_baseline: float, s_to_response: float) -> float:
    """The fraction of the `from` category's baseline tonnage that moved to the `to` category:
    (s_to,response − s_to,baseline) / s_from,baseline. Negative means a diversion the other way."""
    if s_from_baseline <= 0:
        raise ShareError("a diversion rate needs the source category's baseline share above 0")
    return (s_to_response - s_to_baseline) / s_from_baseline


@dataclass(frozen=True)
class Window:
    """A named range of whole months, both ends included."""

    name: str
    first: date
    last: date

    def __post_init__(self) -> None:
        if self.first.day != 1 or self.last.day != 1:
            raise ValueError(f"window {self.name} must start and end on the first of a month")
        if self.first > self.last:
            raise ValueError(f"window {self.name} starts after it ends")

    def contains(self, month: date) -> bool:
        return self.first <= month <= self.last


@dataclass(frozen=True)
class WindowSummary:
    mean: float
    """Mean of the monthly values, weighted by the monthly weights."""
    low: float
    high: float
    months: int


def window_summary(
    values: Mapping[date, float],
    windows: Iterable[Window],
    weights: Mapping[date, float] | None = None,
) -> dict[str, WindowSummary]:
    """For each window, the weighted mean, lowest and highest of the monthly values inside it.
    Windows with no month in `values` are left out."""
    result = {}
    for window in windows:
        months = [m for m in values if window.contains(m)]
        if not months:
            continue
        w = {m: (weights[m] if weights is not None else 1.0) for m in months}
        total = sum(w.values())
        if total <= 0:
            raise ShareError(f"window {window.name} has no weight")
        result[window.name] = WindowSummary(
            mean=sum(values[m] * w[m] for m in months) / total,
            low=min(values[m] for m in months),
            high=max(values[m] for m in months),
            months=len(months),
        )
    return result
