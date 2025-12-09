
# agents/stopfinder/main.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from shared.agentfacts import agentfacts_default
from Capstone.server.app import _normalize_stop_local, _bfs_find, _compress_into_legs

app = FastAPI(title="stopfinder-agent", version="1.0.0")

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.get("/.well-known/agentfacts.json")
def agentfacts():
    return JSONResponse(agentfacts_default(["mbta.stops.normalize"]))

@app.get("/normalize")
def normalize(name: str = Query(...)):
    try:
        return {"ok": True, "input": name, "normalized": _normalize_stop_local(name)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"normalize error: {e}")

@app.get("/route-between-stops")
def route_between_stops(origin: str = Query(...), destination: str = Query(...)):
    try:
        o, d = _normalize_stop_local(origin), _normalize_stop_local(destination)
        res = _bfs_find(o, d)
        if not res: return {"ok": False, "origin": o, "destination": d, "legs": []}
        names, routes = res
        legs = _compress_into_legs(names, routes)
        return {"ok": True, "origin": o, "destination": d, "legs": legs}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"route error: {e}")
