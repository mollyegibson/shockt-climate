"""Create the compact color-chart report and executed notebook companion."""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs/emissions"
COLORS = ["#2864dc", "#ed8b23"]


def read(name):
    return list(csv.DictReader((OUT / name).open()))


def save(fig, name):
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    plt.rcParams.update(
        {"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}
    )
    rows = read("decomposition.csv")
    central = next(
        r
        for r in rows
        if r["route_scenario"] == "equal_node" and r["air_factor"] == "rf"
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    vals = [float(central[k]) / 1000 for k in ("baseline_kg", "response_kg")]
    bars = ax.bar(["May–Dec 2024", "May–Dec 2025"], vals, color=COLORS, width=0.55)
    ax.bar_label(bars, fmt="%.0f t", padding=5)
    ax.set_ylim(0, max(vals) * 1.18)
    ax.set_ylabel("Estimated tonnes CO₂e, international leg")
    ax.set_title(
        "Compressor freight emissions: −25.4% on common route support",
        loc="left",
        weight="bold",
    )
    fig.text(
        0.12,
        0.005,
        "Scenario: equal departure-node weights; fixed WTW factors; aviation RF included.",
        fontsize=9,
    )
    save(fig, "01_emissions_comparison.png")

    cells = read("international_monthly_port.csv")
    origin = defaultdict(float)
    mode = defaultdict(float)
    for r in cells:
        if (
            r["month"].startswith("2025-")
            and 5 <= int(r["month"][5:7]) <= 12
            and r["route_supported"] == "True"
        ):
            origin[(r["iso3"], r["mode"])] += float(r["equal_node_rf_kg_co2e"]) / 1000
            mode[r["mode"]] += float(r["equal_node_rf_kg_co2e"]) / 1000
    countries = sorted(
        {k[0] for k in origin},
        key=lambda c: sum(origin[(c, m)] for m in ("air", "vessel")),
        reverse=True,
    )
    fig, ax = plt.subplots(figsize=(10, 5.6))
    bottom = [0] * len(countries)
    for m, c, label in (
        ("vessel", "#2864dc", "Ocean"),
        ("air", "#a855c7", "Air, with RF"),
    ):
        vals = [origin[(country, m)] for country in countries]
        ax.bar(countries, vals, bottom=bottom, color=c, label=label)
        bottom = [a + b for a, b in zip(bottom, vals)]
    ax.set_ylabel("Estimated tonnes CO₂e, international leg")
    ax.legend()
    ax.set_title(
        "Compressor origin-to-U.S. flows: May–December 2025", loc="left", weight="bold"
    )
    fig.text(
        0.12,
        0.005,
        "Supported routes only; all supported arrivals, not the common-support comparison subset.",
        fontsize=9,
    )
    save(fig, "02_origin_mode_emissions.png")

    lanes = defaultdict(float)
    for r in cells:
        if (
            r["month"].startswith("2025-")
            and 5 <= int(r["month"][5:7]) <= 12
            and r["route_supported"] == "True"
        ):
            lanes[(r["iso3"], r["node_name"], r["mode"])] += (
                float(r["equal_node_rf_kg_co2e"]) / 1000
            )
    top = sorted(lanes, key=lanes.get, reverse=True)[:10]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(
        [f"{c} → {p} ({m})" for c, p, m in reversed(top)],
        [lanes[k] for k in reversed(top)],
        color=["#a855c7" if k[2] == "air" else "#2864dc" for k in reversed(top)],
    )
    ax.set_xlabel("Estimated tonnes CO₂e, international leg")
    ax.set_title(
        "Largest estimated origin-to-arrival flows: May–December 2025",
        loc="left",
        weight="bold",
    )
    fig.text(
        0.12,
        0.005,
        "Origin country → observed U.S. gateway; overseas departure is a scenario. Air includes RF.",
        fontsize=9,
    )
    save(fig, "06_arrival_routes.png")

    import_weights = defaultdict(float)
    for r in csv.DictReader((ROOT / "outputs/tables/compressor_monthly.csv").open()):
        year = r["month"][:4]
        if year in ("2024", "2025") and 5 <= int(r["month"][5:7]) <= 12:
            import_weights[(year, r["origin_group"]) ] += float(r["weight_t"])
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, year in enumerate(("2024", "2025")):
        bars = ax.bar([x + (i-.5)*.35 for x in (0, 1)],
                      [import_weights[(year,c)] for c in ("CHN", "THA")],
                      width=.35, color=COLORS[i], label="May–Dec " + year)
        ax.bar_label(bars, fmt="%.0f t", padding=4)
    ax.set_xticks([0,1], ["China: −36.2%", "Thailand: +12.1%"])
    ax.set_ylabel("Reported compressor import weight, tonnes")
    ax.set_ylim(0,38000); ax.legend()
    ax.set_title("Thailand compressor imports rose while China declined", loc="left", weight="bold")
    fig.text(.12,.005,"Observed Census air + vessel weight; sourcing evidence, not proof of a production transfer.", fontsize=9)
    save(fig, "07_china_thailand_imports.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    for year, color, ek in (
        (2024, COLORS[0], "baseline_kg"),
        (2025, COLORS[1], "response_kg"),
    ):
        rs = [
            next(
                r for r in rows if r["route_scenario"] == s and r["air_factor"] == "rf"
            )
            for s in ("minimum", "equal_node", "maximum")
        ]
        ax.plot(
            ["Shortest available", "Equal departure weights", "Longest available"],
            [float(r[ek]) / 1000 for r in rs],
            "o-",
            color=color,
            label=str(year),
            linewidth=2.5,
        )
    ax.set_ylabel("Estimated tonnes CO₂e, international leg")
    ax.legend()
    ax.set_title(
        "Departure-port sensitivity: lower emissions in every tested scenario",
        loc="left",
        weight="bold",
    )
    fig.text(
        0.12,
        0.005,
        "Common route support. Sensitivity across seeded departure nodes, not a confidence interval.",
        fontsize=9,
    )
    save(fig, "03_route_sensitivity.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    effects = [
        float(central[k]) / 1000 for k in ("volume_effect_kg", "intensity_effect_kg")
    ]
    bars = ax.barh(
        ["Import volume effect", "Emissions per tonne effect"],
        effects,
        color=["#ed8b23", "#13a49b"],
    )
    ax.bar_label(bars, fmt="%.0f t", padding=4)
    ax.set_xlim(min(effects) * 1.2, 0)
    ax.set_xlabel("Contribution to change in estimated tonnes CO₂e")
    ax.set_title(
        "Why estimated emissions fell: mostly lower import volume",
        loc="left",
        weight="bold",
    )
    fig.text(
        0.12,
        0.005,
        "Exact symmetric volume/intensity decomposition; descriptive, not tariff causation.",
        fontsize=9,
    )
    save(fig, "04_volume_intensity.png")

    summary = read("international_matched_windows.csv")
    allrows = {int(r["year"]): r for r in summary if r["mode"] == "all"}
    inland = read("inland_monthly.csv")
    inland_s = []
    for y in (2024, 2025):
        rs = [
            r
            for r in inland
            if r["month"].startswith(str(y)) and 5 <= int(r["month"][5:7]) <= 12
        ]
        mass = sum(float(r["weight_t"]) for r in rs)
        covered = sum(
            float(r["weight_t"]) * float(r["covered_pair_share"] or 0) for r in rs
        )
        emissions = sum(float(r["covered_subset_kg_co2e"] or 0) for r in rs) / 1000
        inland_s.append(
            dict(
                year=y,
                reported_weight_t=mass,
                covered_pair_weight_t=covered,
                coverage=covered / mass,
                estimated_t_co2e=emissions,
            )
        )
    with (OUT / "inland_matched_windows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(inland_s[0]))
        w.writeheader()
        w.writerows(inland_s)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(
        ["May–Dec 2024", "May–Dec 2025"],
        [r["estimated_t_co2e"] for r in inland_s],
        color=COLORS,
        width=0.55,
    )
    ax.bar_label(bars, fmt="%.0f t", padding=5)
    ax.set_ylim(0, max(r["estimated_t_co2e"] for r in inland_s) * 1.18)
    ax.set_ylabel("Estimated tonnes CO₂e, supported U.S. inland pairs")
    ax.set_title(
        "U.S. inland truck reconstruction — separate coverage",
        loc="left",
        weight="bold",
    )
    fig.text(
        0.12,
        0.005,
        "Independent arrival-port/destination-state distributions; not observed shipment pairs.",
        fontsize=9,
    )
    save(fig, "05_inland_emissions.png")
    q0 = float(central["baseline_t"])
    q1 = float(central["response_t"])
    text = f"""# Compressor freight emissions — aggregate scenario estimate

**Result:** On common supported origin/mode/arrival-port cells, estimated international emissions fall
from **{vals_placeholder(central, "baseline_kg"):,.0f} to {vals_placeholder(central, "response_kg"):,.0f} tonnes CO₂e (−25.4%)**.
This compares May–December 2024 with May–December 2025 using fixed factors and equal weights across available foreign departure nodes.
This is a transport scenario estimate, not an observed carbon inventory or a Haier shipment result.

The common supported mass is {q0:,.0f} tonnes in 2024 and {q1:,.0f} tonnes in 2025:
**{q0 / float(allrows[2024]["reported_weight_t"]):.1%} and {q1 / float(allrows[2025]["reported_weight_t"]):.1%}** of reported compressor air/sea weights.
Estimated intensity falls from **{float(central["baseline_kg_per_t"]):.1f} to {float(central["response_kg_per_t"]):.1f} kg CO₂e/tonne**.
Lower volume accounts for **{abs(float(central["volume_effect_kg"])) / 1000:,.0f} tonnes** of the reduction;
intensity changes account for **{abs(float(central["intensity_effect_kg"])) / 1000:,.0f} tonnes**.

## Coverage and interpretation

Thailand compressor imports increased from **5,166 to 5,789 tonnes (+12.1%)** while China declined
from **32,179 to 20,531 tonnes (−36.2%)** in the matched months. Thailand's weight share rose
from 5.3% to 7.6%. The 2025 emissions ranking is a level comparison, not a year-to-year change chart;
the separate China/Thailand import chart answers this sourcing question. Compressor import shifts
do not establish that the same production physically transferred between these countries.

Across all supported arrivals (a different subset from the common-support comparison), the equal-departure scenario estimates
{float(allrows[2024]["equal_node_rf_kg_co2e"]) / 1000:,.0f} tonnes CO₂e in 2024 and
{float(allrows[2025]["equal_node_rf_kg_co2e"]) / 1000:,.0f} tonnes in 2025.
Distance coverage is {float(allrows[2024]["route_coverage"]):.1%} and {float(allrows[2025]["route_coverage"]):.1%};
uncovered mass remains missing, not zero carbon. The origin chart uses this supported subset; do not sum it against the common-support headline.

U.S. inland truck estimates, shown separately because coverage differs, are
{inland_s[0]["estimated_t_co2e"]:,.0f} and {inland_s[1]["estimated_t_co2e"]:,.0f} tonnes CO₂e.
Supported pair-weight coverage is {inland_s[0]["coverage"]:.1%} and {inland_s[1]["coverage"]:.1%}.
No full-lane grand total is claimed.

## Assumptions

- HS 841430 includes compressors for refrigerating equipment beyond household refrigerators; configured Asia/Mexico origins, not all U.S. imports.
- Census supplies observed aggregate weights, origin countries, U.S. ports, modes and months. Foreign departure nodes and inland shipment pairings are not observed.
- Each available seeded departure node in the origin country gets equal weight for each supported arrival. Availability is not evidence of representative export-port market shares.
- Route sensitivity takes the shortest/longest available seeded departure route per arrival; open-passage sea routes. This is not a confidence interval or an exhaustive physical bound. Origin country need not be the actual loading country when transshipment occurs.
- Ocean uses average container ship; U.S. inland assumes truck and independent port/state distributions. Actual vessel/load factor and inland mode are unknown.
- UK 2026 revised factors are held fixed over both historical windows. WTW includes fuel production; air has RF and no-RF alternatives. Aviation RF includes non-CO₂ climate effects, so the two are distinct reporting views.
- Truck combustion uses EPA 2025 Table 8 and Table 11 GWPs, converted from short ton-mile; WTT is estimated with the UK mineral-diesel upstream/combustion ratio, not a measured U.S. upstream factor.
- Excludes foreign inland, unmeasured transshipment, unsupported routes, Mexico truck/rail, manufacturing, refrigerant leakage and product use. No company attribution or causal tariff claim.

## Sensitivity

Common-support change with aviation RF: −25.9% (shortest), −25.4% (equal weights), −24.9% (longest).
Without aviation RF: −25.3%, −24.9%, −24.6%, respectively. These do not cover every source of uncertainty.

## Sources and reproduction

[Census port imports](https://www.census.gov/foreign-trade/data/dataproducts.html),
[UK DESNZ 2026 revised factors](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026),
[EPA 2025 factors](https://www.epa.gov/climateleadership/ghg-emission-factors-hub),
[OurAirports](https://ourairports.com/data/). Shared ShockT weighted-distance and lane-intensity functions; existing sea/air/road distance seeds.
The source manifest records SHA-256 hashes, workbook URLs and assumptions. Factor row IDs and values are in `factors.csv`.
`calculate_compressor_emissions.py` regenerates numerical outputs; `verify_emissions.py` reconciles source weights, units, route arithmetic and decomposition closure.
"""
    (ROOT / "COMPRESSOR_EMISSIONS.md").write_text(text)
    images = [
        ("01_emissions_comparison.png", "Common-support international comparison"),
        ("02_origin_mode_emissions.png", "Supported origin-to-U.S. flows"),
        ("03_route_sensitivity.png", "Departure route sensitivity"),
        ("04_volume_intensity.png", "Volume and intensity decomposition"),
        ("05_inland_emissions.png", "Separate inland reconstruction"),
        ("06_arrival_routes.png", "Largest origin-to-arrival flows"),
        ("07_china_thailand_imports.png", "China and Thailand observed import change"),
    ]
    (OUT / "README.md").write_text(
        text + "\n\n" + "\n\n".join(f"![{label}]({name})" for name, label in images)
    )
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(text),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nfrom IPython.display import display, Image\nimport polars as pl\n"
            "output=Path('outputs/emissions')\n"
            "for filename in ['factors.csv','international_matched_windows.csv','decomposition.csv','inland_matched_windows.csv']:\n"
            "    print(filename)\n    display(pl.read_csv(output/filename))\n"
        ),
        *[
            nbformat.v4.new_code_cell(f"display(Image(filename=str(output/'{name}')))")
            for name, _ in images
        ],
    ]
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nbformat.write(nb, ROOT / "compressor_emissions.ipynb")
    print("Created seven color charts, report and notebook")


def vals_placeholder(r, key):
    return float(r[key]) / 1000


if __name__ == "__main__":
    main()
