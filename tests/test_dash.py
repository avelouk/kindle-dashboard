"""Helpers in dash.py: config fallback, log rotation, title cleaning. Run: python3 tests/test_dash.py"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kindle"))
import dash  # noqa: E402

assert dash.clean_title("emoji 🎉 party\nsecond\tline") == "emoji party second line"
assert dash.clean_title(None) == "Busy" and dash.clean_title("") == "Busy"
assert len(dash.clean_title("x" * 999)) == 200

d = tempfile.mkdtemp()
dash.CONFIG, dash.LOG = os.path.join(d, "config.json"), os.path.join(d, "dash.log")
json.dump({"refresh_minutes": 5}, open(dash.CONFIG, "w"))
assert dash.load_config()["refresh_minutes"] == 5
open(dash.CONFIG, "w").write("{broken json")
assert dash.load_config()["refresh_minutes"] == 5, "broken config must keep the last good one"
json.dump({"refresh_minutes": 0}, open(dash.CONFIG, "w"))
assert dash.load_config()["refresh_minutes"] == 2, "refresh is clamped to >= 2 min"

p = os.path.join(d, "c.json")
dash.write_json_atomic(p, {"a": 1})
assert json.load(open(p)) == {"a": 1}

dash.LOG_MAX = 100
for i in range(50):
    dash.log("line", i)
assert os.path.getsize(dash.LOG) < 400 and os.path.exists(dash.LOG + ".1"), "log must rotate"
# tap-to-light: off at rest, on after a tap, off again after `seconds`
calls = []
dash.set_light = lambda level: calls.append(level)
cfg = {"mode": "tap", "level": 13, "seconds": 3}
light = dash.Light(lambda: cfg)
light.apply()
assert calls == [0], calls
light.tapped(); light.tapped()          # second tap only extends the timer
assert calls == [0, 13], calls
light.tick(); assert calls == [0, 13]   # not yet
light.until = 1                          # pretend the time ran out
light.tick(); assert calls == [0, 13, 0], calls
cfg["mode"] = "on"; light.apply(); assert calls[-1] == 13
cfg["mode"] = "keep"; n = len(calls); light.apply(); light.tapped(); light.restore(); assert len(calls) == n
dash.Light(lambda: {"level": "junk"}).settings()  # bad config must not raise
print("ok: dash helpers")
