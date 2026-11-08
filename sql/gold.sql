CREATE OR REPLACE VIEW studies_gold AS
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
    data_timestamp
FROM studies;

CREATE OR REPLACE VIEW recruitment_status_distribution AS
SELECT
    overall_status,
    COUNT(*) AS study_count
FROM studies
GROUP BY overall_status
ORDER BY study_count DESC;

CREATE OR REPLACE VIEW active_phase3_by_condition AS
SELECT
    c.condition,
    s.overall_status,
    COUNT(DISTINCT s.nct_id) AS study_count
FROM studies s
JOIN study_conditions c ON c.nct_id = s.nct_id
WHERE s.phases ILIKE '%PHASE3%'
  AND s.overall_status IN ('RECRUITING', 'NOT_YET_RECRUITING', 'ACTIVE_NOT_RECRUITING')
GROUP BY c.condition, s.overall_status
ORDER BY study_count DESC;

CREATE OR REPLACE VIEW site_locations AS
SELECT
    l.nct_id,
    s.brief_title,
    s.overall_status,
    s.phases,
    l.facility,
    l.city,
    l.state,
    l.country,
    l.site_status,
    l.latitude,
    l.longitude
FROM study_locations l
JOIN studies s USING (nct_id);
