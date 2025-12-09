from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from shared.agentfacts import agentfacts_default
from Capstone.server.humanize import humanize_alerts
import os, requests, logging

app = FastAPI(title="alerts-agent", version="1.0.0")
log = logging.getLogger("alerts")

MBTA_KEY = os.getenv("MBTA_API_KEY")
if not MBTA_KEY:
    raise RuntimeError("MBTA_API_KEY not set in environment")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/.well-known/agentfacts.json")
def agentfacts():
    return JSONResponse(agentfacts_default(["mbta.service_alerts.read"]))

def get_alerts(route: str | None = None, active_only: bool = True):
    """
    Correct MBTA /alerts call:
      - api_key MUST be a query param
      - use filter[lifecycle], NOT filter[active]
    """
    params = {
        "api_key": MBTA_KEY,
        "sort": "-updated_at",
        "page[limit]": "25",
        "filter[activity]": "BOARD,EXIT,RIDE",
    }
    if route:
        params["filter[route]"] = route

    params["filter[lifecycle]"] = (
        "NEW,ONGOING,UPDATE" if active_only else "NEW,ONGOING,UPDATE,UPCOMING"
    )

    r = requests.get("https://api-v3.mbta.com/alerts", params=params, timeout=10)
    # Log the final URL so we can see the exact query sent
    log.warning("MBTA GET %s", r.url)
    r.raise_for_status()
    return r.json()

@app.get("/alerts")
def alerts(route: str | None = Query(default=None), active_only: bool = True):
    try:
        log.warning("alerts called route=%s active_only=%s", route, active_only)
        data = get_alerts(route=route, active_only=active_only) or {}
        items = data.get("data", [])
        text, total = humanize_alerts(items)
        return {"ok": True, "route": route, "count": total, "text": text, "raw": data}
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"alerts error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"alerts error: {e}") from e
