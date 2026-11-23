"""The renderer must never raise, whatever data it gets. Run: python3 tests/test_render.py"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kindle"))
import render  # noqa: E402

now = dt.datetime(2026, 11, 23, 16, 52)
good_wx = json.load(open(os.path.join(ROOT, "tests", "sample_weather.json")))
weathers = [None, {}, {"error": True, "reason": "The service is overloaded"}, {"current": {}, "daily": {}},
            {"current": {"temperature_2m": None, "weather_code": None}, "daily": {"temperature_2m_max": [None]},
             "hourly": {"time": ["x"], "temperature_2m": [None], "weather_code": [1]}},
            {"current": {"temperature_2m": 20}, "daily": {}, "hourly": {"time": [], "temperature_2m": []}},
            {"current": "garbage", "daily": [], "hourly": 5}, good_wx]
event_sets = [[], None,
    [{"title": "x" * 5000, "start": "2026-11-23T18:00", "end": "2026-11-23T19:00", "marker": "square"}],
    [{"title": "emoji 🎉 party\nsecond line", "start": "2026-11-23T18:00", "end": "2026-11-23T19:00"}],
    [{"start": "garbage", "end": "2026-11-23T19:00"}, {"title": None, "start": None, "end": None}, {}],
    [{"title": "multi-day", "start": "2026-11-20T00:00", "end": "2026-12-05T00:00", "allDay": True, "marker": "ring"}],
    [{"title": "end before start", "start": "2026-11-23T18:00", "end": "2026-11-22T00:00", "allDay": True}],
    [{"title": "since yesterday", "start": "2026-11-22T22:00", "end": "2026-11-24T02:00", "marker": "diamond"}],
    [{"title": "E%d" % i, "start": "2026-11-%02dT%02d:00" % (23 + i % 7, 8 + i % 12),
      "end": "2026-11-%02dT%02d:30" % (23 + i % 7, 8 + i % 12), "marker": "square"} for i in range(200)]]
button_sets = [[], None, [{"id": "a", "label": "A very long button label that does not fit", "style": "primary"}],
               [{"id": "a", "label": "Go", "style": "primary", "weight": 2}, {"id": "b", "label": "Stop"}],
               [{"id": str(i), "label": str(i)} for i in range(9)], [{"label": "no id"}, "junk", {"id": "x", "weight": "bad"}]]
legends = [[], [("Personal", "circle"), ("Work", "square")], [("x" * 50, "nonsense")] * 9]

n = 0
for w in weathers:
    for e in event_sets:
        for b in button_sets:
            for state in ({}, {"a": "busy"}, {"b": "fail"}):
                img = render.render(now, w, e, status="battery 12%", button_state=state, errors=["x offline"] * 3,
                                    buttons=b, legend=legends[n % 3])
                assert img.size == (render.W, render.H)
                n += 1
render.render_fallback(now, "display error", button_sets[3])
for t in (dt.datetime(2026, 12, 31, 23, 59), dt.datetime(2027, 1, 1, 0, 0), dt.datetime(2028, 2, 29, 23, 30)):
    render.render(t, good_wx, event_sets[-1], buttons=button_sets[3])
print("ok: renderer survived %d combinations" % n)
