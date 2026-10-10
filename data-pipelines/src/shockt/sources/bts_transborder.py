"""BTS TransBorder Freight loader for the monthly raw-data ZIPs downloaded from bts.gov.

bts.gov blocks scripted downloads, so the ZIPs are downloaded by hand. One partition is one
month: its ZIP is archived unchanged, then the `dot2` (state × commodity) and `dot3`
(port × commodity) tables are parsed from the archived copy and filtered to the configured
trade type, countries and HS-2 chapters.
"""

import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl
import psycopg

from shockt.archive import Archive, object_key, sha256_hex
from shockt.config import BtsTransborderConfig
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult

DATASET = "bts_transborder"
TARGET = Target(
    dataset=DATASET,
    table="bts_transborder",
    columns=(
        "load_id",
        "source_table",
        "year",
        "month",
        "trdtype",
        "usastate",
        "depe",
        "commodity2",
        "disagmot",
        "mexstate",
        "country",
        "value",
        "shipwt",
        "freight_charges",
        "df",
        "contcode",
    ),
)

_REQUIRED = {
    "dot2": ("TRDTYPE", "USASTATE", "COMMODITY2", "DISAGMOT", "MEXSTATE", "COUNTRY"),
    "dot3": ("TRDTYPE", "DEPE", "COMMODITY2", "DISAGMOT", "COUNTRY"),
}
_COMMON = ("VALUE", "SHIPWT", "FREIGHT_CHARGES", "DF", "CONTCODE", "YEAR")
_INT_COLUMNS = ("YEAR", "MONTH", "TRDTYPE", "DISAGMOT", "VALUE", "SHIPWT", "FREIGHT_CHARGES", "DF")
_MONTHLY_MEMBER = re.compile(r"(?:^|/)(dot[123])_(\d{2})(\d{2})\.csv$", re.IGNORECASE)


class BtsFileError(Exception):
    """A TransBorder ZIP is unreadable, incomplete, or doesn't match its expected layout."""


@dataclass(frozen=True)
class MonthFile:
    month: str
    """'YYYY-MM'."""
    path: Path
    members: dict[str, str]
    """Table name (`dot2`, `dot3`) → member path inside the ZIP."""


def monthly_members(names: list[str]) -> dict[str, tuple[str, str]]:
    """Monthly table files in a ZIP's member list: table → (month, member name).

    Matches `dotN_MMYY.csv` only, so year-to-date (`dotN_ytd_MMYY.csv`) and annual
    (`dotN_YYYY.csv`) files are ignored.
    """
    found: dict[str, tuple[str, str]] = {}
    for name in names:
        match = _MONTHLY_MEMBER.search(name)
        if match is None or not 1 <= int(match.group(2)) <= 12:
            continue
        table = match.group(1).lower()
        month = f"20{match.group(3)}-{match.group(2)}"
        if table in found:
            raise BtsFileError(f"more than one monthly {table} file: {found[table][1]}, {name}")
        found[table] = (month, name)
    return found


def read_month_file(path: Path, tables: list[str]) -> MonthFile:
    """Identify the month and table members of one downloaded ZIP."""
    try:
        with zipfile.ZipFile(path) as zf:
            members = monthly_members(zf.namelist())
            bad = zf.testzip()
    except zipfile.BadZipFile as exc:
        raise BtsFileError(f"{path.name}: not a readable ZIP ({exc}); download it again") from exc
    if bad is not None:
        raise BtsFileError(f"{path.name}: corrupt member {bad}; download it again")
    missing = [t for t in tables if t not in members]
    if missing:
        raise BtsFileError(f"{path.name}: no monthly {', '.join(missing)} file")
    months = {members[t][0] for t in tables}
    if len(months) != 1:
        raise BtsFileError(f"{path.name}: tables cover different months {sorted(months)}")
    return MonthFile(month=months.pop(), path=path, members={t: members[t][1] for t in tables})


def scan_dir(directory: Path, tables: list[str]) -> tuple[dict[str, MonthFile], list[str]]:
    """Every readable month in `directory`, and an error message per ZIP that can't be used."""
    months: dict[str, MonthFile] = {}
    errors: list[str] = []
    for path in sorted(directory.glob("*.zip")):
        try:
            month_file = read_month_file(path, tables)
        except BtsFileError as exc:
            errors.append(str(exc))
            continue
        existing = months.get(month_file.month)
        if existing is not None:
            if sha256_hex(existing.path.read_bytes()) != sha256_hex(path.read_bytes()):
                errors.append(
                    f"{path.name}: {month_file.month} is also in {existing.path.name} with "
                    "different contents; keep one"
                )
            continue
        months[month_file.month] = month_file
    return months, errors


def parse_zip(body: bytes, config: BtsTransborderConfig) -> ParsedSource:
    """Filtered rows for `raw.bts_transborder` from one month's ZIP."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        members = monthly_members(zf.namelist())
        rows: list[tuple[object, ...]] = []
        received = 0
        released: list[date] = []
        for table in config.tables:
            if table not in members:
                raise BtsFileError(f"no monthly {table} file in the ZIP")
            month, name = members[table]
            released.append(date(*zf.getinfo(name).date_time[:3]))
            with zf.open(name) as f:
                frame = pl.read_csv(f.read(), infer_schema_length=0, encoding="utf8-lossy")
            received += frame.height
            rows.extend(_table_rows(table, month, frame, config))
    return ParsedSource(
        rows=rows,
        rows_received=received,
        source_vintage=f"released {max(released).isoformat()}",
    )


def _table_rows(
    table: str, month: str, frame: pl.DataFrame, config: BtsTransborderConfig
) -> list[tuple[object, ...]]:
    missing = [c for c in (*_REQUIRED[table], *_COMMON) if c not in frame.columns]
    if missing:
        raise BtsFileError(f"{table}: missing columns {missing}")
    year, month_number = int(month[:4]), int(month[5:])
    if "MONTH" not in frame.columns:
        frame = frame.with_columns(pl.lit(str(month_number)).alias("MONTH"))
    for name in ("USASTATE", "DEPE", "MEXSTATE"):
        if name not in frame.columns:
            frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias(name))
    try:
        frame = frame.with_columns([_to_int(c) for c in _INT_COLUMNS])
    except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError) as exc:
        raise BtsFileError(f"{table}: non-numeric value in a numeric column ({exc})") from exc
    wrong_period = frame.filter((pl.col("YEAR") != year) | (pl.col("MONTH") != month_number))
    if wrong_period.height:
        raise BtsFileError(f"{table}: {wrong_period.height} rows are not for {month}")
    kept = frame.filter(
        (pl.col("TRDTYPE") == int(config.trade_type))
        & pl.col("COUNTRY").is_in(config.country_codes)
        & pl.col("COMMODITY2").is_in(config.hs2_chapters)
    )
    return [
        (table, *row)
        for row in kept.select(
            "YEAR",
            "MONTH",
            "TRDTYPE",
            "USASTATE",
            "DEPE",
            "COMMODITY2",
            "DISAGMOT",
            "MEXSTATE",
            "COUNTRY",
            "VALUE",
            "SHIPWT",
            "FREIGHT_CHARGES",
            "DF",
            "CONTCODE",
        ).iter_rows()
    ]


def _to_int(column: str) -> pl.Expr:
    """A text column as Int64, with blank cells as null; a non-numeric value fails the cast."""
    stripped = pl.col(column).str.strip_chars()
    return pl.when(stripped == "").then(None).otherwise(stripped).cast(pl.Int64).alias(column)


def archive_key(month: str) -> str:
    """Archive key for a month's ZIP; the downloaded file name is kept in the manifest params."""
    return object_key(DATASET, month, f"transborder_{month}.zip")


def load_month(
    conn: psycopg.Connection,
    archive: Archive,
    month: str,
    obtain: Callable[[], bytes] | None,
    config: BtsTransborderConfig,
    original_filename: str | None = None,
) -> LoadResult:
    """Archive one month's ZIP (or reuse the archived copy when `obtain` is None) and load it."""
    params: dict[str, object] = {
        "month": month,
        "filters": config.model_dump(exclude={"manual_dir"}),
    }
    if original_filename is not None:
        params["original_filename"] = original_filename
    return load_partition(
        conn,
        archive,
        TARGET,
        month,
        key=archive_key(month),
        content_type="application/zip",
        params=params,
        obtain=obtain,
        parse=lambda body: parse_zip(body, config),
    )
