"""Read-only SQL guard."""

import duckdb
import pytest

from ct_intel.agent.sql_tool import SqlGuardError, execute_readonly, validate_readonly_sql
from ct_intel.config import load_settings
from ct_intel.silver.normalize import normalize
from tests.test_normalize import load_fixtures, write_snapshot


def test_rejects_writes_and_multiple_statements():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("DELETE FROM studies")
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("UPDATE studies SET brief_title = 'x'")
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("DROP TABLE studies")
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("SELECT * FROM studies_gold; SELECT 1")
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("PRAGMA database_size")


def test_accepts_select_against_gold_view(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_INTEL_HOME", str(tmp_path))
    write_snapshot(tmp_path, "data_timestamp=2026-11-01T00-00-00", load_fixtures())
    normalize(load_settings())
    warehouse = load_settings().warehouse_path

    raw = execute_readonly(
        "SELECT nct_id, city FROM site_locations WHERE city = 'Boston'",
        warehouse,
    )
    assert "NCT00000001" in raw
    assert "Boston" in raw

    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        count = connection.execute(
            "SELECT study_count FROM active_phase3_by_condition WHERE condition = 'Type 2 Diabetes'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1
