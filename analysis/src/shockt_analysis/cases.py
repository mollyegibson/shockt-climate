"""The steps the case notebooks share, from data frames to the engine and back: supply by window,
shares and their changes, lane emissions per tonne, the supply mix and the derived evidence
records. The arithmetic is the engine's; this module only shapes the data for it."""

import subprocess
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl
import yaml
from matplotlib.axes import Axes
from shockt_engine import (
    EmissionsError,
    LaneInputs,
    LaneMode,
    LaneResult,
    MixCell,
    MixDecomposition,
    Window,
    lane_legs,
    share_change,
    shares,
)

from shockt_analysis.settings import REPO_ROOT

OTHER = "other"

INTERNATIONAL_LEGS = frozenset({"airport → gateway", "port → seaport", "plant → crossing"})
"""Legs that bring freight to the US border; the rest run inside the US."""

LANE_NODE_MODES: Mapping[LaneMode, Mapping[str, str]] = {
    "air": {"departure_airport": "air", "air_gateway": "air", "destination_state": "air"},
    "vessel": {
        "departure_port": "vessel",
        "arrival_seaport": "vessel",
        "destination_state": "vessel",
    },
    "truck": {"mexico_plant": "truck", "border_crossing": "truck", "destination_state": "other"},
    "rail": {"mexico_plant": "rail", "border_crossing": "rail", "destination_state": "other"},
}
"""For each lane mode, the node kinds its legs use and the mode their weights are recorded in.
Destination states record overland freight as `other`, without the truck–rail split."""


def load_windows(path: Path) -> list[Window]:
    """The windows of a `shock_windows.yaml` file, in file order."""
    data = yaml.safe_load(path.read_text())
    return [
        Window(w["id"], _month(w["first_month"]), _month(w["last_month"])) for w in data["windows"]
    ]


def _month(text: str) -> date:
    year, month = text.split("-")
    return date(int(year), int(month), 1)


def with_window(df: pl.DataFrame, windows: Sequence[Window], column: str = "month") -> pl.DataFrame:
    """`df` with a `window` column naming the window each month falls in, or null."""
    expr = pl.lit(None, dtype=pl.String)
    for w in reversed(windows):
        expr = (
            pl.when(pl.col(column).is_between(w.first, w.last)).then(pl.lit(w.name)).otherwise(expr)
        )
    return df.with_columns(expr.alias("window"))


def with_origin_group(df: pl.DataFrame, named: Sequence[str]) -> pl.DataFrame:
    """`df` with an `origin_group` column: the ISO3 code for named origins, else `other`."""
    return df.with_columns(
        pl.when(pl.col("iso3").is_in(list(named)))
        .then(pl.col("iso3"))
        .otherwise(pl.lit(OTHER))
        .alias("origin_group")
    )


def monthly_supply(
    supply: pl.DataFrame, codes: Sequence[str], named: Sequence[str]
) -> pl.DataFrame:
    """Tonnes by month, origin group and mode for `codes`, with the low and high."""
    return (
        with_origin_group(supply.filter(pl.col("hs6").is_in(list(codes))), named)
        .group_by("month", "origin_group", "mode")
        .agg(pl.col("weight_t", "weight_t_low", "weight_t_high").sum())
        .sort("month", "origin_group", "mode")
    )


def window_shares(
    monthly: pl.DataFrame, windows: Sequence[Window], by: Sequence[str]
) -> pl.DataFrame:
    """Tonnes and share of each `by` category within each window."""
    totals = (
        with_window(monthly, windows)
        .drop_nulls("window")
        .group_by("window", *by)
        .agg(pl.col("weight_t").sum())
    )
    rows = []
    for window in [w.name for w in windows]:
        part = totals.filter(pl.col("window") == window)
        if part.is_empty():
            continue
        keys = [tuple(r[c] for c in by) for r in part.iter_rows(named=True)]
        window_shares_ = shares(dict(zip(keys, part["weight_t"].to_list(), strict=True)))
        for key, share in window_shares_.items():
            rows.append({"window": window, **dict(zip(by, key, strict=True)), "share": share})
    return totals.join(pl.DataFrame(rows), on=["window", *by]).sort("window", *by)


def share_changes(
    window_share_frame: pl.DataFrame, baseline: str, window: str, key: str
) -> dict[str, float]:
    """Each `key` category's change in share from `baseline` to `window`."""

    def of(name: str) -> dict[str, float]:
        part = window_share_frame.filter(pl.col("window") == name)
        return dict(zip(part[key].to_list(), part["share"].to_list(), strict=True))

    return share_change(of(baseline), of(window))


@dataclass(frozen=True)
class LaneContext:
    """Everything the lanes need besides the lane itself."""

    weights: pl.DataFrame
    observed_sea: pl.DataFrame
    distances: Mapping[str, Mapping[tuple[str, str], float]]
    factors: Mapping[str, float]
    crossing_plants: pl.DataFrame


def lane_inputs(
    context: LaneContext,
    census_cty_code: str,
    iso3: str,
    codes: Sequence[str],
    mode: LaneMode,
    window: Window,
    coast: str | None = None,
    states: Collection[str] | None = None,
) -> LaneInputs:
    """The node weights, distances and factors one origin's lane in `mode` uses in `window`.
    `coast` keeps only the US arrival nodes on that coast region, and the departure ports' share
    bound for it; `states` keeps only those destination states (two-letter codes)."""
    in_window = pl.col("month").is_between(window.first, window.last)
    weights = context.weights.filter(
        in_window
        & (pl.col("census_cty_code") == census_cty_code)
        & pl.col("hs6").is_in(list(codes))
    )
    by_kind: dict[str, dict[str, float]] = {}
    for kind, node_mode in LANE_NODE_MODES[mode].items():
        part = weights.filter((pl.col("kind") == kind) & (pl.col("mode") == node_mode))
        if coast is not None and kind == "departure_port":
            part = part.filter(pl.col("lane_coast_region") == coast)
        if coast is not None and kind in ("arrival_seaport", "air_gateway"):
            part = part.filter(pl.col("coast_region") == coast)
        if states is not None and kind == "destination_state":
            part = part.filter(pl.col("node_id").is_in([f"destination_state:{s}" for s in states]))
        part = part.group_by("node_id").agg(pl.col("weight_t").sum())
        by_kind[kind] = dict(
            zip(part["node_id"].to_list(), part["weight_t"].to_list(), strict=True)
        )
    observed = (
        context.observed_sea.filter(in_window & (pl.col("origin_iso3") == iso3))
        .group_by("arrival_node_id")
        .agg(
            (
                (pl.col("median_distance_km") * pl.col("n_voyages")).sum()
                / pl.col("n_voyages").sum()
            ).alias("km")
        )
    )
    plants = context.crossing_plants.filter(pl.col("hs6").is_in(list(codes)))
    crossing_plant: dict[str, str] = {}
    for crossing in plants["crossing_node_id"].unique().to_list():
        candidates = plants.filter(pl.col("crossing_node_id") == crossing)[
            "plant_node_id"
        ].to_list()
        crossing_plant[crossing] = Counter(candidates).most_common(1)[0][0]
    return LaneInputs(
        weights=by_kind,
        distances=context.distances,
        factors=context.factors,
        observed_sea=dict(
            zip(observed["arrival_node_id"].to_list(), observed["km"].to_list(), strict=True)
        ),
        crossing_plants=crossing_plant,
    )


def lane_intensities(
    supply: pl.DataFrame,
    codes: Sequence[str],
    windows: Sequence[Window],
    context: LaneContext,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Emissions per tonne of every origin's lane with tonnage in each window, and its legs.
    A lane whose legs can't be measured is listed with a null intensity and the reason."""
    lanes = (
        with_window(supply.filter(pl.col("hs6").is_in(list(codes))), windows)
        .drop_nulls("window")
        .group_by("window", "census_cty_code", "iso3", "mode")
        .agg(pl.col("weight_t").sum())
        .sort("window", "iso3", "mode")
    )
    by_name = {w.name: w for w in windows}
    lane_rows, leg_rows = [], []
    for lane in lanes.iter_rows(named=True):
        mode: LaneMode = lane["mode"]
        result: LaneResult | None = None
        problem = None
        try:
            inputs = lane_inputs(
                context, lane["census_cty_code"], lane["iso3"], codes, mode, by_name[lane["window"]]
            )
            result = lane_legs(mode, inputs)
        except EmissionsError as exc:
            problem = str(exc)
        lane_rows.append(
            {
                "window": lane["window"],
                "iso3": lane["iso3"],
                "mode": mode,
                "weight_t": lane["weight_t"],
                "kg_co2e_per_t": result.kg_co2e_per_t if result else None,
                "missing": ", ".join(result.missing_legs) if result else problem,
            }
        )
        for leg in result.legs if result else ():
            leg_rows.append(
                {
                    "window": lane["window"],
                    "iso3": lane["iso3"],
                    "mode": mode,
                    "leg": leg.name,
                    "factor_mode": leg.factor_mode,
                    "km": leg.km,
                    "kg_co2e_per_tkm": leg.kg_co2e_per_tkm,
                    "kg_co2e_per_t": leg.kg_co2e_per_t,
                    "covered_share": leg.covered_share,
                    "observed_share": leg.observed_share,
                }
            )
    return pl.DataFrame(lane_rows), pl.DataFrame(leg_rows)


def mix_by_month(
    supply: pl.DataFrame,
    codes: Sequence[str],
    windows: Sequence[Window],
    lanes: pl.DataFrame,
    tonnes: str = "weight_t",
) -> pl.DataFrame:
    """Emissions per tonne of the whole supply mix, by month: each origin lane's share of the
    month's tonnes × its intensity in the month's window. Lanes with no intensity are left out
    and `measured_share` says how much tonnage that keeps."""
    monthly = (
        with_window(supply.filter(pl.col("hs6").is_in(list(codes))), windows)
        .drop_nulls("window")
        .group_by("month", "window", "iso3", "mode")
        .agg(pl.col(tonnes).sum().alias("t"))
        .join(
            lanes.select("window", "iso3", "mode", "kg_co2e_per_t"),
            on=["window", "iso3", "mode"],
            how="left",
        )
    )
    return (
        monthly.group_by("month", "window")
        .agg(
            (
                (pl.col("t") * pl.col("kg_co2e_per_t")).sum()
                / pl.col("t").filter(pl.col("kg_co2e_per_t").is_not_null()).sum()
            ).alias("kg_co2e_per_t"),
            (
                pl.col("t").filter(pl.col("kg_co2e_per_t").is_not_null()).sum() / pl.col("t").sum()
            ).alias("measured_share"),
            pl.col("t").sum().alias("t"),
        )
        .sort("month")
    )


def git_commit() -> str:
    """The repo's current commit, with `-dirty` when the tree has uncommitted changes."""
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    return f"{commit}-dirty" if dirty else commit


def write_derived(
    path: Path, case: str, records: Sequence[Mapping[str, object]], provenance: Mapping[str, object]
) -> None:
    """Write the notebook's DERIVED evidence records, replacing the file: they are regenerated on
    every run, so people don't edit this file."""
    document = {
        "case": case,
        "status": "draft",
        "generated_by": provenance,
        "records": list(records),
    }
    path.write_text(
        "# Generated by the Case 1 notebook; regenerate rather than edit.\n"
        + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    )


def leg_frame_parts(legs: pl.DataFrame) -> dict[str, float]:
    """A lane's emissions per tonne in two parts, from its rows of a legs frame: the legs that
    bring freight to the US (`international`) and the legs inside it (`inland`)."""
    international = pl.col("leg").is_in(list(INTERNATIONAL_LEGS))
    return {
        "international": legs.filter(international)["kg_co2e_per_t"].sum(),
        "inland": legs.filter(~international)["kg_co2e_per_t"].sum(),
    }


def lane_mix_cells(
    supply: pl.DataFrame, codes: Sequence[str], window: Window, legs: pl.DataFrame
) -> dict[tuple[str, str], MixCell]:
    """The supply mix's cells for one window, origin × mode, with each lane's tonnage and its
    intensity in two parts. Lanes with no measured legs are left out."""
    tonnes = (
        supply.filter(
            pl.col("hs6").is_in(list(codes)) & pl.col("month").is_between(window.first, window.last)
        )
        .group_by("iso3", "mode")
        .agg(pl.col("weight_t").sum())
    )
    in_window = legs.filter(pl.col("window") == window.name)
    cells = {}
    for row in tonnes.iter_rows(named=True):
        lane = in_window.filter((pl.col("iso3") == row["iso3"]) & (pl.col("mode") == row["mode"]))
        if lane.is_empty() or row["weight_t"] <= 0:
            continue
        cells[(row["iso3"], row["mode"])] = MixCell(row["weight_t"], leg_frame_parts(lane))
    return cells


def suspect_air_months(air: pl.DataFrame, low: float, high: float) -> pl.DataFrame:
    """Origin × HS-6 × months whose air value per kilogram falls in [`low`, `high`], the band
    where Census's imputed weights cluster."""
    return air.filter(
        (pl.col("value_usd") / (pl.col("weight_t") * 1000)).is_between(low, high)
    ).select("month", "census_cty_code", "hs6", "value_usd")


def origin_air_ratios(air: pl.DataFrame, before: date) -> pl.DataFrame:
    """Each origin's air value per kilogram over the months before `before`: overall, and the
    10th and 90th percentile of its monthly values."""
    pre = air.filter(pl.col("month") < before).with_columns(
        (pl.col("value_usd") / (pl.col("weight_t") * 1000)).alias("usd_per_kg")
    )
    return pre.group_by("census_cty_code").agg(
        (pl.col("value_usd").sum() / (pl.col("weight_t").sum() * 1000)).alias("central"),
        pl.col("usd_per_kg").quantile(0.1).alias("p10"),
        pl.col("usd_per_kg").quantile(0.9).alias("p90"),
    )


def all_origins_air_ratio(air: pl.DataFrame, before: date) -> float:
    """Air value per kilogram over every origin's months before `before`."""
    pre = air.filter(pl.col("month") < before)
    return pre["value_usd"].sum() / (pre["weight_t"].sum() * 1000)


def reweight_air(
    supply: pl.DataFrame,
    suspect: pl.DataFrame,
    usd_per_kg: pl.DataFrame | float,
    default: float | None = None,
) -> pl.DataFrame:
    """`supply` with the suspect months' air tonnes recomputed as value ÷ `usd_per_kg`: one value
    for every origin, or a frame of `census_cty_code` and `usd_per_kg`. A suspect origin missing
    from the frame takes `default`, and without one is an error."""
    if isinstance(usd_per_kg, pl.DataFrame):
        fixed = suspect.join(usd_per_kg, on="census_cty_code", how="left")
        if default is not None:
            fixed = fixed.with_columns(pl.col("usd_per_kg").fill_null(default))
        missing = fixed.filter(pl.col("usd_per_kg").is_null())
        if not missing.is_empty():
            raise ValueError(
                f"no value per kg for {sorted(missing['census_cty_code'].unique().to_list())}"
            )
    else:
        fixed = suspect.with_columns(pl.lit(usd_per_kg).alias("usd_per_kg"))
    fixed = fixed.select(
        "month",
        "census_cty_code",
        "hs6",
        pl.lit("air").alias("mode"),
        (pl.col("value_usd") / pl.col("usd_per_kg") / 1000).alias("new_t"),
    )
    keys = ["month", "census_cty_code", "hs6", "mode"]
    return (
        supply.join(fixed, on=keys, how="left")
        .with_columns(
            [
                pl.coalesce("new_t", c).alias(c)
                for c in ("weight_t", "weight_t_low", "weight_t_high")
            ]
        )
        .drop("new_t")
    )


def plot_waterfall(
    ax: Axes,
    decomposition: MixDecomposition,
    labels: Mapping[str, str],
    title: str,
    window_label: str = "window",
) -> None:
    """A waterfall from the baseline mix to the window's, one bar per effect, in kg CO2e per
    tonne."""
    names = list(labels)
    level = decomposition.baseline
    top = max(decomposition.baseline, decomposition.window)
    ax.bar(0, level, color="#8a9a8f")
    for i, name in enumerate(names, start=1):
        effect = decomposition.effects[name]
        ax.bar(i, effect, bottom=level, color="#a2412d" if effect > 0 else "#2d5b4f")
        label_at = level + max(effect, 0)
        ax.annotate(
            f"{effect:+,.0f}",
            (i, label_at),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
        level += effect
        top = max(top, label_at)
    ax.bar(len(names) + 1, decomposition.window, color="#8a9a8f")
    ax.set_ylim(0, top * 1.15)
    ax.set_xticks(
        range(len(names) + 2), ["baseline", *[labels[n] for n in names], window_label], fontsize=8
    )
    ax.set_ylabel("kg CO2e per tonne delivered")
    ax.set_title(title)
