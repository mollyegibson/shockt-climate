"""Aggregate, scenario-based compressor freight estimate; never individual shipment emissions.

Run with the established analysis environment from the repository root. The official factor
workbooks are parsed by shockt.sources.ghg_factors into sources/parsed_factors.json first.
"""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from shockt_engine.emissions import Leg, lane_intensity, pair_weighted_distance

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs/emissions"
SOURCE_REPO = ROOT.parents[1]
if (SOURCE_REPO / "tmp/shockt-climate-v2/data-pipelines/dbt/seeds").exists():
    SOURCE_REPO = SOURCE_REPO / "tmp/shockt-climate-v2"
SEEDS = SOURCE_REPO / "data-pipelines/dbt/seeds"


def read(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with (OUT / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def calculate():
    raw = json.loads((OUT / "sources/parsed_factors.json").read_text())
    uk = {r[0]: r for r in raw["uk"]}
    chosen = {
        "ocean": ("27_320_3235_14_1", "28_916_3235_14_1"),
        "air_rf": ("27_317_3158_14_1", "28_913_3158_14_1"),
        "air_no_rf": ("27_317_3159_14_1", "28_913_3159_14_1"),
    }
    factors = []
    for mode, ids in chosen.items():
        a, b = (uk[i] for i in ids)
        assert a[7:9] == ["tonne.km", "kg CO2e"]
        factors.append(
            dict(
                mode=mode,
                ttw=a[-1],
                wtt=b[-1],
                wtw=a[-1] + b[-1],
                source="UK DESNZ 2026 revised July",
                source_rows=";".join(ids),
            )
        )
    gwp = {r[1]: r[2] for r in raw["gwp"]}
    truck = next(
        r
        for r in raw["epa"]
        if r[0].startswith("Medium-") and r[-1] == "short ton-mile"
    )
    ttw = (truck[1] + (truck[2] * gwp["CH4"] + truck[3] * gwp["N2O"]) / 1000) / (
        0.90718474 * 1.609344
    )
    # Match the existing engine's US EPA + UK diesel WTT construction, not a US WTT observation.
    diesel = uk["11_101_1012_8_1"][-1] / uk["1_101_1012_8_1"][-1]
    factors.append(
        dict(
            mode="truck",
            ttw=ttw,
            wtt=ttw * diesel,
            wtw=ttw * (1 + diesel),
            source="EPA Hub 2025 combustion + UK 2026 mineral-diesel WTT ratio",
            source_rows=truck[0] + ";CH4=28;N2O=265;11_101_1012_8_1;1_101_1012_8_1",
        )
    )
    write("factors.csv", factors)
    ef = {r["mode"]: r["wtw"] for r in factors}
    countries = {
        r["iso2"]: r["iso3"] for r in read(SEEDS / "seed_census_countries.csv")
    }
    airports = {
        r["iata_code"]: countries.get(r["iso_country"])
        for r in read(OUT / "sources/airports.csv")
        if r["iata_code"]
    }
    routes = defaultdict(dict)
    for r in read(SEEDS / "seed_sea_distances.csv"):
        if r["scenario"] == "open":
            country = r["from_node_id"].split(":")[1].split("_")[0]
            routes[("vessel", country, r["to_node_id"])][r["from_node_id"]] = float(
                r["km"]
            )
    for r in read(SEEDS / "seed_air_distances.csv"):
        country = airports.get(r["from_node_id"].split(":")[1])
        if country:
            routes[("air", country, r["to_node_id"])][r["from_node_id"]] = float(
                r["km"]
            )
    route_rows = []
    for (mode, country, node), ds in sorted(routes.items()):
        # Equal weighting is an explicit departure-node scenario, not inferred freight allocation.
        mean = pair_weighted_distance(
            {(d, node): km for d, km in ds.items()}, {(d, node): 1 for d in ds}
        ).km
        route_rows.append(
            dict(
                mode=mode,
                iso3=country,
                node_id=node,
                departures=";".join(sorted(ds)),
                departure_count=len(ds),
                minimum_km=min(ds.values()),
                equal_node_km=mean,
                maximum_km=max(ds.values()),
            )
        )
    write("route_scenarios.csv", route_rows)
    lookup = {(r["mode"], r["iso3"], r["node_id"]): r for r in route_rows}
    ports = [
        r
        for r in read(ROOT / "outputs/tables/port_activity.csv")
        if r["hs6"] == "841430" and r["weight_t"] and float(r["weight_t"]) > 0
    ]
    cells = []
    for r in ports:
        route = lookup.get((r["mode"], r["iso3"], r["node_id"]))
        row = {k: r[k] for k in ("month", "iso3", "mode", "node_id", "node_name")}
        row.update(weight_t=float(r["weight_t"]), route_supported=bool(route))
        for distance in ("minimum", "equal_node", "maximum"):
            for rf in ("rf", "no_rf"):
                factor = ef["ocean" if r["mode"] == "vessel" else "air_" + rf]
                row[distance + "_" + rf + "_kg_co2e"] = (
                    (
                        float(r["weight_t"])
                        * lane_intensity([Leg(route[distance + "_km"], factor)])
                    )
                    if route
                    else None
                )
        cells.append(row)
    write("international_monthly_port.csv", cells)
    inland = [
        r
        for r in read(ROOT / "outputs/tables/domestic_transport_activity.csv")
        if r["hs6"] == "841430"
    ]
    for r in inland:
        value = r["reconstructed_tonne_km_covered"]
        r["covered_subset_kg_co2e"] = float(value) * ef["truck"] if value else None
    write("inland_monthly.csv", inland)
    summaries = []
    for year in (2024, 2025):
        selected = [
            r
            for r in cells
            if r["month"][:4] == str(year) and 5 <= int(r["month"][5:7]) <= 12
        ]
        for mode in ("air", "vessel", "all"):
            rs = [r for r in selected if mode == "all" or r["mode"] == mode]
            mass = sum(r["weight_t"] for r in rs)
            covered = sum(r["weight_t"] for r in rs if r["route_supported"])
            row = dict(
                year=year,
                months="May–December",
                mode=mode,
                reported_weight_t=mass,
                supported_weight_t=covered,
                unsupported_weight_t=mass - covered,
                route_coverage=covered / mass,
            )
            for key in (k for k in cells[0] if k.endswith("kg_co2e")):
                row[key] = sum(r[key] for r in rs if r[key] is not None)
            row["equal_node_rf_kg_co2e_per_supported_t"] = (
                row["equal_node_rf_kg_co2e"] / covered
            )
            summaries.append(row)
    write("international_matched_windows.csv", summaries)
    # Compare identical origin/mode/arrival-node support; never treat absent support as zero carbon.
    windows = {
        y: [
            r
            for r in cells
            if r["month"][:4] == str(y) and 5 <= int(r["month"][5:7]) <= 12
        ]
        for y in (2024, 2025)
    }
    keys = {
        y: {(r["iso3"], r["mode"], r["node_id"]) for r in rs if r["route_supported"]}
        for y, rs in windows.items()
    }
    common = keys[2024] & keys[2025]
    decomposition = []
    for distance in ("minimum", "equal_node", "maximum"):
        for rf in ("rf", "no_rf"):
            key = distance + "_" + rf + "_kg_co2e"
            vals = {
                y: (
                    sum(
                        r["weight_t"]
                        for r in rs
                        if (r["iso3"], r["mode"], r["node_id"]) in common
                    ),
                    sum(
                        r[key]
                        for r in rs
                        if (r["iso3"], r["mode"], r["node_id"]) in common
                    ),
                )
                for y, rs in windows.items()
            }
            q0, e0 = vals[2024]
            q1, e1 = vals[2025]
            i0 = e0 / q0
            i1 = e1 / q1
            volume = (q1 - q0) * (i0 + i1) / 2
            intensity = (i1 - i0) * (q0 + q1) / 2
            assert abs(volume + intensity - (e1 - e0)) < 1e-6
            decomposition.append(
                dict(
                    route_scenario=distance,
                    air_factor=rf,
                    baseline_t=q0,
                    response_t=q1,
                    baseline_kg=e0,
                    response_kg=e1,
                    change_pct=(e1 / e0 - 1) * 100,
                    baseline_kg_per_t=i0,
                    response_kg_per_t=i1,
                    volume_effect_kg=volume,
                    intensity_effect_kg=intensity,
                    common_support=True,
                )
            )
    write("decomposition.csv", decomposition)
    manifest = {
        "scope": "HS841430 configured origins; air and vessel only; no company attribution",
        "factors": "Fixed 2026 UK / 2025 EPA; WTW transport only; no manufacturing or refrigerants",
        "route_assumption": "Equal weights across available country departure nodes; min/max node sensitivity. Not observed routes, representative port selection, or a confidence interval.",
        "inland_assumption": "Truck; independent port/state distributions; covered pairs only",
        "exclusions": "Foreign inland, transshipment, unsupported pairs, Mexican overland; not full supply-chain footprint",
        "source_urls": {
            "uk_2026.xlsx": "https://assets.publishing.service.gov.uk/media/6a6c9748862aaf18d9c62ac9/ghg-conversion-factors-2026-flat-format-revised.xlsx",
            "epa_2025.xlsx": "https://www.epa.gov/system/files/other-files/2025-01/ghg-emission-factors-hub-2025.xlsx",
            "airports.csv": "https://davidmegginson.github.io/ourairports-data/airports.csv",
        },
        "sources": {
            str(p.relative_to(ROOT.parents[1])): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in [
                *sorted((OUT / "sources").glob("*")),
                SEEDS / "seed_sea_distances.csv",
                SEEDS / "seed_air_distances.csv",
                SEEDS / "seed_road_distances.csv",
                ROOT / "outputs/tables/port_activity.csv",
                ROOT / "outputs/tables/domestic_transport_activity.csv",
            ]
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(decomposition, indent=2))


if __name__ == "__main__":
    calculate()
