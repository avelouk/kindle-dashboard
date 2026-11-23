"""Kindle dashboard main loop: fetch weather + calendars, draw, handle taps.

Runs on a jailbroken Kindle with NiLuJe's Python 3.9 (+ Pillow) and FBInk from USBNetwork.
Started by /etc/upstart/dash.conf. Exit: tap the top-left corner 5 times within 5 s.
Everything user-specific lives in config.json (see config.example.json).

Design rule: nothing in here may stop the loop. Every network call, draw and tap
handler is isolated; failures are logged, the last good data stays on screen, and
the footer says what is stale.
"""
import datetime as dt
import email.utils
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(HERE, "vendor"))
import render  # noqa: E402

PY = "/mnt/us/python3/bin/python3.9"
CURL = "/mnt/us/usbnet/bin/curl"
FBINK = "/mnt/us/usbnet/bin/fbink"
TOUCH_DEV = "/dev/input/event0"
OUT_PNG = "/tmp/dash.png"
CLOCK_PNG = "/tmp/dash_clock.png"
CACHE = os.path.join(HERE, "cache.json")
CONFIG = os.path.join(HERE, "config.json")
LOG = os.path.join(HERE, "dash.log")
LOG_MAX = 512 * 1024

DEFAULT_CONFIG = {
    "latitude": 51.5072,
    "longitude": -0.1276,
    "timezone": "Europe/London",
    "calendars": [],   # [{"name": "Personal", "url": "https://...ics", "marker": "circle"}]
    "buttons": [],     # [{"id": "...", "label": "...", "command": ["{python}", "integrations/x.py"], ...}]
    "refresh_minutes": 15,
    "restart_hour": 4,  # daily self-restart (fresh process) at this local hour
}
WEATHER_MAX_AGE = 3 * 3600      # hide weather older than this
CALENDAR_MAX_AGE = 48 * 3600    # drop a calendar's events if it hasn't loaded for this long
WIFI_KICK_AFTER = 20 * 60       # restart Wi-Fi if nothing has loaded for this long
MIN_VALID_EPOCH = 1735689600    # 2025-01-01: anything earlier means the clock isn't set


# ---------------------------------------------------------------- helpers

def log(*a):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX:
            os.replace(LOG, LOG + ".1")
        with open(LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except Exception:
        pass  # logging must never break anything


def sh(args, timeout=30):
    """subprocess.run that never raises; returns CompletedProcess or None."""
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout)
    except Exception as e:
        log("command failed", args[0], e)
        return None


_last_good_config = dict(DEFAULT_CONFIG)


def load_config():
    """Config with defaults; a broken file keeps the last good config instead of crashing."""
    global _last_good_config
    try:
        cfg = dict(DEFAULT_CONFIG)
        with open(CONFIG) as f:
            cfg.update(json.load(f))
        cfg["refresh_minutes"] = max(2, int(cfg.get("refresh_minutes", 15)))
        _last_good_config = cfg
    except FileNotFoundError:
        pass
    except Exception as e:
        log("config unreadable, keeping previous:", e)
    return dict(_last_good_config)


def write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def curl(url, out_file, timeout=40, headers_file=None):
    args = [CURL, "-4", "-sSL", "--fail", "-m", str(timeout), "-o", out_file]
    if headers_file:
        args += ["-D", headers_file]
    r = sh(args + [url], timeout=timeout + 15)
    if r is None or r.returncode != 0:
        raise RuntimeError("download failed (%s)" % (r.returncode if r else "timeout"))


_NON_BMP = re.compile("[\U00010000-\U0010FFFF]")


def clean_title(s):
    """One line, no emoji (the Kindle fonts can't draw them), sane length."""
    s = _NON_BMP.sub("", str(s or "")).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return (s or "Busy")[:200]


def battery():
    r = sh(["gasgauge-info", "-c"], timeout=5)
    try:
        return int(r.stdout.decode().strip().rstrip("%"))
    except Exception:
        return None


def keep_awake():
    sh(["lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "1"], timeout=10)


# ---------------------------------------------------------------- dashboard

class Dashboard:
    def __init__(self):
        self.cfg = load_config()
        self.lock = threading.Lock()
        self.weather = None
        self.weather_time = 0
        self.calendars = {}          # url -> {"events": [...], "time": epoch}
        self.utc_offset = -3 * 3600
        self.errors = []
        self.button_state = {}
        self.last_success = time.time()
        self.last_wifi_kick = 0
        self.started = time.time()
        self.running = True
        self._load_cache()
        self.started_day = self.now().date()

    # ---------- cache ----------
    def _load_cache(self):
        try:
            with open(CACHE) as f:
                c = json.load(f)
            w = c.get("weather")
            if isinstance(w, dict) and "current" in w:
                self.weather, self.weather_time = w, float(c.get("weather_time", 0))
            cals = c.get("calendars")
            if isinstance(cals, dict):
                self.calendars = cals
            self.utc_offset = int(c.get("utc_offset", self.utc_offset))
        except Exception:
            pass

    def _save_cache(self):
        try:
            write_json_atomic(CACHE, {"weather": self.weather, "weather_time": self.weather_time,
                                      "calendars": self.calendars, "utc_offset": self.utc_offset})
        except Exception as e:
            log("cache save failed", e)

    # ---------- time ----------
    def now(self):
        return dt.datetime.utcfromtimestamp(time.time() + self.utc_offset)

    def clock_ok(self):
        return time.time() > MIN_VALID_EPOCH

    def check_clock_drift(self, headers_file):
        """Correct the system clock from the weather server's Date header if it drifted > 2 min."""
        try:
            with open(headers_file, errors="replace") as f:
                dates = [l.split(":", 1)[1].strip() for l in f if l.lower().startswith("date:")]
            if not dates:
                return
            server = email.utils.parsedate_to_datetime(dates[-1]).timestamp()
            drift = time.time() - server
            if abs(drift) > 120:
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(server))
                r = sh(["date", "-u", "-s", stamp], timeout=10)
                log("clock drift %.0f s, corrected" % drift, "ok" if r and r.returncode == 0 else "FAILED")
        except Exception as e:
            log("clock check failed", e)

    # ---------- data ----------
    def events(self):
        out = []
        for url, c in self.calendars.items():
            out += c.get("events", [])
        return out

    def fetch(self):
        errors = []
        c = self.cfg
        ok_any = False

        # weather
        try:
            url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=%s"
                   "&current=temperature_2m,weather_code,is_day"
                   "&hourly=temperature_2m,weather_code,is_day,precipitation"
                   "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code"
                   "&forecast_days=2") % (c["latitude"], c["longitude"], c["timezone"].replace("/", "%2F"))
            curl(url, "/tmp/wx.json", headers_file="/tmp/wx.headers")
            with open("/tmp/wx.json") as f:
                wx = json.load(f)
            if not isinstance(wx, dict) or wx.get("error") or not all(k in wx for k in ("current", "hourly", "daily")):
                raise RuntimeError("bad weather reply: %s" % str(wx.get("reason") if isinstance(wx, dict) else wx)[:120])
            self.weather, self.weather_time = wx, time.time()
            self.utc_offset = int(wx.get("utc_offset_seconds", self.utc_offset))
            self.check_clock_drift("/tmp/wx.headers")
            ok_any = True
        except Exception as e:
            log("weather failed:", e)
            errors.append("weather offline")
        if self.weather and time.time() - self.weather_time > WEATHER_MAX_AGE:
            self.weather = None

        # calendars: each source keeps its last good events independently
        urls = []
        for i, src in enumerate(c.get("calendars") or []):
            try:
                url, name, marker = src["url"], str(src.get("name", "calendar %d" % (i + 1))), src.get("marker", "circle")
            except Exception:
                continue
            urls.append(url)
            try:
                evs = self.fetch_ics(url, marker, i)
                self.calendars[url] = {"events": evs, "time": time.time()}
                ok_any = True
            except Exception as e:
                log("calendar %d (%s) failed:" % (i, name), e)
                errors.append("%s offline" % name)
        for url in list(self.calendars):
            stale = time.time() - self.calendars[url].get("time", 0) > CALENDAR_MAX_AGE
            if url not in urls or stale:
                del self.calendars[url]
        if not urls:
            errors.append("no calendars set up")

        if ok_any:
            self.last_success = time.time()
        self.errors = list(dict.fromkeys(errors))  # dedupe, keep order
        self._save_cache()

    def fetch_ics(self, url, marker, idx):
        """Download an iCal feed and expand it (recurrences included) for the next 7 days."""
        import icalendar
        import recurring_ical_events
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(self.cfg["timezone"])
        tmp = "/tmp/cal_%d.ics" % idx
        curl(url, tmp)
        with open(tmp, "rb") as f:
            cal = icalendar.Calendar.from_ical(f.read())
        start = self.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=7)
        out = []
        for ev in recurring_ical_events.of(cal).between(start.replace(tzinfo=tz), end.replace(tzinfo=tz)):
            try:
                if str(ev.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                s_ = ev["DTSTART"].dt
                e_ = ev["DTEND"].dt if ev.get("DTEND") else None
                all_day = not isinstance(s_, dt.datetime)
                if all_day:
                    s_ = dt.datetime.combine(s_, dt.time())
                    e_ = dt.datetime.combine(e_, dt.time()) if e_ else s_ + dt.timedelta(days=1)
                else:
                    s_ = s_.astimezone(tz).replace(tzinfo=None) if s_.tzinfo else s_
                    if e_ is None:
                        e_ = s_
                    elif isinstance(e_, dt.datetime):
                        e_ = e_.astimezone(tz).replace(tzinfo=None) if e_.tzinfo else e_
                    else:
                        e_ = dt.datetime.combine(e_, dt.time())
                if e_ < s_:
                    e_ = s_
                out.append({"title": clean_title(ev.get("SUMMARY")), "start": s_.strftime("%Y-%m-%dT%H:%M"),
                            "end": e_.strftime("%Y-%m-%dT%H:%M"), "allDay": all_day, "marker": marker})
            except Exception as e:
                log("skipped one event:", e)
        out.sort(key=lambda e: e["start"])
        return out[:300]

    def maybe_kick_wifi(self):
        """If nothing has loaded for a while, toggle Wi-Fi (at most every 30 min)."""
        now = time.time()
        if now - self.last_success < WIFI_KICK_AFTER or now - self.last_wifi_kick < 30 * 60:
            return
        self.last_wifi_kick = now
        log("nothing loaded for %d min, restarting Wi-Fi" % ((now - self.last_success) / 60))
        sh(["lipc-set-prop", "com.lab126.cmd", "wirelessEnable", "0"], timeout=20)
        time.sleep(5)
        sh(["lipc-set-prop", "com.lab126.cmd", "wirelessEnable", "1"], timeout=20)

    # ---------- display ----------
    def buttons(self):
        return [b for b in (self.cfg.get("buttons") or []) if isinstance(b, dict) and b.get("id")]

    def legend(self):
        return [(c.get("name", "?"), c.get("marker", "circle")) for c in (self.cfg.get("calendars") or [])
                if isinstance(c, dict)]

    def _render(self, status=None):
        try:
            return render.render(self.now(), self.weather, self.events(), status=status,
                                 button_state=dict(self.button_state), errors=self.errors,
                                 buttons=self.buttons(), legend=self.legend())
        except Exception:
            log("render failed, using fallback", traceback.format_exc())
            return render.render_fallback(self.now(), "display error, see dash.log", self.buttons())

    def draw(self, flash=False):
        with self.lock:
            b = battery()
            status = None if b is None else ("LOW BATTERY %d%%" % b if b < 20 else "battery %d%%" % b)
            self._render(status).save(OUT_PNG)
            args = [FBINK, "-q"] + (["-f"] if flash else []) + ["-g", "file=" + OUT_PNG]
            r = sh(args, timeout=30)
            if r is None or r.returncode != 0:
                log("fbink failed", r.returncode if r else "timeout")

    def draw_clock(self):
        """Redraw only the clock area (no flash)."""
        with self.lock:
            x0, y0, x1, y1 = render.clock_box()
            self._render().crop((x0, y0, x1, y1)).save(CLOCK_PNG)
            sh([FBINK, "-q", "-g", "file=%s,x=%d,y=%d" % (CLOCK_PNG, x0, y0)], timeout=30)

    def safe(self, fn, **kw):
        try:
            fn(**kw)
        except Exception:
            log("error in", getattr(fn, "__name__", fn), traceback.format_exc())

    # ---------- buttons ----------
    def press(self, button):
        """Run the button's command (cwd = this folder). Exit code 0 = "ok", anything else = "fail".
        "{python}" in the command is replaced by the Kindle's Python, "{here}" by this folder."""
        name = button["id"]
        if self.button_state.get(name) == "busy":
            return
        cmd = [str(a).replace("{python}", PY).replace("{here}", HERE) for a in (button.get("command") or [])]
        if not cmd:
            return
        self.button_state[name] = "busy"
        self.safe(self.draw)

        def work():
            result = "fail"
            try:
                try:
                    r = subprocess.run(cmd, capture_output=True, cwd=HERE, timeout=int(button.get("timeout", 90)))
                    log("button", name, r.returncode, r.stdout.decode(errors="replace").strip()[-300:],
                        r.stderr.decode(errors="replace").strip()[-300:])
                    result = "ok" if r.returncode == 0 else "fail"
                except Exception as e:
                    log("button", name, "failed:", e)
            finally:
                self.button_state[name] = result
                self.safe(self.draw)
                time.sleep(15)
                self.button_state.pop(name, None)
                self.safe(self.draw)

        threading.Thread(target=work, daemon=True).start()

    # ---------- touch ----------
    def touch_loop(self):
        """Read taps forever; if the device errors out, reopen it."""
        while self.running:
            try:
                self._touch_once()
            except Exception:
                log("touch error, reopening", traceback.format_exc())
                time.sleep(5)

    def _touch_once(self):
        fmt = "llHHi"
        size = struct.calcsize(fmt)
        x = y = None
        corner_taps = []
        with open(TOUCH_DEV, "rb") as f:
            while self.running:
                data = f.read(size)
                if len(data) < size:
                    time.sleep(0.1)
                    continue
                _, _, etype, code, value = struct.unpack(fmt, data)
                if etype == 3 and code in (0, 53):
                    x = value
                elif etype == 3 and code in (1, 54):
                    y = value
                elif etype == 1 and code == 330 and value == 0 and x is not None and y is not None:
                    try:
                        self.on_tap(x, y, corner_taps)
                    except Exception:
                        log("tap handler error", traceback.format_exc())

    def on_tap(self, x, y, corner_taps):
        if x < 120 and y < 120:
            t = time.time()
            corner_taps[:] = [c for c in corner_taps if t - c < 5] + [t]
            if len(corner_taps) >= 5:
                log("exit gesture")
                open("/tmp/dash_exited", "w").close()  # stay in normal Kindle mode until reboot
                self.running = False
            return
        for button, (x0, y0, x1, y1) in render.button_boxes(self.buttons()):
            if x0 <= x <= x1 and y0 <= y <= y1:
                log("tap", button["id"])
                self.press(button)
                return

    # ---------- main ----------
    def run(self):
        threading.Thread(target=self.touch_loop, daemon=True).start()
        self.safe(self.draw, flash=True)  # show cached data right away
        next_fetch = 0
        last_hour = self.now().strftime("%Y%m%d%H")
        last_clock = self.now().strftime("%H:%M")
        while self.running:
            try:
                now = self.now()
                if (now.hour == self.cfg.get("restart_hour", 4) and now.date() != self.started_day
                        and time.time() - self.started > 3600):
                    self.restart()
                if time.time() >= next_fetch:
                    self.cfg = load_config()
                    keep_awake()
                    if self.clock_ok():
                        self.safe(self.fetch)
                    else:
                        self.errors = ["waiting for clock"]
                    self.maybe_kick_wifi()
                    next_fetch = time.time() + 60 * (self.cfg["refresh_minutes"] if self.last_success > time.time() - 60 else 2)
                    self.safe(self.draw, flash=True)
                    last_hour = self.now().strftime("%Y%m%d%H")
                elif now.strftime("%Y%m%d%H") != last_hour:
                    last_hour = now.strftime("%Y%m%d%H")
                    self.safe(self.draw)  # hourly: keep now/next markers and past events right
                elif now.strftime("%H:%M") != last_clock:
                    self.safe(self.draw_clock)
                last_clock = self.now().strftime("%H:%M")
            except Exception:
                log("loop error", traceback.format_exc())
            time.sleep(5)

    def restart(self):
        """Daily fresh start in the same process slot (keeps the stock UI stopped)."""
        log("daily restart")
        try:
            os.execv(PY, [PY, os.path.abspath(__file__), "--restarted"])
        except Exception as e:
            log("restart failed", e)


def kindle_ui(enable):
    """Stop/start the stock Kindle UI so it doesn't draw over us or react to taps."""
    if enable:
        sh(["lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "0"], timeout=10)
        sh(["/sbin/start", "lab126_gui"], timeout=60)
    else:
        keep_awake()
        sh(["/sbin/stop", "lab126_gui"], timeout=60)
        time.sleep(2)


if __name__ == "__main__":
    log("starting" + (" (daily restart)" if "--restarted" in sys.argv else ""))
    if "--restarted" not in sys.argv:
        kindle_ui(False)
    try:
        Dashboard().run()
    finally:
        log("stopping")
        kindle_ui(True)
