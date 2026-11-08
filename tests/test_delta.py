"""SHA-256 change tracking."""

from __future__ import annotations

import copy

import duckdb

from ct_intel.config import load_settings
from ct_intel.silver.normalize import normalize
from tests.test_normalize import copy_snapshot_for_delta, load_fixtures


def _change_rows(warehouse) -> list[tuple]:
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        return connection.execute(
            """
            SELECT nct_id, change_type, old_hash IS NULL, new_hash
            FROM study_changes
            ORDER BY detected_at, nct_id, change_type
            """
        ).fetchall()
    finally:
        connection.close()


def test_changed_payload_appends_one_update_and_identical_appends_none(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_INTEL_HOME", str(tmp_path))
    pages = load_fixtures()
    copy_snapshot_for_delta(tmp_path, "data_timestamp=2026-11-01T00-00-00", pages)
    normalize(load_settings())

    first = _change_rows(load_settings().warehouse_path)
    assert len(first) == 3
    assert {row[1] for row in first} == {"insert"}

    changed_pages = copy.deepcopy(pages)
    changed_pages[0]["studies"][0]["protocolSection"]["statusModule"]["overallStatus"] = "ACTIVE_NOT_RECRUITING"
    copy_snapshot_for_delta(tmp_path, "data_timestamp=2026-11-02T00-00-00", changed_pages)
    second_result = normalize(load_settings())
    assert second_result["changed"] == 1

    second = _change_rows(load_settings().warehouse_path)
    updates = [row for row in second if row[1] == "update"]
    assert len(updates) == 1
    assert updates[0][0] == "NCT00000001"
    assert updates[0][2] is False

    connection = duckdb.connect(str(load_settings().warehouse_path), read_only=True)
    try:
        status = connection.execute(
            "SELECT overall_status FROM studies WHERE nct_id = 'NCT00000001'"
        ).fetchone()[0]
        asthma = connection.execute(
            "SELECT count(*) FROM study_conditions WHERE nct_id = 'NCT00000002'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "ACTIVE_NOT_RECRUITING"
    assert asthma == 1

    third_result = normalize(load_settings())
    assert third_result["changed"] == 0
    assert len(_change_rows(load_settings().warehouse_path)) == len(second)
