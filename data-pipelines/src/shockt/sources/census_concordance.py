"""Census import concordance: one workbook per year mapping HS-10 commodities to NAICS and more.

Partitioned by year. Every row is loaded, so adding a case's HS codes needs no reload.
"""

import io
import zipfile
from collections.abc import Callable

import openpyxl
import psycopg

from shockt.archive import Archive, object_key
from shockt.config import ImportConcordanceConfig
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult
from shockt.sources.reference import ReferenceSourceError

DATASET = "census_import_concordance"
COLUMNS = (
    "commodity",
    "descriptn",
    "abbreviatn",
    "unit_qy1",
    "unit_qy2",
    "sitc",
    "end_use",
    "naics",
    "usda",
    "hitech",
)
TARGET = Target(dataset=DATASET, table=DATASET, columns=("load_id", "year", *COLUMNS))

# Document metadata only; the 2023 workbook's copy has a timestamp openpyxl can't parse.
_CORE_PROPERTIES = "docProps/core.xml"


def url(config: ImportConcordanceConfig, year: int) -> str:
    return config.url_template.format(yy=f"{year % 100:02d}")


def parse_workbook(body: bytes, year: int) -> ParsedSource:
    """Rows of the workbook's single sheet, every value kept as the source string."""
    sheet = openpyxl.load_workbook(
        io.BytesIO(_without_core_properties(body)), read_only=True
    ).worksheets[0]
    rows_iter = sheet.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if header is None or tuple(header) != COLUMNS:
        raise ReferenceSourceError(f"Concordance {year} header is {header}, expected {COLUMNS}")
    rows: list[tuple[object, ...]] = []
    for record in rows_iter:
        if all(v is None for v in record):
            continue
        values: list[str | None] = []
        for column, value in zip(COLUMNS, record, strict=True):
            if value is not None and not isinstance(value, str):
                raise ReferenceSourceError(
                    f"Concordance {year} {column} is {type(value).__name__}, expected text"
                )
            values.append(value.strip() or None if value else None)
        commodity = values[0]
        if commodity is None or len(commodity) != 10 or not commodity.isdigit():
            raise ReferenceSourceError(f"Concordance {year} has commodity {commodity!r}")
        rows.append((year, *values))
    return ParsedSource(rows=rows, rows_received=len(rows), source_version=None)


def load_year(
    conn: psycopg.Connection,
    archive: Archive,
    config: ImportConcordanceConfig,
    year: int,
    obtain: Callable[[], bytes] | None,
    version: str | None,
) -> LoadResult:
    source_url = url(config, year)

    def parse(body: bytes) -> ParsedSource:
        parsed = parse_workbook(body, year)
        return ParsedSource(parsed.rows, parsed.rows_received, version)

    return load_partition(
        conn,
        archive,
        TARGET,
        str(year),
        key=object_key(DATASET, str(year), source_url.rsplit("/", 1)[-1]),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        params={"url": source_url},
        obtain=obtain,
        parse=parse,
    )


def _without_core_properties(body: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(body)) as source:
        if _CORE_PROPERTIES not in source.namelist():
            return body
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                if info.filename != _CORE_PROPERTIES:
                    target.writestr(info, source.read(info))
    return out.getvalue()
