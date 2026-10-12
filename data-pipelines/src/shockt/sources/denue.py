"""INEGI DENUE manufacturing establishments in the industries the case HS codes map to.

The industries are read from `raw.census_import_concordance`: the NAICS codes of every
commodity under a case HS prefix, cut to `industry_digits`, where SCIAN and NAICS agree.
DENUE is a snapshot, loaded as one `latest` partition. Street address and contact columns are
not loaded.
"""

import csv
import io
import zipfile
from collections.abc import Callable, Sequence

import psycopg

from shockt.archive import Archive
from shockt.config import DenueConfig
from shockt.loading import ParsedSource, Target
from shockt.manifest import LoadResult
from shockt.sources import reference
from shockt.sources.census_concordance import DATASET as CONCORDANCE_DATASET

DATASET = "denue_establishments"
SOURCE_COLUMNS = (
    "id",
    "clee",
    "nom_estab",
    "raz_social",
    "codigo_act",
    "nombre_act",
    "per_ocu",
    "cve_ent",
    "entidad",
    "cve_mun",
    "municipio",
    "cve_loc",
    "localidad",
    "tipoUniEco",
    "latitud",
    "longitud",
    "fecha_alta",
)
TARGET = Target(
    dataset=DATASET,
    table=DATASET,
    columns=("load_id", *(c.lower() for c in SOURCE_COLUMNS)),
)
ENCODING = "latin-1"


class DenueError(Exception):
    """DENUE couldn't be filtered or parsed."""


def case_industries(conn: psycopg.Connection, hs_prefixes: Sequence[str], digits: int) -> list[str]:
    """Industry-code prefixes of every commodity under a case HS prefix, across loaded years."""
    rows = conn.execute(
        """
        SELECT DISTINCT left(c.naics, %(digits)s)
        FROM raw.census_import_concordance c
        JOIN raw.load_manifest m USING (load_id)
        WHERE m.dataset = %(dataset)s AND m.status = 'succeeded'
          AND c.naics IS NOT NULL
          AND c.commodity LIKE ANY (%(patterns)s)
        ORDER BY 1
        """,
        {
            "digits": digits,
            "dataset": CONCORDANCE_DATASET,
            "patterns": [f"{prefix}%" for prefix in hs_prefixes],
        },
    ).fetchall()
    industries = [row[0] for row in rows]
    if not industries:
        raise DenueError(
            "No industries found for the case HS codes; load the import concordance first "
            "(shockt ingest census-concordance)"
        )
    return industries


def parse(body: bytes, industries: Sequence[str]) -> ParsedSource:
    """Establishments whose `codigo_act` starts with one of `industries`."""
    wanted = tuple(industries)
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        name = next((n for n in zf.namelist() if n.endswith(".csv") and "conjunto" in n), None)
        if name is None:
            raise DenueError(f"DENUE ZIP has no data CSV: {zf.namelist()}")
        with zf.open(name) as raw_file:
            reader = csv.DictReader(io.TextIOWrapper(raw_file, encoding=ENCODING, newline=""))
            missing = set(SOURCE_COLUMNS) - set(reader.fieldnames or [])
            if missing:
                raise DenueError(f"DENUE CSV is missing columns {sorted(missing)}")
            rows: list[tuple[object, ...]] = []
            received = 0
            for record in reader:
                received += 1
                if not record["codigo_act"].startswith(wanted):
                    continue
                rows.append(
                    (
                        int(record["id"]),
                        *(_text(record[c]) for c in SOURCE_COLUMNS[1:14]),
                        _float(record["latitud"]),
                        _float(record["longitud"]),
                        _text(record["fecha_alta"]),
                    )
                )
    return ParsedSource(rows=rows, rows_received=received, source_version=None)


def load(
    conn: psycopg.Connection,
    archive: Archive,
    config: DenueConfig,
    hs_prefixes: Sequence[str],
    obtain: Callable[[], bytes] | None,
    version: str | None,
) -> LoadResult:
    industries = case_industries(conn, hs_prefixes, config.industry_digits)
    params: dict[str, object] = {
        "url": config.url,
        "hs_prefixes": list(hs_prefixes),
        "industry_digits": config.industry_digits,
        "industries": industries,
        "industries_from": CONCORDANCE_DATASET,
        "encoding": ENCODING,
    }
    return reference.load(
        conn,
        archive,
        TARGET,
        config.url.rsplit("/", 1)[-1],
        "application/zip",
        params,
        obtain,
        lambda body: parse(body, industries),
        version,
    )


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _float(value: str | None) -> float | None:
    value = _text(value)
    return float(value) if value is not None else None
