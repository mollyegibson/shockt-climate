import csv
import io
import zipfile

import openpyxl
import psycopg
import pytest

from shockt.config import DenueConfig, ImportConcordanceConfig
from shockt.sources import census_concordance, denue
from shockt.sources.reference import ReferenceSourceError
from tests.conftest import MemoryArchive

CONCORDANCE = ImportConcordanceConfig(
    url_template="https://example.invalid/concordance/impconcord{yy}.xlsx"
)
DENUE = DenueConfig(
    url="https://example.invalid/denue_00_31-33_csv.zip", industry_digits=5, cases=["tariffs_2025"]
)


def concordance_workbook(*rows: tuple[str | None, ...], core_xml: bytes | None = None) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(census_concordance.COLUMNS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    if core_xml is None:
        return buffer.getvalue()
    source = zipfile.ZipFile(buffer)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            body = core_xml if info.filename == "docProps/core.xml" else source.read(info)
            target.writestr(info, body)
    return out.getvalue()


def commodity(code: str, naics: str) -> tuple[str | None, ...]:
    return (code, "DESCRIPTION", "ABBR", "NO", "X", "75220", "21300", naics, "2", "-")


def denue_zip(*records: dict[str, str]) -> bytes:
    text = io.StringIO()
    writer = csv.DictWriter(
        text, fieldnames=[*denue.SOURCE_COLUMNS, "telefono"], quoting=csv.QUOTE_ALL
    )
    writer.writeheader()
    for record in records:
        writer.writerow({c: record.get(c, "") for c in [*denue.SOURCE_COLUMNS, "telefono"]})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("diccionario_de_datos/denue_diccionario_de_datos.csv", "x")
        zf.writestr(
            "conjunto_de_datos/denue_inegi_31-33_.csv", text.getvalue().encode(denue.ENCODING)
        )
    return buffer.getvalue()


def establishment(id_: str, codigo_act: str) -> dict[str, str]:
    return {
        "id": id_,
        "nom_estab": "FÁBRICA",
        "codigo_act": codigo_act,
        "per_ocu": "251 y más personas",
        "entidad": "Nuevo León",
        "tipoUniEco": "Fijo",
        "latitud": "25.67",
        "longitud": "-100.31",
        "fecha_alta": "2014-12",
    }


def test_url_uses_the_two_digit_year() -> None:
    assert census_concordance.url(CONCORDANCE, 2026).endswith("/impconcord26.xlsx")


def test_parse_workbook_keeps_source_strings() -> None:
    body = concordance_workbook(commodity("8471500150", "334111"))

    parsed = census_concordance.parse_workbook(body, 2026)

    assert parsed.rows == [
        (2026, "8471500150", "DESCRIPTION", "ABBR", "NO", "X", "75220", "21300", "334111", "2", "-")
    ]


def test_parse_workbook_ignores_unreadable_document_metadata() -> None:
    body = concordance_workbook(
        commodity("8471500150", "334111"),
        core_xml=b'<?xml version="1.0"?><cp:coreProperties '
        b'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        b'xmlns:dcterms="http://purl.org/dc/terms/" '
        b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        b'<dcterms:modified xsi:type="dcterms:W3CDTF">2023- 2- 7T19: 3:54Z</dcterms:modified>'
        b"</cp:coreProperties>",
    )

    assert len(census_concordance.parse_workbook(body, 2023).rows) == 1


def test_parse_workbook_rejects_a_changed_header() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(("commodity", "description"))
    buffer = io.BytesIO()
    workbook.save(buffer)

    with pytest.raises(ReferenceSourceError, match="header"):
        census_concordance.parse_workbook(buffer.getvalue(), 2026)


def test_parse_workbook_rejects_a_short_commodity() -> None:
    body = concordance_workbook(commodity("84715001", "334111"))

    with pytest.raises(ReferenceSourceError, match="commodity"):
        census_concordance.parse_workbook(body, 2026)


def test_parse_denue_filters_by_industry_prefix_and_decodes_latin1() -> None:
    body = denue_zip(establishment("1", "334110"), establishment("2", "311812"))

    parsed = denue.parse(body, ["33411"])

    assert parsed.rows_received == 2
    row = dict(zip(denue.TARGET.columns[1:], parsed.rows[0], strict=True))
    assert len(parsed.rows) == 1
    assert row["id"] == 1 and row["nom_estab"] == "FÁBRICA" and row["entidad"] == "Nuevo León"
    assert row["per_ocu"] == "251 y más personas"
    assert row["tipounieco"] == "Fijo"
    assert row["latitud"] == 25.67 and row["clee"] is None


def test_parse_denue_rejects_a_file_without_coordinates() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("conjunto_de_datos/denue_inegi_31-33_.csv", '"id","codigo_act"\n"1","334110"\n')

    with pytest.raises(denue.DenueError, match="latitud"):
        denue.parse(buffer.getvalue(), ["33411"])


def test_denue_load_takes_its_industries_from_the_concordance(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    workbook = concordance_workbook(
        commodity("8471500150", "334111"),
        commodity("8504400000", "335999"),
        commodity("0101210010", "112920"),
    )
    census_concordance.load_year(conn, memory_archive, CONCORDANCE, 2026, lambda: workbook, "test")
    body = denue_zip(
        establishment("1", "334110"),
        establishment("2", "335991"),
        establishment("3", "112920"),
    )

    result = denue.load(conn, memory_archive, DENUE, ["847150", "8504"], lambda: body, "test")

    assert result.row_count == 2
    params = conn.execute(
        "SELECT params FROM raw.load_manifest WHERE load_id = %s", (result.load_id,)
    ).fetchone()
    assert params is not None and params[0]["industries"] == ["33411", "33599"]


def test_denue_load_requires_the_concordance(
    conn: psycopg.Connection, memory_archive: MemoryArchive
) -> None:
    with pytest.raises(denue.DenueError, match="concordance"):
        denue.load(conn, memory_archive, DENUE, ["847150"], lambda: b"", "test")
