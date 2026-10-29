"""SBTi Target Dashboard downloads: the by-company and by-target workbooks, loaded whole.

Each workbook is archived unchanged and loaded as one `latest` partition. The first row is the
header; columns keep the workbook's field names. Year and scope cells mix numbers with labels
(`FY2030`, `NA`), so they load as text, with whole numbers written without a decimal point.
"""

import io
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

import openpyxl

from shockt.loading import ParsedSource, Target

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COMPANIES_FILENAME = "companies-excel.xlsx"
TARGETS_FILENAME = "targets-excel.xlsx"

Kind = Literal["text", "int", "timestamp"]
Column = tuple[str, Kind]

COMPANY_COLUMNS: tuple[Column, ...] = (
    ("sbti_id", "int"),
    ("company_name", "text"),
    ("isin", "text"),
    ("lei", "text"),
    ("organization_type", "text"),
    ("location", "text"),
    ("region", "text"),
    ("sector", "text"),
    ("near_term_status", "text"),
    ("near_term_target_classification", "text"),
    ("near_term_target_year", "text"),
    ("long_term_status", "text"),
    ("long_term_target_classification", "text"),
    ("long_term_target_year", "text"),
    ("net_zero_status", "text"),
    ("net_zero_year", "text"),
    ("full_target_language", "text"),
    ("ba15_status", "text"),
    ("ba15_date", "timestamp"),
    ("target_classification_long", "text"),
    ("status_reason", "text"),
    ("date_updated", "timestamp"),
)
TARGET_COLUMNS: tuple[Column, ...] = (
    ("row_entry_id", "text"),
    ("sbti_id", "int"),
    ("company_name", "text"),
    ("isin", "text"),
    ("lei", "text"),
    ("location", "text"),
    ("region", "text"),
    ("sector", "text"),
    ("organization_type", "text"),
    ("validation_route", "text"),
    ("action", "text"),
    ("commitment_type", "text"),
    ("commitment_deadline", "text"),
    ("status", "text"),
    ("status_reason", "text"),
    ("full_target_language", "text"),
    ("company_temperature_alignment", "text"),
    ("target", "text"),
    ("target_wording", "text"),
    ("scope", "text"),
    ("target_value", "text"),
    ("type", "text"),
    ("sub_type", "text"),
    ("target_classification_short", "text"),
    ("base_year", "text"),
    ("target_year", "text"),
    ("year_type", "text"),
    ("date_published", "timestamp"),
)

COMPANIES = Target(
    dataset="sbti_companies",
    table="sbti_companies",
    columns=("load_id", *(name for name, _ in COMPANY_COLUMNS)),
)
TARGETS = Target(
    dataset="sbti_targets",
    table="sbti_targets",
    columns=("load_id", *(name for name, _ in TARGET_COLUMNS)),
)


class SbtiSourceError(Exception):
    """An SBTi workbook doesn't have the layout the parser expects."""


def parse_companies(body: bytes) -> ParsedSource:
    """Every company of the by-company workbook, keyed by `sbti_id`."""
    return _parse(body, COMPANY_COLUMNS, key="sbti_id")


def parse_targets(body: bytes) -> ParsedSource:
    """Every target or commitment of the by-target workbook, keyed by `row_entry_id`."""
    return _parse(body, TARGET_COLUMNS, key="row_entry_id")


def _parse(body: bytes, columns: Sequence[Column], key: str) -> ParsedSource:
    workbook = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    lines = workbook.worksheets[0].iter_rows(values_only=True)
    header = next(lines, None)
    names = [name for name, _ in columns]
    if header is None or [h for h in header if h is not None] != names:
        raise SbtiSourceError(f"SBTi header is not the expected columns: {header}")
    key_position = names.index(key)
    rows: list[tuple[object, ...]] = []
    seen: set[object] = set()
    for line in lines:
        cells = (*line, *([None] * len(names)))[: len(names)]
        if not any(c not in (None, "") for c in cells):
            continue
        row = tuple(_convert(c, kind, name) for c, (name, kind) in zip(cells, columns, strict=True))
        if row[key_position] in seen:
            raise SbtiSourceError(f"SBTi {key} {row[key_position]!r} appears twice")
        seen.add(row[key_position])
        rows.append(row)
    if not rows:
        raise SbtiSourceError("SBTi workbook has no rows")
    return ParsedSource(rows=rows, rows_received=len(rows), source_version=None)


def _convert(cell: object, kind: Kind, name: str) -> object:
    empty = cell is None or cell == ""
    if kind == "int":
        if isinstance(cell, int | float) and not isinstance(cell, bool) and cell == int(cell):
            return int(cell)
        raise SbtiSourceError(f"SBTi {name} is not a whole number: {cell!r}")
    if empty:
        return None
    if kind == "timestamp":
        if isinstance(cell, datetime):
            return cell
        raise SbtiSourceError(f"SBTi {name} is not a date: {cell!r}")
    if isinstance(cell, datetime):
        return cell.isoformat()
    if isinstance(cell, float) and cell == int(cell):
        return str(int(cell))
    if isinstance(cell, bool):
        raise SbtiSourceError(f"SBTi {name} is a boolean: {cell!r}")
    return str(cell).strip() or None
