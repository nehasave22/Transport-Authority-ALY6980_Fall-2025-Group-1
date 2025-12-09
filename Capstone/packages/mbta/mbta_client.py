
# Capstone/packages/mbta/mbta_client.py
import os, requests
from typing import Optional, Dict, Any

MBTA_BASE = "https://api-v3.mbta.com"
MBTA_API_KEY = os.getenv("MBTA_API_KEY", "")

def _headers() -> Dict[str, str]:
    h = {}
    if MBTA_API_KEY: h["x-api-key"] = MBTA_API_KEY
    return h

def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{MBTA_BASE}{path}"
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()

def get_alerts(route: Optional[str] = None, active_only: bool = True) -> Dict[str, Any]:
    params = {"sort": "-updated_at", "page[limit]": 25, "filter[activity]": "BOARD,EXIT,RIDE"}
    if route: params["filter[route]"] = route
    if active_only: params["filter[active]"] = "true"
    return _get("/alerts", params)

def get_routes() -> Dict[str, Any]:
    params = {"page[limit]": 100, "sort": "type,name", "filter[type]": "0,1,2,3"}
    return _get("/routes", params)

def get_predictions(stop_id: str, limit: int = 10) -> Dict[str, Any]:
    params = {"filter[stop]": stop_id, "page[limit]": limit, "sort": "departure_time"}
    return _get("/predictions", params)
