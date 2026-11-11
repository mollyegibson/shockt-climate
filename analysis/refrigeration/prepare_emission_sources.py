"""Download public workbooks/reference data and reuse the established factor parsers.

Run in the data-pipelines Python environment from the repository root, before the calculator.
Historical source hashes in outputs/emissions/manifest.json identify this frozen run; a later
airport reference download can differ. No API credentials or database are required.
"""
import json
import urllib.request
from pathlib import Path

from shockt.sources.ghg_factors import parse_epa_gwp, parse_epa_transport, parse_uk_workbook

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "outputs/emissions/sources"
URLS = {
    "uk_2026.xlsx": "https://assets.publishing.service.gov.uk/media/6a6c9748862aaf18d9c62ac9/ghg-conversion-factors-2026-flat-format-revised.xlsx",
    "epa_2025.xlsx": "https://www.epa.gov/system/files/other-files/2025-01/ghg-emission-factors-hub-2025.xlsx",
    "airports.csv": "https://davidmegginson.github.io/ourairports-data/airports.csv",
}
SOURCES.mkdir(parents=True, exist_ok=True)
for name, url in URLS.items():
    if not (SOURCES / name).exists():
        urllib.request.urlretrieve(url, SOURCES / name)
uk = (SOURCES / "uk_2026.xlsx").read_bytes()
epa = (SOURCES / "epa_2025.xlsx").read_bytes()
(SOURCES / "parsed_factors.json").write_text(json.dumps({
    "uk": parse_uk_workbook(uk).rows,
    "epa": parse_epa_transport(epa).rows,
    "gwp": parse_epa_gwp(epa).rows,
}))
print("Official public sources archived and parsed")
