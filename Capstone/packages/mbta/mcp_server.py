
# Capstone/packages/mbta/mcp_server.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any
import math, time

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon/2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _fmt_km(km: float) -> str:
    if km < 1.0: return f"{int(km*1000)} m"
    return f"{km:.1f} km"

@dataclass
class Leg:
    mode: str
    from_point: str
    to_point: str
    distance: str
    est_minutes: int

def plan_direct_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float, radius_m: int = 600) -> Dict[str, Any]:
    try:
        for v in (origin_lat, origin_lng, dest_lat, dest_lng):
            if v is None or not isinstance(v, (int, float)):
                return {"ok": False, "error": "Invalid coordinates"}
        d_km = _haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        est = max(1, int(round(d_km * 12)))
        leg = Leg("walk", f"{origin_lat:.5f},{origin_lng:.5f}", f"{dest_lat:.5f},{dest_lng:.5f}", _fmt_km(d_km), est)
        return {
            "ok": True,
            "summary": f"Walk {leg.distance} (~{leg.est_minutes} min).",
            "legs": [asdict(leg)],
            "metrics": {"distance_km": round(d_km,3), "computed_at": int(time.time()), "radius_m": radius_m}
        }
    except Exception as e:
        return {"ok": False, "error": f"planner failure: {e}"}
