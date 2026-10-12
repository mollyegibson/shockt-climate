import csv

import pytest
from pydantic import ValidationError

from shockt.config import (
    CENSUS_ALL_COUNTRIES,
    CensusFilterConfig,
    DateRange,
    HsCodesConfig,
    OriginRegion,
    OriginsConfig,
    OverlandWeightConfig,
    SourcesConfig,
    hs_codes_config,
    origins_config,
    sources_config,
    transforms_config,
)
from shockt.origins import COUNTRIES_SEED, OriginsError, origin_iso3


def test_the_committed_config_files_load() -> None:
    sources_config()
    hs_codes_config()
    origins_config()
    transforms_config()


def test_an_unknown_key_fails_instead_of_being_ignored() -> None:
    raw = sources_config().model_dump()
    raw["portwatch"]["chokepionts"] = {}

    with pytest.raises(ValidationError, match="chokepionts"):
        SourcesConfig.model_validate(raw)


@pytest.mark.parametrize("month", ["2022-1", "2022-13", "January 2022"])
def test_date_range_months_must_be_yyyy_mm(month: str) -> None:
    with pytest.raises(ValidationError):
        DateRange(start_month=month)


def test_hs_prefixes_must_not_nest() -> None:
    with pytest.raises(ValidationError, match="not nested"):
        HsCodesConfig.model_validate(
            {"prefixes": [{"prefix": "8504", "cases": ["a"]}, {"prefix": "850421", "cases": ["a"]}]}
        )


def test_hs_prefixes_must_be_distinct() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        HsCodesConfig.model_validate(
            {
                "prefixes": [
                    {"prefix": "850421", "cases": ["a"]},
                    {"prefix": "850421", "cases": ["b"]},
                ]
            }
        )


def test_for_cases_selects_the_prefixes_of_any_listed_case() -> None:
    config = HsCodesConfig.model_validate(
        {
            "prefixes": [
                {"prefix": "847150", "cases": ["tariffs_2025", "panama_red_sea"]},
                {"prefix": "850421", "cases": ["panama_red_sea"]},
            ]
        }
    )

    assert config.for_cases(["tariffs_2025"]) == ["847150"]


def test_denue_cases_select_at_least_one_configured_prefix() -> None:
    assert hs_codes_config().for_cases(sources_config().reference_sources.denue.cases)


ORIGINS = OriginsConfig(
    regions={
        "asia": OriginRegion(census_code_prefixes=["5"]),
        "mexico": OriginRegion(census_codes=["2010"]),
    }
)


def test_region_of_matches_codes_and_prefixes() -> None:
    assert ORIGINS.region_of("5830") == "asia"
    assert ORIGINS.region_of("2010") == "mexico"
    assert ORIGINS.region_of("1220") is None


def test_origins_only_resolves_to_the_origin_countries_and_the_total() -> None:
    config = CensusFilterConfig(drop_country_groups=True, drop_all_zero=True, origins_only=True)

    countries = config.row_filter(ORIGINS).countries

    assert countries is not None
    assert countries.code_prefixes == ["5"]
    assert countries.codes == ["2010", CENSUS_ALL_COUNTRIES]


def test_no_schedule_c_country_falls_in_two_origin_regions() -> None:
    regions = origins_config().regions
    with COUNTRIES_SEED.open(newline="") as f:
        codes = [row["census_cty_code"] for row in csv.DictReader(f)]

    overlapping = [c for c in codes if sum(r.contains(c) for r in regions.values()) > 1]

    assert overlapping == []


def test_origin_iso3_comes_from_the_schedule_c_seed() -> None:
    iso3 = origin_iso3(ORIGINS)

    assert {"TWN", "CHN", "IND", "SAU", "MEX"} <= set(iso3)
    assert "USA" not in iso3 and "CAN" not in iso3


def test_origin_iso3_fails_when_no_country_matches() -> None:
    with pytest.raises(OriginsError, match="no country"):
        origin_iso3(OriginsConfig(regions={"none": OriginRegion(census_codes=["0000"])}))


def test_hs2_chapters_come_from_the_case_prefixes() -> None:
    config = HsCodesConfig.model_validate(
        {
            "prefixes": [
                {"prefix": "847150", "cases": ["a"]},
                {"prefix": "850421", "cases": ["b"]},
                {"prefix": "853720", "cases": ["b"]},
            ]
        }
    )

    assert config.hs2_chapters() == ["84", "85"]


def test_overland_range_percentiles_must_be_ordered_within_zero_and_one() -> None:
    with pytest.raises(ValidationError, match="range_percentiles"):
        OverlandWeightConfig(min_air_vessel_value_usd=1, range_percentiles=[0.95, 0.05])
    with pytest.raises(ValidationError, match="two values"):
        OverlandWeightConfig(min_air_vessel_value_usd=1, range_percentiles=[0.05, 0.5, 0.95])
