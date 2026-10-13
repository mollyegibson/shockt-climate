"""The steps of the Case 2 notebook that are its own: shock windows from chokepoint transits, which
lanes use which passage, coast-of-arrival lanes, and the cells of the supply mix. Shared steps
are in `cases`; the arithmetic is the engine's."""

import calendar
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl
import yaml
from shockt_engine import (
    EmissionsError,
    InlandMode,
    LaneMode,
    LaneResult,
    MixCell,
    Window,
    lane_legs,
    months_outside_range,
    passage_used,
    weighted_leg_distance,
)

from shockt_analysis.cases import INTERNATIONAL_LEGS, LaneContext, lane_inputs

COASTS = ("east", "gulf", "west")
"""The US coast regions a lane can arrive on; inland, noncontiguous and unknown ports are
reported as left out."""

SCENARIOS = {
    "panama": "panama_closed",
    "red_sea": "red_sea_closed",
}
"""Passage → the `searoute` scenario with it closed."""


@dataclass(frozen=True)
class ShockRule:
    shock: str
    chokepoint_id: str
    series: Literal["n_total", "n_container"]
    side: Literal["below", "above"]
    max_gap: int
    starts_by: date
    """Runs starting after this month belong to later events, not this case."""


@dataclass(frozen=True)
class CaseWindows:
    baseline: Window
    rules: tuple[ShockRule, ...]


def _month(text: str) -> date:
    year, month = str(text).split("-")
    return date(int(year), int(month), 1)


def load_case_windows(path: Path) -> CaseWindows:
    """The baseline months and each shock's rule from a rule-based `shock_windows.yaml`."""
    data = yaml.safe_load(path.read_text())
    base = data["baseline"]
    rules = []
    for shock in data["shocks"]:
        if shock["method"] != "rule":
            raise ValueError(f"shock {shock['id']} isn't set by a rule")
        rule = shock["rule"]
        rules.append(
            ShockRule(
                shock=shock["id"],
                chokepoint_id=rule["chokepoint_id"],
                series=rule["series"],
                side=rule["side"],
                max_gap=int(rule["max_gap"]),
                starts_by=_month(rule["starts_by"]),
            )
        )
    return CaseWindows(
        baseline=Window("baseline", _month(base["first_month"]), _month(base["last_month"])),
        rules=tuple(rules),
    )


def daily_series(transits: pl.DataFrame, chokepoint_id: str, series: str) -> dict[date, float]:
    """Transits per reported day for one chokepoint, for the months PortWatch reported in full.
    A month reported only in part (the latest, usually) is left out; one in the middle is an
    error, because the windows need every month."""
    rows = transits.filter(pl.col("chokepoint_id") == chokepoint_id).sort("month")
    if rows.is_empty():
        raise ValueError(f"no transits for {chokepoint_id}")
    values: dict[date, float] = {}
    months = rows["month"].to_list()
    for i, row in enumerate(rows.iter_rows(named=True)):
        month: date = row["month"]
        full = row["days_reported"] == calendar.monthrange(month.year, month.month)[1]
        if not full:
            if i == len(months) - 1:
                continue
            raise ValueError(f"{chokepoint_id} {month:%Y-%m} is reported for part of the month")
        values[month] = row[series] / row["days_reported"]
    return values


def shock_windows(
    transits: pl.DataFrame, case: CaseWindows
) -> tuple[list[Window], dict[str, dict[str, object]]]:
    """Each shock's windows from its rule, and per shock the baseline range and the runs found. Runs
    starting after the rule's `starts_by` are reported but get no window. A shock with several
    runs in the case gets one window per run, numbered after the first."""
    windows: list[Window] = []
    found: dict[str, dict[str, object]] = {}
    for rule in case.rules:
        series = daily_series(transits, rule.chokepoint_id, rule.series)
        result = months_outside_range(
            series, case.baseline.first, case.baseline.last, rule.side, rule.max_gap
        )
        in_case = [run for run in result.runs if run[0] <= rule.starts_by]
        for i, (first, last) in enumerate(in_case):
            windows.append(Window(rule.shock if i == 0 else f"{rule.shock}_{i + 1}", first, last))
        found[rule.shock] = {
            "chokepoint_id": rule.chokepoint_id,
            "series": rule.series,
            "baseline_low_per_day": round(result.baseline_low, 2),
            "baseline_high_per_day": round(result.baseline_high, 2),
            "runs": [[f"{a:%Y-%m}", f"{b:%Y-%m}"] for a, b in in_case],
            "later_runs": [
                [f"{a:%Y-%m}", f"{b:%Y-%m}"] for a, b in result.runs if a > rule.starts_by
            ],
            "last_month": f"{max(series):%Y-%m}",
        }
    return windows, found


def passage_flags(
    open_km: Mapping[tuple[str, str], float],
    closed_km: Mapping[str, Mapping[tuple[str, str], float]],
    tolerance_km: float,
) -> pl.DataFrame:
    """For each departure port → US seaport pair, whether its route uses each passage."""
    rows = []
    for pair, km in open_km.items():
        row: dict[str, object] = {"departure": pair[0], "arrival": pair[1], "open_km": km}
        for passage, distances in closed_km.items():
            row[f"uses_{passage}"] = passage_used(km, distances[pair], tolerance_km)
        rows.append(row)
    return pl.DataFrame(rows)


def lane_passage_shares(
    context: LaneContext,
    flags: pl.DataFrame,
    census_cty_code: str,
    iso3: str,
    codes: Sequence[str],
    coast: str,
    window: Window,
) -> dict[str, float]:
    """The share of one origin's vessel lane to `coast` whose port pairs use each passage, with the
    pairs weighted as in the lane's sea leg (departure weight × arrival weight)."""
    inputs = lane_inputs(context, census_cty_code, iso3, codes, "vessel", window, coast=coast)
    departures = inputs.weights.get("departure_port", {})
    arrivals = inputs.weights.get("arrival_seaport", {})
    total = sum(departures.values()) * sum(arrivals.values())
    if total <= 0:
        return {}
    by_pair = {(r["departure"], r["arrival"]): r for r in flags.iter_rows(named=True)}
    shares: dict[str, float] = {}
    for passage in (c.removeprefix("uses_") for c in flags.columns if c.startswith("uses_")):
        used = sum(
            dw * aw
            for d, dw in departures.items()
            for a, aw in arrivals.items()
            if (d, a) in by_pair and by_pair[(d, a)][f"uses_{passage}"]
        )
        shares[passage] = used / total
    return shares


def modelled_sea_km(
    context: LaneContext,
    sea_by_scenario: Mapping[str, Mapping[tuple[str, str], float]],
    census_cty_code: str,
    iso3: str,
    codes: Sequence[str],
    coast: str,
    window: Window,
) -> dict[str, float]:
    """One origin's sea leg to `coast` in each `searoute` scenario, over the lane's port pairs;
    empty when the lane has no ports in the window."""
    inputs = lane_inputs(context, census_cty_code, iso3, codes, "vessel", window, coast=coast)
    departures = inputs.weights.get("departure_port", {})
    arrivals = inputs.weights.get("arrival_seaport", {})
    if sum(departures.values()) <= 0 or sum(arrivals.values()) <= 0:
        return {}
    return {
        scenario: weighted_leg_distance(distances, departures, arrivals).km
        for scenario, distances in sea_by_scenario.items()
    }


def lane_result(
    context: LaneContext,
    census_cty_code: str,
    iso3: str,
    codes: Sequence[str],
    mode: LaneMode,
    window: Window,
    coast: str,
    inland: InlandMode = "truck",
    states: Collection[str] | None = None,
) -> tuple[LaneResult | None, str | None]:
    """A coast-of-arrival lane's legs, or None and the reason it can't be measured."""
    try:
        inputs = lane_inputs(
            context, census_cty_code, iso3, codes, mode, window, coast=coast, states=states
        )
        return lane_legs(mode, inputs, inland=inland), None
    except EmissionsError as exc:
        return None, str(exc)


def intensity_parts(result: LaneResult) -> dict[str, float]:
    """A lane's emissions per tonne in two parts: the legs that bring freight to the US
    (`international`) and the legs inside it (`inland`)."""
    return {
        "international": sum(
            leg.kg_co2e_per_t for leg in result.legs if leg.name in INTERNATIONAL_LEGS
        ),
        "inland": sum(
            leg.kg_co2e_per_t for leg in result.legs if leg.name not in INTERNATIONAL_LEGS
        ),
    }


def mix_cells(
    port_tonnes: pl.DataFrame,
    context: LaneContext,
    codes: Sequence[str],
    window: Window,
) -> tuple[dict[tuple[str, str, str], MixCell], pl.DataFrame]:
    """The supply mix's cells for one window: origin × arrival coast × mode, with tonnage from the
    port data and each lane's emissions per tonne. Also every cell's tonnage and, where a lane
    can't be measured or arrives off the three coasts, why it's left out."""
    cells = (
        port_tonnes.filter(
            pl.col("hs6").is_in(list(codes)) & pl.col("month").is_between(window.first, window.last)
        )
        .group_by("census_cty_code", "iso3", "coast_region", "mode")
        .agg(pl.col("weight_t").sum())
        .sort("iso3", "coast_region", "mode")
    )
    kept: dict[tuple[str, str, str], MixCell] = {}
    report = []
    for row in cells.iter_rows(named=True):
        coast = row["coast_region"]
        reason = None
        result = None
        if coast not in COASTS:
            reason = f"arrives on {coast}"
        else:
            result, reason = lane_result(
                context, row["census_cty_code"], row["iso3"], codes, row["mode"], window, coast
            )
        if result is not None:
            kept[(row["iso3"], coast, row["mode"])] = MixCell(
                row["weight_t"], intensity_parts(result)
            )
        report.append(
            {
                "window": window.name,
                "iso3": row["iso3"],
                "coast": coast,
                "mode": row["mode"],
                "weight_t": row["weight_t"],
                "kg_co2e_per_t": result.kg_co2e_per_t if result else None,
                "left_out": reason,
            }
        )
    return kept, pl.DataFrame(report)


def quarter_share(
    state_port: pl.DataFrame, states: Collection[str], coast: str
) -> dict[date, float]:
    """Each quarter's share of vessel tonnage bound for `states` that was unladen on `coast`."""
    part = state_port.filter(pl.col("state").is_in(list(states)))
    totals = part.group_by("quarter").agg(
        pl.col("weight_t").sum().alias("all"),
        pl.col("weight_t").filter(pl.col("unlading_coast_region") == coast).sum().alias("coast"),
    )
    return {
        r["quarter"]: r["coast"] / r["all"]
        for r in totals.sort("quarter").iter_rows(named=True)
        if r["all"] > 0
    }
