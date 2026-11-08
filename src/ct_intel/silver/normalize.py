"""Flatten the latest Bronze snapshot into Silver tables and Parquet."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import duckdb

from ct_intel.config import Settings
from ct_intel.gold.marts import apply_gold
from ct_intel.silver.delta import MERGE_SQL, canonical_study_hash, nct_id_of
from ct_intel.sql_util import execute_script, split_sql


def latest_snapshot_dir(bronze_dir: Path) -> Path | None:
    if not bronze_dir.exists():
        return None
    folders = [path for path in bronze_dir.iterdir() if path.is_dir() and path.name.startswith("data_timestamp=")]
    if not folders:
        return None
    return sorted(folders, key=lambda path: path.name)[-1]


def load_studies(snapshot_dir: Path) -> list[dict[str, Any]]:
    pages = sorted(snapshot_dir.glob("page_*.json"))
    by_id: dict[str, dict[str, Any]] = {}
    for page_path in pages:
        payload = json.loads(page_path.read_text(encoding="utf-8"))
        for study in payload.get("studies") or []:
            nct_id = nct_id_of(study)
            if nct_id:
                by_id[nct_id] = study
    return list(by_id.values())


def snapshot_timestamp(snapshot_dir: Path) -> str:
    raw = snapshot_dir.name.removeprefix("data_timestamp=")
    return raw


def _split_marked_sql(script: str) -> tuple[str, str]:
    if "-- @flatten" not in script:
        raise ValueError("sql/silver.sql is missing the -- @flatten marker.")
    ddl, flatten = script.split("-- @flatten", 1)
    ddl = ddl.replace("-- @ddl", "")
    return ddl, flatten


def normalize(settings: Settings) -> dict[str, Any]:
    snapshot = latest_snapshot_dir(settings.bronze_dir)
    if snapshot is None:
        raise FileNotFoundError(f"No Bronze snapshots in {settings.bronze_dir}.")

    studies = load_studies(snapshot)
    data_timestamp = snapshot_timestamp(snapshot)
    settings.ensure_dirs()
    settings.warehouse_path.parent.mkdir(parents=True, exist_ok=True)

    script = (settings.sql_dir / "silver.sql").read_text(encoding="utf-8")
    ddl, flatten = _split_marked_sql(script)

    connection = duckdb.connect(str(settings.warehouse_path))
    try:
        execute_script(connection, ddl)
        connection.execute("CREATE OR REPLACE TEMP TABLE incoming_raw (study_json JSON, content_hash VARCHAR)")
        connection.execute("CREATE OR REPLACE TEMP TABLE snapshot_meta (data_timestamp VARCHAR)")
        connection.execute("INSERT INTO snapshot_meta VALUES (?)", [data_timestamp])
        if studies:
            connection.executemany(
                "INSERT INTO incoming_raw VALUES (CAST(? AS JSON), ?)",
                [(json.dumps(study, ensure_ascii=False), canonical_study_hash(study)) for study in studies],
            )
        execute_script(connection, flatten)
        for statement in split_sql(MERGE_SQL):
            connection.execute(statement)
        _export_parquet(connection, settings)
        apply_gold(connection, settings)
        counts = {
            "studies": connection.execute("SELECT count(*) FROM studies").fetchone()[0],
            "changed": connection.execute("SELECT count(*) FROM to_replace").fetchone()[0],
            "conditions": connection.execute("SELECT count(*) FROM study_conditions").fetchone()[0],
            "locations": connection.execute("SELECT count(*) FROM study_locations").fetchone()[0],
        }
    finally:
        connection.close()

    return {"data_timestamp": data_timestamp, "snapshot": str(snapshot), **counts}


def _export_parquet(connection, settings: Settings) -> None:
    studies_dir = settings.silver_dir / "studies"
    if studies_dir.exists():
        shutil.rmtree(studies_dir)
    studies_dir.mkdir(parents=True, exist_ok=True)
    study_count = connection.execute("SELECT count(*) FROM studies").fetchone()[0]
    if study_count:
        destination = (studies_dir).as_posix()
        connection.execute(
            f"COPY studies TO '{destination}' (FORMAT PARQUET, PARTITION_BY (update_year))"
        )
    for table in ("study_conditions", "study_interventions", "study_locations", "study_changes"):
        target = (settings.silver_dir / f"{table}.parquet").as_posix()
        connection.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET)")
