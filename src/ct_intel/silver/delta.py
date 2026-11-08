"""Hash study payloads and append insert/update history."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_study_hash(study: dict[str, Any]) -> str:
    encoded = json.dumps(study, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def nct_id_of(study: dict[str, Any]) -> str | None:
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    nct_id = identification.get("nctId")
    if not nct_id:
        return None
    return str(nct_id)


MERGE_SQL = """
CREATE OR REPLACE TEMP TABLE to_replace AS
SELECT i.*
FROM incoming_studies i
LEFT JOIN studies s USING (nct_id)
WHERE s.nct_id IS NULL OR s.content_hash <> i.content_hash;

INSERT INTO study_changes (nct_id, change_type, old_hash, new_hash, data_timestamp, detected_at)
SELECT
    i.nct_id,
    CASE WHEN s.nct_id IS NULL THEN 'insert' ELSE 'update' END,
    s.content_hash,
    i.content_hash,
    i.data_timestamp,
    current_timestamp
FROM to_replace i
LEFT JOIN studies s USING (nct_id);

DELETE FROM study_conditions
WHERE nct_id IN (SELECT nct_id FROM to_replace);

DELETE FROM study_interventions
WHERE nct_id IN (SELECT nct_id FROM to_replace);

DELETE FROM study_locations
WHERE nct_id IN (SELECT nct_id FROM to_replace);

DELETE FROM studies
WHERE nct_id IN (SELECT nct_id FROM to_replace);

INSERT INTO studies
SELECT
    nct_id,
    brief_title,
    official_title,
    overall_status,
    study_type,
    phases,
    enrollment_count,
    enrollment_type,
    lead_sponsor,
    eligibility_criteria,
    start_date,
    primary_completion_date,
    last_update_post_date,
    update_year,
    content_hash,
    data_timestamp,
    ingested_at
FROM to_replace;

INSERT INTO study_conditions
SELECT c.nct_id, c.condition
FROM incoming_conditions c
WHERE c.nct_id IN (SELECT nct_id FROM to_replace);

INSERT INTO study_interventions
SELECT i.nct_id, i.intervention_type, i.intervention_name
FROM incoming_interventions i
WHERE i.nct_id IN (SELECT nct_id FROM to_replace);

INSERT INTO study_locations
SELECT
    l.nct_id,
    l.facility,
    l.city,
    l.state,
    l.zip,
    l.country,
    l.site_status,
    l.latitude,
    l.longitude
FROM incoming_locations l
WHERE l.nct_id IN (SELECT nct_id FROM to_replace);
"""
