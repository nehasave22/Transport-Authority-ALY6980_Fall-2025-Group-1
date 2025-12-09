# Capstone/packages/mbta/rest_server.py
"""
REST helper module for MBTA API and internal agent HTTP requests.
Keeps all HTTP communication consistent, with:
 - Standardized timeout and headers
 - Optional caching
 - Safe retry on transient network issues

Used primarily by:
 - mbta_client.py
 - orchestrator A2A calls
"""

from __future__ import annotations
import os
import time
import requests
from typing import Optional, Dict, Any, Tuple

# Base MBTA API configuration
MBTA_BASE = "https://api-v3.mbta.com"
MBTA_API_KEY = os.getenv("MBTA_API_KEY", "")
DEFAULT_TIMEOUT = int(os.getenv("MBTA_TIMEOUT", "10"))  # seconds
_CACHE_TTL = 60  # seconds for temporary cache (short-lived)

# simple in-memory cache { (url, sorted(params)) : (timestamp, response_json) }
_cache: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}


def _headers() -> Dict[str, str]:
    """Default HTTP headers for all MBTA API calls."""
    h = {"User-Agent": "MBTA-Agent/1.0"}
    if MBTA_API_KEY:
        h["x-api-key"] = MBTA_API_KEY
    return h


def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """Create a consistent key for caching."""
    key = f"{url}|{sorted(params.items()) if params else ''}"
    return (url, key)


def get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    base_url: str = MBTA_BASE,
    use_cache: bool = True,
    retries: int = 2,
) -> Dict[str, Any]:
    """
    GET wrapper with caching and retry logic.
    Returns a dict parsed from JSON or raises requests.HTTPError.
    """
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    key = _cache_key(url, params)

    # Serve from cache if valid
    if use_cache and key in _cache:
        ts, cached = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return cached

    for attempt in range(1, retries + 2):
        try:
            resp = requests.get(url, params=params or {}, headers=_headers(), timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if use_cache:
                _cache[key] = (time.time(), data)
            return data
        except Exception as e:
            if attempt <= retries:
                time.sleep(0.5 * attempt)
                continue
            raise RuntimeError(f"REST GET failed for {url}: {e}") from e


def post(
    path: str,
    payload: Dict[str, Any],
    base_url: str = MBTA_BASE,
    retries: int = 1,
) -> Dict[str, Any]:
    """POST wrapper for JSON API calls."""
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    for attempt in range(1, retries + 2):
        try:
            resp = requests.post(url, json=payload, headers=_headers(), timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt <= retries:
                time.sleep(0.5 * attempt)
                continue
            raise RuntimeError(f"REST POST failed for {url}: {e}") from e


def clear_cache():
    """Manually clears the in-memory cache."""
    _cache.clear()
