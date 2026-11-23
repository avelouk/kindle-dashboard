"""Render the dashboard on your computer with sample events + live weather, using your
kindle/config.json (or config.example.json) for location, calendars' legend and buttons.

    python3 tools/preview.py [out.png] [--state BUTTON_ID=busy]

Needs Pillow. Run tools/fetch-fonts.sh once so the fonts match the Kindle.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kindle"))
import render  # noqa: E402

cfg_path = os.path.join(ROOT, "kindle", "config.json")
if not os.path.exists(cfg_path):
    cfg_path = os.path.join(ROOT, "kindle", "config.example.json")
cfg = json.load(open(cfg_path))
cals = cfg.get("calendars") or [{"name": "Calendar", "marker": "circle"}]
m = [c.get("marker", "circle") for c in cals] + ["circle", "square"]

url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=%s"
       "&current=temperature_2m,weather_code,is_day&hourly=temperature_2m,weather_code,is_day,precipitation"
       "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code"
       "&forecast_days=2") % (cfg["latitude"], cfg["longitude"], cfg["timezone"].replace("/", "%2F"))
try:
    wx = json.load(urllib.request.urlopen(url, timeout=20))
    now = dt.datetime.utcnow() + dt.timedelta(seconds=wx["utc_offset_seconds"])
except Exception as e:
    print("weather unavailable (%s), previewing without it" % e)
    wx, now = None, dt.datetime.now()

t = now.date()


def ev(day, h, mi, dur_min, title, marker, all_day=False):
    d = t + dt.timedelta(days=day)
    s = dt.datetime.combine(d, dt.time(h, mi))
    e = s + dt.timedelta(minutes=dur_min)
    if all_day:
        s, e = dt.datetime.combine(d, dt.time()), dt.datetime.combine(d + dt.timedelta(days=1), dt.time())
    return {"title": title, "start": s.strftime("%Y-%m-%dT%H:%M"), "end": e.strftime("%Y-%m-%dT%H:%M"),
            "allDay": all_day, "marker": marker}


events = [
    ev(0, 0, 0, 0, "Birthday: Ana", m[0], True),
    ev(0, now.hour, 0, 60, "Design review", m[1]),
    ev(0, min(now.hour + 2, 22), 30, 60, "Pick up the kids", m[0]),
    ev(0, min(now.hour + 3, 23), 0, 45, "Spanish class", m[0]),
    ev(1, 9, 30, 30, "Team standup", m[1]),
    ev(1, 14, 0, 60, "Dentist", m[0]),
    ev(2, 9, 30, 30, "Team standup", m[1]),
    ev(2, 16, 0, 60, "1:1", m[1]),
]
state = {}
for a in sys.argv[2:]:
    if a.startswith("--state"):
        continue
    if "=" in a:
        k, v = a.split("=", 1)
        state[k] = v
out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else os.path.join(ROOT, "preview.png")
img = render.render(now, wx, events, status="battery 100%", button_state=state,
                    buttons=cfg.get("buttons") or [],
                    legend=[(c.get("name", "?"), c.get("marker", "circle")) for c in cfg.get("calendars") or []])
img.save(out)
print("wrote", out)
