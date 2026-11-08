-- Persistent Silver tables. Flattening lives in the @flatten section and expects
-- a temp table incoming_raw(study_json JSON, content_hash VARCHAR) plus
-- snapshot_meta(data_timestamp VARCHAR).

-- @ddl
CREATE TABLE IF NOT EXISTS studies (
    nct_id VARCHAR PRIMARY KEY,
    brief_title VARCHAR,
    official_title VARCHAR,
    overall_status VARCHAR,
    study_type VARCHAR,
    phases VARCHAR,
    enrollment_count INTEGER,
    enrollment_type VARCHAR,
    lead_sponsor VARCHAR,
    eligibility_criteria VARCHAR,
    start_date VARCHAR,
    primary_completion_date VARCHAR,
    last_update_post_date VARCHAR,
    update_year VARCHAR,
    content_hash VARCHAR NOT NULL,
    data_timestamp VARCHAR,
    ingested_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_conditions (
    nct_id VARCHAR,
    condition VARCHAR
);

CREATE TABLE IF NOT EXISTS study_interventions (
    nct_id VARCHAR,
    intervention_type VARCHAR,
    intervention_name VARCHAR
);

CREATE TABLE IF NOT EXISTS study_locations (
    nct_id VARCHAR,
    facility VARCHAR,
    city VARCHAR,
    state VARCHAR,
    zip VARCHAR,
    country VARCHAR,
    site_status VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE
);

CREATE TABLE IF NOT EXISTS study_changes (
    nct_id VARCHAR,
    change_type VARCHAR,
    old_hash VARCHAR,
    new_hash VARCHAR,
    data_timestamp VARCHAR,
    detected_at TIMESTAMP
);

-- @flatten
CREATE OR REPLACE TEMP TABLE incoming_studies AS
SELECT
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.nctId') AS nct_id,
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.briefTitle') AS brief_title,
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.officialTitle') AS official_title,
    json_extract_string(r.study_json, '$.protocolSection.statusModule.overallStatus') AS overall_status,
    json_extract_string(r.study_json, '$.protocolSection.designModule.studyType') AS study_type,
    CAST(json_extract(r.study_json, '$.protocolSection.designModule.phases') AS VARCHAR) AS phases,
    TRY_CAST(
        json_extract_string(r.study_json, '$.protocolSection.designModule.enrollmentInfo.count') AS INTEGER
    ) AS enrollment_count,
    json_extract_string(r.study_json, '$.protocolSection.designModule.enrollmentInfo.type') AS enrollment_type,
    json_extract_string(r.study_json, '$.protocolSection.sponsorCollaboratorsModule.leadSponsor.name') AS lead_sponsor,
    json_extract_string(r.study_json, '$.protocolSection.eligibilityModule.eligibilityCriteria') AS eligibility_criteria,
    json_extract_string(r.study_json, '$.protocolSection.statusModule.startDateStruct.date') AS start_date,
    json_extract_string(
        r.study_json, '$.protocolSection.statusModule.primaryCompletionDateStruct.date'
    ) AS primary_completion_date,
    json_extract_string(r.study_json, '$.protocolSection.statusModule.lastUpdatePostDateStruct.date') AS last_update_post_date,
    CASE
        WHEN regexp_full_match(
            substr(
                json_extract_string(r.study_json, '$.protocolSection.statusModule.lastUpdatePostDateStruct.date'),
                1,
                4
            ),
            '^[0-9]{4}$'
        )
        THEN substr(
            json_extract_string(r.study_json, '$.protocolSection.statusModule.lastUpdatePostDateStruct.date'),
            1,
            4
        )
        ELSE 'unknown'
    END AS update_year,
    r.content_hash,
    m.data_timestamp,
    current_timestamp AS ingested_at
FROM incoming_raw r
CROSS JOIN snapshot_meta m
WHERE json_extract_string(r.study_json, '$.protocolSection.identificationModule.nctId') IS NOT NULL;

CREATE OR REPLACE TEMP TABLE incoming_conditions AS
SELECT DISTINCT
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.nctId') AS nct_id,
    condition
FROM incoming_raw r,
UNNEST(
    from_json(
        COALESCE(json_extract(r.study_json, '$.protocolSection.conditionsModule.conditions'), '[]'::JSON),
        '["VARCHAR"]'
    )
) AS u(condition)
WHERE condition IS NOT NULL AND condition <> '';

CREATE OR REPLACE TEMP TABLE incoming_interventions AS
SELECT DISTINCT
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.nctId') AS nct_id,
    json_extract_string(item, '$.type') AS intervention_type,
    json_extract_string(item, '$.name') AS intervention_name
FROM incoming_raw r,
UNNEST(
    from_json(
        COALESCE(
            json_extract(r.study_json, '$.protocolSection.armsInterventionsModule.interventions'),
            '[]'::JSON
        ),
        '["JSON"]'
    )
) AS u(item)
WHERE json_extract_string(item, '$.name') IS NOT NULL
   OR json_extract_string(item, '$.type') IS NOT NULL;

CREATE OR REPLACE TEMP TABLE incoming_locations AS
SELECT DISTINCT
    json_extract_string(r.study_json, '$.protocolSection.identificationModule.nctId') AS nct_id,
    json_extract_string(item, '$.facility') AS facility,
    json_extract_string(item, '$.city') AS city,
    json_extract_string(item, '$.state') AS state,
    json_extract_string(item, '$.zip') AS zip,
    json_extract_string(item, '$.country') AS country,
    json_extract_string(item, '$.status') AS site_status,
    TRY_CAST(json_extract_string(item, '$.geoPoint.lat') AS DOUBLE) AS latitude,
    TRY_CAST(json_extract_string(item, '$.geoPoint.lon') AS DOUBLE) AS longitude
FROM incoming_raw r,
UNNEST(
    from_json(
        COALESCE(
            json_extract(r.study_json, '$.protocolSection.contactsLocationsModule.locations'),
            '[]'::JSON
        ),
        '["JSON"]'
    )
) AS u(item);
