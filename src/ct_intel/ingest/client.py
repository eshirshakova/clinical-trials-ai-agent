"""HTTP client for ClinicalTrials.gov API v2."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from ct_intel.config import API_BASE, STUDY_FIELDS, USER_AGENT

RETRY_STATUSES = {429, 500, 502, 503, 504}


class ClinicalTrialsClient:
    def __init__(self, client: httpx.Client, *, pause_s: float = 0.2, retries: int = 5) -> None:
        self._client = client
        self._pause_s = pause_s
        self._retries = retries

    def fetch_version(self) -> dict[str, Any]:
        response = self._request("GET", f"{API_BASE}/version")
        payload = response.json()
        if "dataTimestamp" not in payload:
            raise ValueError("Version response did not include dataTimestamp.")
        return payload

    def iter_study_pages(
        self,
        *,
        page_size: int = 100,
        max_pages: int | None = 5,
        query_cond: str | None = None,
        overall_status: str | None = None,
    ) -> Iterator[tuple[int, bytes]]:
        """Yield (page_number, raw_response_bytes).

        Stop only when nextPageToken is absent. An empty studies array can still
        carry a token, so an empty page is not a stop signal.
        """
        page_token: str | None = None
        page_num = 0
        while True:
            page_num += 1
            if page_num > 1 and self._pause_s:
                time.sleep(self._pause_s)
            params: dict[str, str] = {
                "format": "json",
                "pageSize": str(page_size),
                "fields": STUDY_FIELDS,
            }
            if page_token is None:
                params["countTotal"] = "true"
            else:
                params["pageToken"] = page_token
            if query_cond:
                params["query.cond"] = query_cond
            if overall_status:
                params["filter.overallStatus"] = overall_status

            response = self._request("GET", f"{API_BASE}/studies", params=params)
            yield page_num, response.content

            payload = response.json()
            page_token = payload.get("nextPageToken") or None
            if not page_token:
                break
            if max_pages is not None and page_num >= max_pages:
                break

    def _request(self, method: str, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        delay = 1.0
        last: httpx.Response | None = None
        for attempt in range(self._retries):
            last = self._client.request(method, url, params=params)
            if last.status_code in RETRY_STATUSES and attempt < self._retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            last.raise_for_status()
            return last
        assert last is not None
        last.raise_for_status()
        return last


def default_http_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
    )
