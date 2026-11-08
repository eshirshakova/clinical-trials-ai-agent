"""Silver flatten tests against saved study pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb

from ct_intel.config import load_settings
from ct_intel.silver.normalize import normalize

FIXTURES = Path(__file__).parent / "fixtures"


def write_snapshot(root: Path, timestamp_dirname: str, pages: list[dict]) -> None:
    folder = root / "data" / "bronze" / timestamp_dirname
    folder.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(pages, start=1):
        (folder / f"page_{index:04d}.json").write_text(json.dumps(page), encoding="utf-8")


def load_fixtures() -> list[dict]:
    return [
        json.loads((FIXTURES / "page_1.json").read_text(encoding="utf-8")),
        json.loads((FIXTURES / "page_2.json").read_text(encoding="utf-8")),
    ]


def test_fixture_flattens_studies_conditions_and_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_INTEL_HOME", str(tmp_path))
    write_snapshot(tmp_path, "data_timestamp=2026-11-01T00-00-00", load_fixtures())
    result = normalize(load_settings())

    assert result["studies"] == 3
    assert result["conditions"] == 4
    assert result["locations"] == 2

    settings = load_settings()
    connection = duckdb.connect(str(settings.warehouse_path), read_only=True)
    try:
        boston = connection.execute(
            """
            SELECT brief_title, overall_status, phases, enrollment_count, lead_sponsor,
                   start_date, update_year, city, latitude
            FROM studies s
            JOIN study_locations l USING (nct_id)
            WHERE s.nct_id = 'NCT00000001'
            """
        ).fetchone()
        conditions = connection.execute(
            """
            SELECT condition FROM study_conditions
            WHERE nct_id = 'NCT00000001'
            ORDER BY condition
            """
        ).fetchall()
        asthma_year = connection.execute(
            "SELECT update_year FROM studies WHERE nct_id = 'NCT00000002'"
        ).fetchone()[0]
        unknown_year = connection.execute(
            "SELECT update_year FROM studies WHERE nct_id = 'NCT00000003'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert boston[0] == "Phase 3 Diabetes Trial in Boston"
    assert boston[1] == "RECRUITING"
    assert "PHASE3" in boston[2]
    assert boston[3] == 120
    assert boston[4] == "Example Pharma"
    assert boston[5] == "2026-11-01"
    assert boston[6] == "2026"
    assert boston[7] == "Boston"
    assert boston[8] == 42.336
    assert [row[0] for row in conditions] == ["Obesity", "Type 2 Diabetes"]
    assert asthma_year == "2020"
    assert unknown_year == "unknown"

    partitions = {path.parent.name for path in (settings.silver_dir / "studies").rglob("*.parquet")}
    assert "update_year=2026" in partitions
    assert "update_year=2020" in partitions
    assert "update_year=unknown" in partitions
    assert (settings.silver_dir / "study_locations.parquet").exists()


def copy_snapshot_for_delta(tmp_path: Path, dirname: str, pages: list[dict]) -> None:
    if (tmp_path / "data" / "bronze" / dirname).exists():
        shutil.rmtree(tmp_path / "data" / "bronze" / dirname)
    write_snapshot(tmp_path, dirname, pages)
