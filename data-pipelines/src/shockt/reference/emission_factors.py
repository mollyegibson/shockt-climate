"""Builds `dbt/seeds/seed_emission_factors.csv` from the official UK and US factor workbooks.

The set is a hybrid. Ocean and international air factors come from the UK government
conversion factors, which have container-ship size classes, radiative-forcing variants and
well-to-tank (fuel supply) factors. North American truck and rail factors come from the EPA
GHG Emission Factors Hub, which covers combustion only (tank-to-wheel); their well-to-tank
share is taken from the UK factor for the same mode so every factor is well-to-wheel.
"""

import csv
import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import openpyxl

SHORT_TON_MILE_IN_TONNE_KM = 0.90718474 * 1.609344
UK_SHEET = "Factors by Category"
UK_TTW_LEVEL_1 = "Freighting goods"
UK_WTT_LEVEL_1 = "WTT- delivery vehs & freight"

SEED_COLUMNS = (
    "factor_id",
    "mode",
    "variant",
    "region",
    "ttw_kg_co2e_per_tkm",
    "wtt_kg_co2e_per_tkm",
    "wtw_kg_co2e_per_tkm",
    "ttw_source",
    "wtt_source",
    "gwp_basis",
    "notes",
)


class FactorSourceError(Exception):
    """A factor workbook doesn't contain a row the seed needs, or contains it more than once."""


@dataclass(frozen=True)
class UkRow:
    factor_id: str
    level_1: str
    level_2: str
    level_3: str
    level_4: str | None
    column_text: str | None
    value: float


@dataclass(frozen=True)
class UkFactor:
    value: float
    factor_id: str


@dataclass(frozen=True)
class EpaFactors:
    """EPA Hub Table 8 factors per short ton-mile, and Table 11 GWPs."""

    by_vehicle: dict[str, tuple[float, float, float]]
    """Vehicle type → (kg CO2, g CH4, g N2O) per short ton-mile."""
    gwp_ch4: float
    gwp_n2o: float

    def kg_co2e_per_tkm(self, vehicle: str) -> float:
        if vehicle not in self.by_vehicle:
            raise FactorSourceError(f"EPA Table 8 has no ton-mile row for {vehicle!r}")
        co2, ch4_g, n2o_g = self.by_vehicle[vehicle]
        per_short_ton_mile = co2 + (ch4_g * self.gwp_ch4 + n2o_g * self.gwp_n2o) / 1000
        return per_short_ton_mile / SHORT_TON_MILE_IN_TONNE_KM


@dataclass(frozen=True)
class SeedRow:
    factor_id: str
    mode: str
    variant: str
    region: str
    ttw: float
    wtt: float
    ttw_source: str
    wtt_source: str
    notes: str

    def as_csv_row(self) -> list[str]:
        return [
            self.factor_id,
            self.mode,
            self.variant,
            self.region,
            f"{self.ttw:.6f}",
            f"{self.wtt:.6f}",
            f"{self.ttw + self.wtt:.6f}",
            self.ttw_source,
            self.wtt_source,
            "IPCC AR5 100-year",
            self.notes,
        ]


def read_uk_rows(workbook: bytes) -> list[UkRow]:
    """kg CO2e per tonne.km rows from the UK flat file's freight and freight WTT sections."""
    sheet = openpyxl.load_workbook(io.BytesIO(workbook), read_only=True, data_only=True)[UK_SHEET]
    rows = list(sheet.iter_rows(values_only=True))
    header_index = next((i for i, row in enumerate(rows) if row and "Level 1" in row), None)
    if header_index is None:
        raise FactorSourceError(f"UK workbook sheet {UK_SHEET!r} has no header row")
    header = rows[header_index]
    value_column = next(
        (h for h in header if isinstance(h, str) and h.startswith("GHG Conversion Factor")), None
    )
    if value_column is None:
        raise FactorSourceError("UK workbook has no 'GHG Conversion Factor' column")
    index = {name: i for i, name in enumerate(header) if isinstance(name, str)}
    result: list[UkRow] = []
    for row in rows[header_index + 1 :]:
        if not row or row[index["Level 1"]] not in (UK_TTW_LEVEL_1, UK_WTT_LEVEL_1):
            continue
        if row[index["UOM"]] != "tonne.km" or row[index["GHG/Unit"]] != "kg CO2e":
            continue
        value = row[index[value_column]]
        if not isinstance(value, int | float):
            continue
        result.append(
            UkRow(
                factor_id=str(row[index["ID"]]),
                level_1=str(row[index["Level 1"]]),
                level_2=str(row[index["Level 2"]]),
                level_3=str(row[index["Level 3"]]),
                level_4=_text(row[index["Level 4"]]),
                column_text=_text(row[index["Column Text"]]),
                value=float(value),
            )
        )
    return result


def uk_factor(
    rows: Iterable[UkRow],
    *,
    level_1: str,
    level_2: str,
    level_3: str,
    level_4: str | None = None,
    column_text: str | None = None,
) -> UkFactor:
    """The single UK row matching the given levels; text matching ignores case."""

    def same(a: str | None, b: str | None) -> bool:
        return (a or "").casefold() == (b or "").casefold()

    matches = [
        r
        for r in rows
        if r.level_1 == level_1
        and same(r.level_2, level_2)
        and same(r.level_3, level_3)
        and same(r.level_4, level_4)
        and same(r.column_text, column_text)
    ]
    label = " / ".join(x for x in (level_2, level_3, level_4, column_text) if x)
    if len(matches) != 1:
        raise FactorSourceError(f"expected one UK row for {level_1}: {label}, found {len(matches)}")
    return UkFactor(value=matches[0].value, factor_id=matches[0].factor_id)


def read_epa_factors(workbook: bytes) -> EpaFactors:
    """Table 8 (transportation, per short ton-mile) and Table 11 (GWP) from the EPA Hub."""
    sheet = openpyxl.load_workbook(io.BytesIO(workbook), read_only=True, data_only=True).worksheets[
        0
    ]
    rows = [[c for c in row if c is not None] for row in sheet.iter_rows(values_only=True)]
    table_8 = _table_start(rows, "Table 8")
    by_vehicle: dict[str, tuple[float, float, float]] = {}
    for row in rows[table_8 + 1 :]:
        if row and isinstance(row[0], str) and row[0].startswith("Table "):
            break
        if len(row) == 5 and row[4] == "short ton-mile":
            # EPA appends footnote letters to names, e.g. "Medium- and Heavy-Duty TruckC".
            name = re.sub(r"(?<=[a-z])[A-Z]$", "", str(row[0]).strip())
            by_vehicle[name] = (
                float(row[1]),
                float(row[2]),
                float(row[3]),
            )
    table_11 = _table_start(rows, "Table 11")
    gwp: dict[str, float] = {}
    for row in rows[table_11 + 1 : table_11 + 12]:
        if len(row) >= 3 and row[1] in ("CH4", "N2O"):
            gwp[str(row[1])] = float(row[2])
    if set(gwp) != {"CH4", "N2O"}:
        raise FactorSourceError("EPA Table 11 is missing the CH4 or N2O GWP")
    return EpaFactors(by_vehicle=by_vehicle, gwp_ch4=gwp["CH4"], gwp_n2o=gwp["N2O"])


def build_seed_rows(
    uk_rows: Sequence[UkRow], epa: EpaFactors, uk_version: str, epa_version: str
) -> list[SeedRow]:
    uk = f"UK DESNZ conversion factors {uk_version}"
    epa_source = f"EPA GHG Emission Factors Hub {epa_version}, Table 8"
    rows: list[SeedRow] = []

    for factor_id, size, note in (
        (
            "ocean_container_8000plus_teu",
            "8000+ TEU",
            "Large ships typical of transpacific services.",
        ),
        ("ocean_container_5000_7999_teu", "5000–7999 TEU", ""),
        ("ocean_container_average", "Average", "Fleet average across size classes."),
    ):
        ttw = uk_factor(
            uk_rows,
            level_1=UK_TTW_LEVEL_1,
            level_2="Cargo ship",
            level_3="Container ship",
            level_4=size,
        )
        wtt = uk_factor(
            uk_rows,
            level_1=UK_WTT_LEVEL_1,
            level_2="WTT- cargo ship",
            level_3="Container ship",
            level_4=size,
        )
        rows.append(
            SeedRow(
                factor_id,
                "ocean",
                f"Container ship, {size}",
                "international",
                ttw.value,
                wtt.value,
                f"{uk} ID {ttw.factor_id}",
                f"{uk} ID {wtt.factor_id}",
                note,
            )
        )

    for factor_id, rf, note in (
        (
            "air_international_with_rf",
            "With RF",
            "Includes radiative forcing from high-altitude emissions.",
        ),
        (
            "air_international_without_rf",
            "Without RF",
            "Comparable with inventories that exclude radiative forcing.",
        ),
    ):
        ttw = uk_factor(
            uk_rows,
            level_1=UK_TTW_LEVEL_1,
            level_2="Freight flights",
            level_3="International, to/from non-UK",
            column_text=rf,
        )
        wtt = uk_factor(
            uk_rows,
            level_1=UK_WTT_LEVEL_1,
            level_2="WTT- freight flights",
            level_3="International, to/from non-UK",
            column_text=rf,
        )
        rows.append(
            SeedRow(
                factor_id,
                "air",
                f"International freight flight, {rf.replace('RF', 'radiative forcing').lower()}",
                "international",
                ttw.value,
                wtt.value,
                f"{uk} ID {ttw.factor_id}",
                f"{uk} ID {wtt.factor_id}",
                note,
            )
        )

    for factor_id, mode, vehicle, uk_ttw_args, uk_wtt_args, variant in (
        (
            "truck_north_america",
            "truck",
            "Medium- and Heavy-Duty Truck",
            {
                "level_2": "HGV (non-refrigerated, all diesel)",
                "level_3": "Average non-refrigerated HGVs",
                "column_text": "Average laden",
            },
            {
                "level_2": "WTT- HGV (non-refrigerated, all diesel)",
                "level_3": "Average non-refrigerated HGVs",
                "column_text": "Average laden",
            },
            "Medium- and heavy-duty truck",
        ),
        (
            "rail_north_america",
            "rail",
            "Rail",
            {"level_2": "Rail", "level_3": "Freight train"},
            {"level_2": "WTT- rail", "level_3": "Freight train"},
            "Freight rail",
        ),
    ):
        ttw = epa.kg_co2e_per_tkm(vehicle)
        uk_ttw = uk_factor(uk_rows, level_1=UK_TTW_LEVEL_1, **uk_ttw_args)
        uk_wtt = uk_factor(uk_rows, level_1=UK_WTT_LEVEL_1, **uk_wtt_args)
        share = uk_wtt.value / uk_ttw.value
        rows.append(
            SeedRow(
                factor_id,
                mode,
                variant,
                "north_america",
                ttw,
                ttw * share,
                f"{epa_source} ({vehicle}), per short ton-mile converted to tonne-km",
                f"{uk} IDs {uk_wtt.factor_id} / {uk_ttw.factor_id}: "
                f"well-to-tank share {share:.3f} applied",
                "Also used for truck legs in Mexico.",
            )
        )
    return rows


def write_seed(rows: Sequence[SeedRow], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(SEED_COLUMNS)
        writer.writerows(row.as_csv_row() for row in rows)


def _table_start(rows: list[list[object]], title: str) -> int:
    for i, row in enumerate(rows):
        if row and row[0] == title:
            return i
    raise FactorSourceError(f"EPA workbook has no {title}")


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
