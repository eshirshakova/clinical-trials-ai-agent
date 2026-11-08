"""Paths and environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Piece names, not JSON paths. The API still returns these nested under protocolSection.
# Location fields are requested individually so central-contact emails and phones are omitted.
STUDY_FIELDS = ",".join(
    [
        "NCTId",
        "BriefTitle",
        "OfficialTitle",
        "OverallStatus",
        "StartDate",
        "PrimaryCompletionDate",
        "LastUpdatePostDate",
        "StudyType",
        "Phase",
        "EnrollmentCount",
        "EnrollmentType",
        "Condition",
        "InterventionType",
        "InterventionName",
        "EligibilityCriteria",
        "LeadSponsorName",
        "LocationFacility",
        "LocationCity",
        "LocationState",
        "LocationZip",
        "LocationCountry",
        "LocationStatus",
        "LocationGeoPoint",
    ]
)

API_BASE = "https://clinicaltrials.gov/api/v2"
USER_AGENT = "ct-intel/0.1 (local clinical-trials research pipeline)"


def package_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "sql" / "silver.sql").exists():
            return candidate
    raise FileNotFoundError("Could not locate the project root (pyproject.toml and sql/).")


def data_root() -> Path:
    override = os.environ.get("CT_INTEL_HOME")
    if override:
        return Path(override)
    return package_root()


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    bronze_dir: Path
    silver_dir: Path
    warehouse_path: Path
    state_path: Path
    sql_dir: Path
    google_api_key: str | None
    google_model: str
    s3_bucket: str | None
    aws_region: str | None

    def ensure_dirs(self) -> None:
        self.bronze_dir.mkdir(parents=True, exist_ok=True)
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    root = package_root()
    load_dotenv(root / ".env", override=False)
    data = data_root()
    bucket = os.environ.get("AWS_S3_BUCKET", "").strip() or None
    region = os.environ.get("AWS_REGION", "").strip() or None
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip() or None
    model = os.environ.get("GOOGLE_MODEL", "").strip() or "gemini-2.5-flash"
    return Settings(
        root=root,
        data_dir=data / "data",
        bronze_dir=data / "data" / "bronze",
        silver_dir=data / "data" / "silver",
        warehouse_path=data / "data" / "warehouse.duckdb",
        state_path=data / "data" / "state" / "version.json",
        sql_dir=root / "sql",
        google_api_key=api_key,
        google_model=model,
        s3_bucket=bucket,
        aws_region=region,
    )
