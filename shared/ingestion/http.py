"""HTTP fetch helper shared by every project's extract task.

Handles retries/backoff for transient failures and rate limits (HTTP 429),
and writes the raw response to disk before any parsing/validation happens,
so a bad transform never destroys the ability to re-run from raw data.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DEFAULT_TIMEOUT = 30


def get_json_with_retry(
    url: str,
    *,
    params: dict | None = None,
    max_attempts: int = 4,
    backoff_seconds: float = 2.0,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                wait = backoff_seconds * attempt
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"GET {url} failed after {max_attempts} attempts") from last_exc


def save_raw_json(payload: Any, *, raw_dir: str, prefix: str) -> str:
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(raw_dir) / f"{prefix}_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return str(out_path)
