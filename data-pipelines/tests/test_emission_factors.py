import csv
import io
from collections.abc import Callable
from pathlib import Path

import openpyxl
import pytest

from shockt.reference.emission_factors import (
    SEED_COLUMNS,
    SHORT_TON_MILE_IN_TONNE_KM,
    FactorSourceError,
    build_seed_rows,
    read_epa_factors,
    read_uk_rows,
    uk_factor,
    write_seed,
)

UK_HEADER = (
    "ID",
    "Scope",
    "Level 1",
    "Level 2",
    "Level 3",
    "Level 4",
    "Column Text",
    "UOM",
    "GHG/Unit",
    "GHG Conversion Factor 2026",
)
TTW = "Freighting goods"
WTT = "WTT- delivery vehs & freight"
INTL = "International, to/from non-UK"
HGV = "HGV (non-refrigerated, all diesel)"
HGV_AVG = "Average non-refrigerated HGVs"
UK_ROWS = [
    ("t1", TTW, "Cargo ship", "Container ship", "8000+ TEU", None, 0.0127),
    ("w1", WTT, "WTT- cargo ship", "Container ship", "8000+ TEU", None, 0.0029),
    ("t2", TTW, "Cargo ship", "Container ship", "5000–7999 TEU", None, 0.0168),
    ("w2", WTT, "WTT- cargo ship", "Container ship", "5000–7999 TEU", None, 0.0038),
    ("t3", TTW, "Cargo ship", "Container ship", "Average", None, 0.0161),
    ("w3", WTT, "WTT- cargo ship", "Container ship", "Average", None, 0.0037),
    ("t4", TTW, "Freight flights", INTL, None, "With RF", 0.8994),
    ("w4", WTT, "WTT- freight flights", INTL, None, "With RF", 0.1352),
    ("t5", TTW, "Freight flights", INTL, None, "Without RF", 0.5313),
    ("w5", WTT, "WTT- freight flights", INTL, None, "Without RF", 0.1352),
    ("t6", TTW, HGV, HGV_AVG, None, "Average laden", 0.1),
    ("w6", WTT, f"WTT- {HGV}", HGV_AVG, None, "Average laden", 0.025),
    ("t7", TTW, "Rail", "Freight train", None, None, 0.02),
    ("w7", WTT, "WTT- rail", "Freight train", None, None, 0.005),
]


def workbook_bytes(build: Callable[[openpyxl.Workbook], None]) -> bytes:
    wb = openpyxl.Workbook()
    build(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def uk_workbook(rows: list[tuple[object, ...]] = UK_ROWS) -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        wb.active.title = "Front page"
        sheet = wb.create_sheet("Factors by Category")
        sheet.append(["Greenhouse gas reporting: conversion factors 2026"])
        sheet.append([])
        sheet.append(UK_HEADER)
        for factor_id, level_1, level_2, level_3, level_4, column_text, value in rows:
            sheet.append(
                [
                    factor_id,
                    "Scope 3",
                    level_1,
                    level_2,
                    level_3,
                    level_4,
                    column_text,
                    "tonne.km",
                    "kg CO2e",
                    value,
                ]
            )
        # Rows the reader must ignore: another unit, a per-gas breakdown and an energy section.
        sheet.append(
            ["x1", "Scope 3", TTW, "Rail", "Freight train", None, None, "km", "kg CO2e", 9]
        )
        sheet.append(
            [
                "x2",
                "Scope 3",
                TTW,
                "Rail",
                "Freight train",
                None,
                None,
                "tonne.km",
                "kg CO2e of CO2 per unit",
                9,
            ]
        )
        sheet.append(
            [
                "x3",
                "Scope 3",
                "SECR kWh pass & delivery vehs",
                "Rail",
                "Freight train",
                None,
                None,
                "tonne.km",
                "kg CO2e",
                9,
            ]
        )

    return workbook_bytes(build)


def epa_workbook() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        sheet = wb.active
        sheet.title = "Emission Factors Hub"
        sheet.append(["Table 8", "Scope 3 Category 4 and Category 9"])
        sheet.append(["Vehicle Type", "CO2 Factor", "CH4 Factor", "N2O Factor", "Units"])
        sheet.append(["Medium- and Heavy-Duty Truck", 1.298, 0.0115, 0.0376, "vehicle-mile"])
        sheet.append(["Medium- and Heavy-Duty TruckC", 0.186, 0.0016, 0.0054, "short ton-mile"])
        sheet.append(["Rail", 0.021, 0.0016, 0.0005, "short ton-mile"])
        sheet.append(["Table 9", "Waste"])
        sheet.append(["Table 11", "Global Warming Potential (GWP)"])
        sheet.append(["Common Name", "Chemical Formula", "100-Year GWP"])
        sheet.append(["Carbon dioxide", "CO2", 1])
        sheet.append(["Methane", "CH4", 28])
        sheet.append(["Nitrous oxide", "N2O", 265])

    return workbook_bytes(build)


def test_read_uk_rows_keeps_only_kg_co2e_per_tonne_km_freight_rows() -> None:
    rows = read_uk_rows(uk_workbook())

    assert {r.factor_id for r in rows} == {row[0] for row in UK_ROWS}


def test_uk_factor_matches_column_text_case_insensitively() -> None:
    rows = read_uk_rows(uk_workbook())

    factor = uk_factor(
        rows,
        level_1=TTW,
        level_2="HGV (non-refrigerated, all diesel)",
        level_3="Average non-refrigerated HGVs",
        column_text="Average Laden",
    )

    assert factor.factor_id == "t6"


def test_uk_factor_fails_when_a_row_is_missing() -> None:
    rows = read_uk_rows(uk_workbook([r for r in UK_ROWS if r[0] != "w1"]))

    with pytest.raises(FactorSourceError, match="8000\\+ TEU"):
        uk_factor(
            rows,
            level_1=WTT,
            level_2="WTT- cargo ship",
            level_3="Container ship",
            level_4="8000+ TEU",
        )


def test_read_epa_factors_strips_footnote_letters_and_reads_gwps() -> None:
    epa = read_epa_factors(epa_workbook())

    assert set(epa.by_vehicle) == {"Medium- and Heavy-Duty Truck", "Rail"}
    assert (epa.gwp_ch4, epa.gwp_n2o) == (28, 265)


def test_epa_factor_converts_short_ton_miles_and_adds_ch4_and_n2o() -> None:
    epa = read_epa_factors(epa_workbook())

    expected = (0.021 + (0.0016 * 28 + 0.0005 * 265) / 1000) / SHORT_TON_MILE_IN_TONNE_KM
    assert epa.kg_co2e_per_tkm("Rail") == pytest.approx(expected)
    assert SHORT_TON_MILE_IN_TONNE_KM == pytest.approx(1.459972, rel=1e-6)


def test_build_seed_rows_applies_the_uk_well_to_tank_share_to_epa_factors() -> None:
    rows = {
        r.factor_id: r
        for r in build_seed_rows(
            read_uk_rows(uk_workbook()), read_epa_factors(epa_workbook()), "2026", "2025"
        )
    }

    rail = rows["rail_north_america"]
    assert rail.wtt == pytest.approx(rail.ttw * 0.005 / 0.02)
    assert rows["ocean_container_8000plus_teu"].ttw == 0.0127
    assert rows["air_international_with_rf"].wtt == 0.1352
    assert set(rows) == {
        "ocean_container_8000plus_teu",
        "ocean_container_5000_7999_teu",
        "ocean_container_average",
        "air_international_with_rf",
        "air_international_without_rf",
        "truck_north_america",
        "rail_north_america",
    }


def test_write_seed_sums_well_to_wheel(tmp_path: Path) -> None:
    path = tmp_path / "seed.csv"
    rows = build_seed_rows(
        read_uk_rows(uk_workbook()), read_epa_factors(epa_workbook()), "2026", "2025"
    )

    write_seed(rows, path)

    written = list(csv.DictReader(path.open()))
    assert tuple(written[0]) == SEED_COLUMNS
    ocean = next(r for r in written if r["factor_id"] == "ocean_container_8000plus_teu")
    assert float(ocean["wtw_kg_co2e_per_tkm"]) == pytest.approx(0.0156)
