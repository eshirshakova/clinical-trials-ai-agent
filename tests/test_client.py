"""Pagination and version-skip behavior. No live API calls."""

from __future__ import annotations

import json

import httpx

from ct_intel.config import load_settings
from ct_intel.ingest.bronze import ingest
from ct_intel.ingest.client import ClinicalTrialsClient


def _client(handler) -> ClinicalTrialsClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ClinicalTrialsClient(http, pause_s=0)


def test_pagination_stops_when_token_missing_and_follows_token():
    seen_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            return httpx.Response(200, json={"apiVersion": "2.0.5", "dataTimestamp": "2026-10-05T09:00:05"})
        token = request.url.params.get("pageToken")
        seen_tokens.append(token)
        if token is None:
            assert request.url.params.get("countTotal") == "true"
            assert request.url.params.get("pageSize") == "100"
            return httpx.Response(
                200,
                json={
                    "studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT1"}}}],
                    "nextPageToken": "tok-2",
                    "totalCount": 2,
                },
            )
        assert token == "tok-2"
        assert "countTotal" not in request.url.params
        return httpx.Response(
            200,
            json={"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT2"}}}]},
        )

    pages = list(_client(handler).iter_study_pages(page_size=100, max_pages=None))
    assert [number for number, _ in pages] == [1, 2]
    assert seen_tokens == [None, "tok-2"]
    assert json.loads(pages[1][1])["studies"][0]["protocolSection"]["identificationModule"]["nctId"] == "NCT2"


def test_pagination_continues_when_page_is_empty_but_token_present():
    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        if token is None:
            return httpx.Response(200, json={"studies": [{"id": 1}], "nextPageToken": "A"})
        if token == "A":
            return httpx.Response(200, json={"studies": [], "nextPageToken": "B"})
        assert token == "B"
        return httpx.Response(200, json={"studies": [{"id": 3}]})

    pages = list(_client(handler).iter_study_pages(page_size=100, max_pages=None))
    assert len(pages) == 3
    assert json.loads(pages[1][1])["studies"] == []
    assert json.loads(pages[2][1])["studies"] == [{"id": 3}]


def test_version_match_skips_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setenv("CT_INTEL_HOME", str(tmp_path))
    calls = {"version": 0, "studies": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            calls["version"] += 1
            return httpx.Response(200, json={"apiVersion": "2.0.5", "dataTimestamp": "2026-10-05T09:00:05"})
        calls["studies"] += 1
        if "pageToken" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT1"}}}],
                    "nextPageToken": "tok",
                },
            )
        return httpx.Response(200, json={"studies": []})

    settings = load_settings()
    api = _client(handler)
    first = ingest(settings, page_size=100, max_pages=5, client=api)
    assert first["skipped"] is False
    assert first["pages"] == 2
    assert (settings.bronze_dir / "data_timestamp=2026-10-05T09-00-05" / "page_0001.json").exists()

    second = ingest(settings, page_size=100, max_pages=5, client=api)
    assert second["skipped"] is True
    assert second["pages"] == 0
    assert calls["studies"] == 2

    third = ingest(settings, page_size=100, max_pages=5, force=True, client=api)
    assert third["skipped"] is False
    assert calls["studies"] == 4
