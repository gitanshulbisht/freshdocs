"""Thin client for the Bright Data Scraper Studio API.

Flow (from the official quickstart):
  POST /dca/trigger?collector=<id>&queue_next=1   -> {"collection_id": "j_..."}
  GET  /dca/dataset?id=<snapshot_id>              -> {"status": "building"} until ready,
                                                    then a JSON array of rows.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.brightdata.com"
TRIGGER_PATH = "/dca/trigger"
DATASET_PATH = "/dca/dataset"

POLL_INTERVAL_S = 5.0
TRIGGER_TIMEOUT_S = 60.0
DATASET_TIMEOUT_S = 60.0


class BrightDataError(RuntimeError):
    """Unrecoverable error from the Bright Data API (auth, bad collector, schema)."""


class BrightDataClient:
    def __init__(self, api_token: Optional[str] = None) -> None:
        self.api_token = api_token or os.environ.get("BRIGHT_DATA_API_TOKEN", "")
        if not self.api_token:
            raise BrightDataError("BRIGHT_DATA_API_TOKEN is not set")
        self._headers = {"Authorization": f"Bearer {self.api_token}"}

    def trigger(self, collector_id: str, inputs: list[dict[str, str]]) -> str:
        """Queue inputs and return the snapshot id (collection_id / j_...)."""
        url = f"{API_BASE}{TRIGGER_PATH}"
        params = {"collector": collector_id, "queue_next": 1}
        response = httpx.post(
            url,
            params=params,
            headers=self._headers,
            json=inputs,
            timeout=TRIGGER_TIMEOUT_S,
        )
        self._raise_for_status(response, "trigger")
        snapshot_id = response.json().get("collection_id")
        if not snapshot_id:
            raise BrightDataError(f"trigger returned no collection_id: {response.text}")
        return snapshot_id

    def dataset(self, snapshot_id: str) -> Any:
        """Fetch the current dataset state for a snapshot."""
        response = httpx.get(
            f"{API_BASE}{DATASET_PATH}",
            params={"id": snapshot_id},
            headers=self._headers,
            timeout=DATASET_TIMEOUT_S,
        )
        self._raise_for_status(response, "dataset")
        return response.json()

    def collect(self, collector_id: str, inputs: list[dict[str, str]],
                max_wait_s: float = 1800.0) -> list[dict[str, Any]]:
        """Trigger + poll until the dataset is ready; return the row list.

        Returns [] (rather than raising) if the snapshot ends with zero rows —
        callers turn that into a health-check failure, which is the signal that
        feeds the self-heal loop.
        """
        snapshot_id = self.trigger(collector_id, inputs)
        log.info("triggered collector=%s snapshot=%s inputs=%d", collector_id, snapshot_id, len(inputs))

        deadline = time.monotonic() + max_wait_s
        while True:
            body = self.dataset(snapshot_id)
            if isinstance(body, list):
                log.info("snapshot %s ready: %d rows", snapshot_id, len(body))
                return body
            status = body.get("status", "unknown") if isinstance(body, dict) else type(body).__name__
            if time.monotonic() > deadline:
                raise BrightDataError(
                    f"timed out after {max_wait_s:.0f}s waiting for snapshot {snapshot_id} "
                    f"(last status: {status})"
                )
            log.debug("snapshot %s still building (status=%s)", snapshot_id, status)
            time.sleep(POLL_INTERVAL_S)

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.status_code == 401:
            raise BrightDataError(f"{operation}: 401 Unauthorized — check BRIGHT_DATA_API_TOKEN")
        if response.status_code == 404:
            raise BrightDataError(f"{operation}: 404 — collector does not exist or account lacks access")
        if response.status_code == 422:
            raise BrightDataError(
                f"{operation}: 422 — input schema mismatch; confirm field names against the collector schema"
            )
        if response.status_code >= 500:
            raise BrightDataError(f"{operation}: {response.status_code} — transient Bright Data error")
        response.raise_for_status()

    def save_rows(self, rows: list[dict[str, Any]], path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, ensure_ascii=False)
