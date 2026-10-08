import json

import pytest

from shockt.config import CensusRowFilter
from shockt.sources.census_api import (
    DATASETS,
    CensusResponseError,
    RowFilter,
    month_range,
    parse_bundle,
    parse_rows,
)
from tests.conftest import census_fixture


@pytest.mark.parametrize("endpoint", ["hs", "porths", "statehs"])
def test_parse_rows_maps_every_column(endpoint: str) -> None:
    spec = DATASETS[endpoint]
    body = census_fixture(endpoint)

    rows = list(parse_rows(spec, body))

    assert len(rows) == len(body) - 1
    assert all(len(row) == len(spec.columns) - 1 for row in rows)


def test_parse_rows_types_values_and_reads_first_i_commodity() -> None:
    spec = DATASETS["hs"]
    columns = spec.columns[1:]
    taiwan = dict(zip(columns, next(parse_rows(spec, census_fixture("hs"))), strict=True))

    assert taiwan["i_commodity"] == "8471500150"
    assert taiwan["cty_code"] == "5830"
    assert taiwan["air_wgt_mo"] == 4_333_280
    assert taiwan["ves_wgt_mo"] == 200_800
    assert taiwan["unit_qy1"] == "NO"
    assert taiwan["last_update"] == "0"
    assert taiwan["time"] == "2024-12"


def test_parse_rows_takes_comm_lvl_from_the_appended_predicate() -> None:
    spec = DATASETS["porths"]
    columns = spec.columns[1:]
    row = dict(zip(columns, next(parse_rows(spec, census_fixture("porths"))), strict=True))

    assert row["comm_lvl"] == "HS6"
    assert row["port"] == "1001"


def test_parse_rows_rejects_a_non_integer_value() -> None:
    body = census_fixture("hs")
    body[1][body[0].index("AIR_WGT_MO")] = "12.5"

    with pytest.raises(CensusResponseError, match="row 2"):
        list(parse_rows(DATASETS["hs"], body))


def test_parse_rows_rejects_a_missing_column() -> None:
    body = census_fixture("hs")
    index = body[0].index("VES_WGT_MO")
    body = [row[:index] + row[index + 1 :] for row in body]

    with pytest.raises(CensusResponseError, match="VES_WGT_MO"):
        list(parse_rows(DATASETS["hs"], body))


def test_parse_bundle_skips_empty_responses() -> None:
    bundle = json.dumps(
        {
            "fetched_at": "2026-10-08T00:00:00+00:00",
            "responses": [
                {"params": {}, "status": 200, "body": census_fixture("hs")},
                {"params": {}, "status": 204, "body": None},
            ],
        }
    ).encode()

    keep_all = CensusRowFilter(drop_country_groups=False, drop_all_zero=False)
    parsed = parse_bundle(DATASETS["hs"], bundle, keep_all)

    assert parsed.rows_received == len(parsed.rows) == len(census_fixture("hs")) - 1


def _rows(endpoint: str) -> list[dict[str, object]]:
    spec = DATASETS[endpoint]
    columns = spec.columns[1:]
    return [
        dict(zip(columns, row, strict=True)) for row in parse_rows(spec, census_fixture(endpoint))
    ]


def test_row_filter_drops_country_groups() -> None:
    spec = DATASETS["hs"]
    row_filter = RowFilter(spec, CensusRowFilter(drop_country_groups=True, drop_all_zero=False))

    kept = [r for r in parse_rows(spec, census_fixture("hs")) if row_filter.keep(r)]

    assert all(dict(zip(spec.columns[1:], r, strict=True))["summary_lvl"] == "DET" for r in kept)
    assert len(kept) == len([r for r in _rows("hs") if r["summary_lvl"] == "DET"])


def test_row_filter_drops_all_zero_rows() -> None:
    spec = DATASETS["statehs"]
    row_filter = RowFilter(spec, CensusRowFilter(drop_country_groups=False, drop_all_zero=True))

    kept = {
        dict(zip(spec.columns[1:], r, strict=True))["state"]
        for r in parse_rows(spec, census_fixture("statehs"))
        if row_filter.keep(r)
    }

    assert "AR" not in kept
    assert {"AK", "AL"} <= kept


def test_row_filter_keeps_listed_countries_and_prefixes() -> None:
    spec = DATASETS["porths"]
    config = CensusRowFilter.model_validate(
        {
            "drop_country_groups": False,
            "drop_all_zero": False,
            "countries": {"code_prefixes": ["5"], "codes": ["2010"]},
        }
    )
    row_filter = RowFilter(spec, config)

    kept = {
        dict(zip(spec.columns[1:], r, strict=True))["cty_code"]
        for r in parse_rows(spec, census_fixture("porths"))
        if row_filter.keep(r)
    }

    assert kept == {"5830", "2010"}


def test_month_range_crosses_a_year() -> None:
    assert month_range("2023-11", "2024-02") == ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_month_range_rejects_reversed_bounds() -> None:
    with pytest.raises(ValueError, match="after"):
        month_range("2024-02", "2024-01")
