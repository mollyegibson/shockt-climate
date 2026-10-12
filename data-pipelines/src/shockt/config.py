from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from shockt.settings import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config"

CensusDataset = Literal["hs", "porths", "statehs"]


class DateRange(BaseModel):
    start_month: str
    end_month: str | None = None


class CountryFilter(BaseModel):
    """Keep only countries whose Census code starts with one of `code_prefixes` or is in `codes`."""

    code_prefixes: list[str] = []
    codes: list[str] = []


class CensusRowFilter(BaseModel):
    """Rows dropped as a Census response is parsed into raw."""

    drop_country_groups: bool
    drop_all_zero: bool
    countries: CountryFilter | None = None


class CensusApiConfig(BaseModel):
    base_url: str
    comm_lvl: dict[CensusDataset, str]
    timeout_seconds: float
    filters: dict[CensusDataset, CensusRowFilter]


class BtsTransborderConfig(BaseModel):
    manual_dir: str
    """Directory of monthly ZIPs downloaded from bts.gov, relative to `data-pipelines/`."""
    trade_type: str
    country_codes: list[str]
    hs2_chapters: list[str]
    tables: list[Literal["dot2", "dot3"]]


class PortwatchConfig(BaseModel):
    query_url: str
    page_size: int
    chokepoints: dict[str, str]
    """PortWatch `portid` → chokepoint name."""


class ClimateTraceConfig(BaseModel):
    table: str
    """Fully qualified BigQuery table, project.dataset.table."""
    origin_iso3: list[str]
    destination_iso3: list[str]


class CensusSchedulesConfig(BaseModel):
    schedule_c_url: str
    schedule_d_url: str


class OurAirportsConfig(BaseModel):
    url: str


class GeonamesCitiesConfig(BaseModel):
    url: str
    countries: list[str]


class BorderCrossingsConfig(BaseModel):
    url: str
    border: str
    page_size: int


class ImportConcordanceConfig(BaseModel):
    url_template: str
    """Workbook URL with `{yy}` for the two-digit year."""


class DenueConfig(BaseModel):
    url: str
    industry_digits: int
    """Industry-code prefix length at which DENUE's SCIAN is matched to the concordance's NAICS."""


class ReferenceSourcesConfig(BaseModel):
    ourairports: OurAirportsConfig
    geonames_cities: GeonamesCitiesConfig
    bts_border_crossings: BorderCrossingsConfig
    census_import_concordance: ImportConcordanceConfig
    denue: DenueConfig


class FactorSource(BaseModel):
    url: str
    version: str
    publication: str


class EmissionFactorsConfig(BaseModel):
    uk: FactorSource
    epa: FactorSource


class SourcesConfig(BaseModel):
    """The parts of `config/sources.yaml` the loaders read so far; other sections are ignored."""

    date_range: DateRange
    census_api: CensusApiConfig
    bts_transborder: BtsTransborderConfig
    portwatch: PortwatchConfig
    climatetrace: ClimateTraceConfig
    census_schedules: CensusSchedulesConfig
    reference_sources: ReferenceSourcesConfig
    emission_factors: EmissionFactorsConfig


class HsPrefix(BaseModel):
    prefix: str
    level: str
    label: str
    cases: list[str]


class HsCodesConfig(BaseModel):
    prefixes: list[HsPrefix]


def _load_yaml(path: Path) -> object:
    with path.open() as f:
        return yaml.safe_load(f)


@cache
def sources_config() -> SourcesConfig:
    return SourcesConfig.model_validate(_load_yaml(CONFIG_DIR / "sources.yaml"))


@cache
def hs_codes_config() -> HsCodesConfig:
    return HsCodesConfig.model_validate(_load_yaml(CONFIG_DIR / "hs_codes.yaml"))
