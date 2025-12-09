
# Capstone/server/humanize.py
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

_SEVERITY = {0:"ℹ️",1:"ℹ️",2:"⚠️",3:"⚠️",4:"⚠️",5:"⛔",6:"⛔",7:"⛔",8:"⛔",9:"⛔",10:"⛔"}
_EFFECT = {"DELAY":"Delay","SHUTTLE":"Shuttle bus","DETOUR":"Detour","SUSPENSION":"Suspension","STOP_MOVED":"Stop moved"}

def _fmt_time(ts: Optional[str]) -> str:
    if not ts: return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z","+00:00"))
        return dt.strftime("%b %d, %I:%M %p").lstrip("0")
    except Exception:
        return ts

def humanize_alert(alert: Dict[str, Any]) -> str:
    a = alert.get("attributes", {})
    sev = _SEVERITY.get(int(a.get("severity", 0)), "ℹ️")
    effect = _EFFECT.get(a.get("effect", ""), a.get("effect", "").title() or "Notice")
    hdr = a.get("short_header") or a.get("header") or "Service advisory"
    ap = (a.get("active_period") or [{}])[0]
    start = _fmt_time(ap.get("start")); end = _fmt_time(ap.get("end")); life = (a.get("lifecycle","") or "").title()
    when = f" ({life} • {start}–{end})" if start or end or life else ""
    desc = a.get("description") or ""
    return f"{sev} {effect}: {hdr}{when}" + (f"\n{desc}" if desc else "")

def humanize_alerts(alerts: List[Dict[str, Any]], limit: int = 5) -> Tuple[str,int]:
    if not alerts: return ("No current alerts.", 0)
    def rank(a):
        life = (a.get("attributes", {}) or {}).get("lifecycle","")
        order = {"NEW":0,"ONGOING":0,"ACTIVE":0,"UPCOMING":1}.get(life,2)
        sev = int((a.get("attributes", {}) or {}).get("severity", 0))
        return (order, -sev)
    top = sorted(alerts, key=rank)[:limit]
    lines = [humanize_alert(a) for a in top]
    return ("\n\n".join(lines), len(alerts))

def humanize_predictions(items: List[Dict[str,Any]], stop_name: str = "") -> str:
    if not items: return f"No upcoming departures{(' for ' + stop_name) if stop_name else ''}."
    now = datetime.now(timezone.utc)
    times = []
    for it in items[:8]:
        at = (it.get("attributes") or {}).get("arrival_time")
        if not at: continue
        try:
            dt = datetime.fromisoformat(at.replace("Z","+00:00"))
            mins = max(0, int((dt - now).total_seconds() // 60))
            rid = (it.get("relationships",{}).get("route",{}).get("data") or {}).get("id","?")
            times.append(f"{rid} in {mins} min")
        except Exception:
            pass
    return (", ".join(times)) if times else "No upcoming departures."
