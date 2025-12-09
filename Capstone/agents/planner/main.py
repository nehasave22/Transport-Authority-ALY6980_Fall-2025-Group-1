
# agents/planner/main.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from shared.agentfacts import agentfacts_default
from Capstone.server.app import _normalize_stop_local, _bfs_find, _compress_into_legs, render_legs_human
from Capstone.packages.mbta.mcp_server import plan_direct_route

app = FastAPI(title="planner-agent", version="1.0.0")

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.get("/.well-known/agentfacts.json")
def agentfacts():
    return JSONResponse(agentfacts_default(["mbta.routes.plan"]))

@app.get("/plan")
def plan(origin: str = Query(...), destination: str = Query(...)):
    try:
        o, d = _normalize_stop_local(origin), _normalize_stop_local(destination)
        res = _bfs_find(o, d)
        if not res:
            return {"ok": False, "origin": o, "destination": d, "legs": []}
        names, routes = res
        legs = _compress_into_legs(names, routes)
        return {"ok": True, "origin": o, "destination": d, "legs": legs, "text": render_legs_human(legs)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"plan error: {e}")

@app.get("/plan-direct")
def plan_direct(origin_lat: float = Query(...), origin_lng: float = Query(...),
                dest_lat: float = Query(...), dest_lng: float = Query(...)):
    out = plan_direct_route(origin_lat, origin_lng, dest_lat, dest_lng)
    if not out.get("ok"):
        raise HTTPException(status_code=502, detail=out.get("error", "planner error"))
    return out
