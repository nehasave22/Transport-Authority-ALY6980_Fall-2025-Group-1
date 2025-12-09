
# Capstone/server/app.py (ORCHESTRATOR)
import os, re, json
from typing import List, Literal, Optional, Dict, Tuple
from pathlib import Path
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
import requests

load_dotenv()

ALERTS_AGENT_URL     = os.getenv("ALERTS_AGENT_URL",     "http://alerts-agent:8787")
PLANNER_AGENT_URL    = os.getenv("PLANNER_AGENT_URL",    "http://planner-agent:8787")
STOPFINDER_AGENT_URL = os.getenv("STOPFINDER_AGENT_URL", "http://stopfinder-agent:8787")

ALLOWED_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
INDEX_FILE = WEB_DIR / "index.html"
FAVICON_FILE = WEB_DIR / "favicon.ico"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="MBTA Orchestrator UI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()] or ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

@app.get("/", include_in_schema=False)
def root():
    if INDEX_FILE.exists(): return FileResponse(str(INDEX_FILE))
    return RedirectResponse(url="/docs")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    if FAVICON_FILE.exists(): return FileResponse(str(FAVICON_FILE))
    return Response(status_code=204)

class ChatMessage(BaseModel):
    role: Literal["user","assistant","tool"]
    content: str
class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    intent: Optional[str] = None
class ChatResponse(BaseModel):
    messages: List[ChatMessage]

def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

@lru_cache(maxsize=1)
def load_aliases() -> Dict[str, str]:
    p = DATA_DIR / "aliases.json"
    return {k.lower(): v for k, v in (_load_json(p) if p.exists() else {}).items()}

@lru_cache(maxsize=1)
def load_transfers() -> Dict:
    p = DATA_DIR / "transfers.json"
    return _load_json(p) if p.exists() else {"default_walk_minutes": 3, "pairs": []}

@lru_cache(maxsize=1)
def load_lines() -> Dict[str, Dict]:
    lines_dir = DATA_DIR / "lines"; out = {}
    if lines_dir.exists():
        for f in lines_dir.iterdir():
            if f.suffix == ".json":
                obj = _load_json(f); out[obj["route_id"]] = obj
    return out

@lru_cache(maxsize=1)
def build_graph() -> Dict[str, List[Tuple[str, str]]]:
    graph: Dict[str, List[Tuple[str, str]]] = {}
    lines = load_lines()
    for line in lines.values():
        stops = [s.strip() for s in line["stops"]]
        for i in range(len(stops)-1):
            a, b = stops[i].lower(), stops[i+1].lower()
            graph.setdefault(a, []).append((stops[i+1], line["route_id"]))
            graph.setdefault(b, []).append((stops[i], line["route_id"]))
    for a, b in load_transfers().get("pairs", []):
        graph.setdefault(a.strip().lower(), []).append((b, "walk"))
        graph.setdefault(b.strip().lower(), []).append((a, "walk"))
    return graph

def _normalize_stop_local(name: str) -> str:
    if not name: return ""
    alias_map = load_aliases()
    return alias_map.get(name.strip().lower(), name.strip())

def _bfs_find(origin: str, dest: str):
    graph = build_graph(); o_key, d_key = origin.lower(), dest.lower()
    if o_key not in graph or d_key not in graph: return None
    from collections import deque
    parent: Dict[str, Tuple[str, str]] = {o_key: ("", "")}
    q = deque([o_key])
    while q:
        node = q.popleft()
        if node == d_key: break
        for neigh_name, route_id in graph[node]:
            k = neigh_name.lower()
            if k not in parent:
                parent[k] = (node, route_id)
                q.append(k)
    if d_key not in parent: return None
    names_rev, routes_rev, cur = [], [], d_key
    while cur:
        p, r = parent[cur]; names_rev.append(cur)
        if r: routes_rev.append(r)
        cur = p
    names = [n for n in reversed(names_rev)]
    routes = list(reversed(routes_rev))
    return names, routes

def _compress_into_legs(names: List[str], routes: List[str]) -> List[Dict]:
    if not names or not routes: return []
    legs = []; cur_route = routes[0]; cur_stops = [names[0]]
    for stop_name, r in zip(names[1:], routes):
        if r != cur_route:
            legs.append({"route_id": cur_route, "from": cur_stops[0], "to": cur_stops[-1],
                         "stops_count": max(0, len(cur_stops)-1), "stops_list": cur_stops[:]})
            cur_route, cur_stops = r, [cur_stops[-1]]
        cur_stops.append(stop_name)
    legs.append({"route_id": cur_route, "from": cur_stops[0], "to": cur_stops[-1],
                 "stops_count": max(0, len(cur_stops)-1), "stops_list": cur_stops[:]})
    return legs

def render_legs_human(legs: List[Dict]) -> str:
    out = []
    for leg in legs:
        r = leg["route_id"]
        if r == "walk":
            out.append(f"Walk: {leg['from']} → {leg['to']} (~3 min)")
        else:
            out.append(f"Take **{r}**: {leg['from']} → {leg['to']} (~{leg['stops_count']} stops)")
    return "\\n".join(out)

def a2a_call(base, path, params=None, timeout=6):
    try:
        r = requests.get(f"{base}{path}", params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"A2A error calling {base}{path}: {e}")

def ask_alerts(route: Optional[str]):
    return a2a_call(ALERTS_AGENT_URL, "/alerts", {"route": route} if route else {})

def ask_plan(origin: str, destination: str):
    return a2a_call(PLANNER_AGENT_URL, "/plan", {"origin": origin, "destination": destination})

def ask_plan_direct(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float):
    return a2a_call(PLANNER_AGENT_URL, "/plan-direct",
                    {"origin_lat": origin_lat, "origin_lng": origin_lng, "dest_lat": dest_lat, "dest_lng": dest_lng})

def ask_normalize(name: str):
    return a2a_call(STOPFINDER_AGENT_URL, "/normalize", {"name": name})

class ChatMessage(BaseModel):
    role: Literal["user","assistant","tool"]
    content: str
class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    intent: Optional[str] = None
class ChatResponse(BaseModel):
    messages: List[ChatMessage]

_FROM_TO_RE = re.compile(r"\bfrom\s+(?P<orig>.+?)\s+to\s+(?P<dest>.+)$", re.I)

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    usr = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if not usr:
        return ChatResponse(messages=[ChatMessage(role="assistant", content="Say something to begin.")])
    text = (usr.content or "").strip(); low = text.lower(); history = list(req.messages)

    if req.intent == "alerts" or "alert" in low:
        route = None
        for t in ["green-b","green-c","green-d","green-e","red","orange","blue"]:
            if t in low: route = t.title() if "-" in t else t.capitalize(); break
        out = ask_alerts(route)
        history.append(ChatMessage(role="assistant", content=out.get("text") or "No alerts."))
        return ChatResponse(messages=history)

    if req.intent == "directions" or _FROM_TO_RE.search(text):
        m = _FROM_TO_RE.search(text)
        if not m:
            history.append(ChatMessage(role="assistant", content="Please ask like: ‘directions from X to Y’."))
            return ChatResponse(messages=history)
        origin, dest = m.group("orig").strip(), m.group("dest").strip()
        try:
            norm_o = ask_normalize(origin).get("normalized", origin)
            norm_d = ask_normalize(dest).get("normalized", dest)
        except Exception:
            norm_o, norm_d = origin, dest
        plan = ask_plan(norm_o, norm_d)
        history.append(ChatMessage(role="assistant", content=plan.get("text") or "No route."))
        return ChatResponse(messages=history)

    if "prediction" in low or "arrival" in low or "when is the next" in low:
        history.append(ChatMessage(role="assistant", content="Give me a stop id like place-kencl and I’ll fetch predictions."))
        return ChatResponse(messages=history)

    history.append(ChatMessage(role="assistant", content="Try: ‘alerts for Green-D’, ‘routes’, ‘predictions for Kendall’, or ‘directions from Northeastern University to Government Center’."))
    return ChatResponse(messages=history)


@app.get("/agentfacts")
def get_agentfacts():
    """Serve AgentFacts for NANDA registry"""
    from shared.agentfacts import agentfacts_default
    
    capabilities = [
        "MBTA transit alerts and service updates",
        "Real-time route information",
        "Trip planning and directions",
        "Real-time arrival predictions",
        "Stop finding"
    ]
    
    facts = agentfacts_default(capabilities)
    public_url = os.getenv("PUBLIC_URL", f"http://{PUBLIC_IP}:6000")
    chat_url = os.getenv("CHAT_URL", f"http://{PUBLIC_IP}:8787")
    
    facts["endpoints"] = {
        "https": public_url,
        "a2a": f"{public_url}/a2a",
        "chat": f"{chat_url}/chat",
        "docs": f"{chat_url}/docs"
    }
    facts["name"] = "MBTA Transit Agent"
    facts["version"] = "1.0.0"
    facts["owner"] = "nanda"
    
    return JSONResponse(content=facts)






@app.get("/healthz")
def healthz():
    return {"ok": True, "frontend": INDEX_FILE.exists()}
