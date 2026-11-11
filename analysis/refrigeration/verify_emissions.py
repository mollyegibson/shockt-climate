"""Independent output reconciliation, missing-route accounting, and source hash checks."""

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs/emissions"


def read(path):
    return list(csv.DictReader(path.open()))


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-6), (a, b)


def main():
    manifest = json.loads((OUT / "manifest.json").read_text())
    for name, digest in manifest["sources"].items():
        assert (
            hashlib.sha256((ROOT.parents[1] / name).read_bytes()).hexdigest() == digest
        )
    factors = {r["mode"]: r for r in read(OUT / "factors.csv")}
    for r in factors.values():
        close(float(r["wtw"]), float(r["ttw"]) + float(r["wtt"]))
    close(
        float(factors["truck"]["ttw"]),
        (0.186 + (0.0016 * 28 + 0.0054 * 265) / 1000) / (0.90718474 * 1.609344),
    )
    routes = {
        (r["mode"], r["iso3"], r["node_id"]): r
        for r in read(OUT / "route_scenarios.csv")
    }
    cells = read(OUT / "international_monthly_port.csv")
    totals = defaultdict(float)
    seen = set()
    for r in cells:
        key = (r["month"], r["iso3"], r["mode"], r["node_id"])
        assert key not in seen
        seen.add(key)
        tonnes = float(r["weight_t"])
        totals[(r["month"], r["iso3"], r["mode"])] += tonnes
        route = routes.get((r["mode"], r["iso3"], r["node_id"]))
        for rf in ("rf", "no_rf"):
            for scenario in ("minimum", "equal_node", "maximum"):
                value = r[scenario + "_" + rf + "_kg_co2e"]
                if route is None:
                    assert value == ""
                else:
                    ef = float(
                        factors["ocean" if r["mode"] == "vessel" else "air_" + rf][
                            "wtw"
                        ]
                    )
                    close(float(value), tonnes * float(route[scenario + "_km"]) * ef)
    national = defaultdict(float)
    for r in read(ROOT / "outputs/snapshot/supply.csv"):
        if r["hs6"] == "841430":
            national[(r["month"][:7], r["iso3"], r["mode"])] += float(r["weight_t"])
    for (month, country, mode), mass in national.items():
        close(totals[(month + "-01", country, mode)], mass)
    for r in read(OUT / "decomposition.csv"):
        close(
            float(r["volume_effect_kg"]) + float(r["intensity_effect_kg"]),
            float(r["response_kg"]) - float(r["baseline_kg"]),
        )
    for r in read(OUT / "inland_monthly.csv"):
        if r["covered_subset_kg_co2e"]:
            close(
                float(r["covered_subset_kg_co2e"]),
                float(r["reconstructed_tonne_km_covered"])
                * float(factors["truck"]["wtw"]),
            )
    print(
        "PASS: source hashes; official-factor units; cell arithmetic; Census weight reconciliation; missing routes; inland and decomposition closure"
    )


if __name__ == "__main__":
    main()
