"""Land raw API pages on disk and, when configured, in S3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ct_intel.config import Settings
from ct_intel.ingest.client import ClinicalTrialsClient, default_http_client


def snapshot_dirname(data_timestamp: str) -> str:
    safe = data_timestamp.replace(":", "-")
    return f"data_timestamp={safe}"


def read_version_state(path: Path) -> str | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = payload.get("dataTimestamp")
    return str(value) if value else None


def write_version_state(path: Path, data_timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "dataTimestamp": data_timestamp,
        "ingestedAt": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")


def bronze_key(data_timestamp: str, page_num: int) -> str:
    filename = f"page_{page_num:04d}.json"
    return f"bronze/{snapshot_dirname(data_timestamp)}/{filename}"


def write_page(settings: Settings, data_timestamp: str, page_num: int, raw: bytes) -> Path:
    settings.ensure_dirs()
    folder = settings.bronze_dir / snapshot_dirname(data_timestamp)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"page_{page_num:04d}.json"
    path.write_bytes(raw)
    _maybe_upload_s3(settings, bronze_key(data_timestamp, page_num), raw)
    return path


def _maybe_upload_s3(settings: Settings, key: str, body: bytes) -> None:
    if not settings.s3_bucket:
        return
    import boto3

    client = boto3.client("s3", region_name=settings.aws_region)
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def ingest(
    settings: Settings,
    *,
    page_size: int = 100,
    max_pages: int | None = 5,
    query_cond: str | None = None,
    overall_status: str | None = None,
    force: bool = False,
    client: ClinicalTrialsClient | None = None,
) -> dict[str, Any]:
    http = None
    if client is None:
        http = default_http_client()
        client = ClinicalTrialsClient(http)
    try:
        version = client.fetch_version()
        data_timestamp = str(version["dataTimestamp"])
        previous = read_version_state(settings.state_path)
        if previous == data_timestamp and not force:
            return {
                "skipped": True,
                "data_timestamp": data_timestamp,
                "pages": 0,
                "reason": "dataTimestamp unchanged",
            }

        folder = settings.bronze_dir / snapshot_dirname(data_timestamp)
        if folder.exists():
            for child in folder.glob("page_*.json"):
                child.unlink()

        pages = 0
        for page_num, raw in client.iter_study_pages(
            page_size=page_size,
            max_pages=max_pages,
            query_cond=query_cond,
            overall_status=overall_status,
        ):
            write_page(settings, data_timestamp, page_num, raw)
            pages += 1

        write_version_state(settings.state_path, data_timestamp)
        return {"skipped": False, "data_timestamp": data_timestamp, "pages": pages}
    finally:
        if http is not None:
            http.close()
