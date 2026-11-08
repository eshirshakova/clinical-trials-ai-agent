"""Read-only SQL guard for Gold DuckDB views."""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|copy|attach|install|pragma)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 200

GOLD_SCHEMA = """
Views (read-only):
- studies_gold(nct_id, brief_title, official_title, overall_status, study_type, phases, enrollment_count, enrollment_type, lead_sponsor, eligibility_criteria, start_date, primary_completion_date, last_update_post_date, update_year, data_timestamp)
- recruitment_status_distribution(overall_status, study_count)
- active_phase3_by_condition(condition, overall_status, study_count)
- site_locations(nct_id, brief_title, overall_status, phases, facility, city, state, country, site_status, latitude, longitude)

phases is a JSON array stored as text, for example ["PHASE3"]. Match it with ILIKE '%PHASE3%'.
Dates are sponsor-submitted strings and may be a year, a month (YYYY-MM), or a day (YYYY-MM-DD).
overall_status values look like RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED.
Use site_locations.city and site_locations.state for place questions. Boston is a city.
""".strip()


class SqlGuardError(ValueError):
    """The statement is not a single read-only query."""


def validate_readonly_sql(sql: str) -> str:
    statement = sql.strip()
    while statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if not statement:
        raise SqlGuardError("SQL is empty.")
    if ";" in statement:
        raise SqlGuardError("Only a single statement is allowed.")
    if not re.match(r"(?is)^(select|with)\b", statement):
        raise SqlGuardError("Only SELECT or WITH queries are allowed.")
    if _FORBIDDEN.search(statement):
        raise SqlGuardError("Write or administrative statements are not allowed.")
    return statement


def execute_readonly(sql: str, warehouse_path: Path) -> str:
    statement = validate_readonly_sql(sql)
    if not warehouse_path.exists():
        raise SqlGuardError(f"Warehouse not found at {warehouse_path}. Run normalize first.")
    connection = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        cursor = connection.execute(statement)
        description = cursor.description or []
        columns = [column[0] for column in description]
        rows = cursor.fetchmany(_MAX_ROWS + 1)
    finally:
        connection.close()
    truncated = len(rows) > _MAX_ROWS
    visible = rows[:_MAX_ROWS]
    payload = [dict(zip(columns, row, strict=True)) for row in visible]
    body = json.dumps(payload, default=str)
    if truncated:
        return body + f"\n(truncated to {_MAX_ROWS} rows)"
    return body
