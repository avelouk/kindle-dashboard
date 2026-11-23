"""Draws the dashboard as a 758x1024 grayscale image (Kindle Paperwhite 1 screen).

Pure Pillow, no I/O besides fonts. Fonts come from the Kindle's own /usr/java/lib/fonts;
for previews on a computer, copy them into ./fonts (see tools/fetch-fonts.sh).
Every section draws independently, so bad data in one never blanks the others."""
import datetime as dt
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 758, 1024
M = 36  # side margin
BLACK, DARK, MID, LIGHT, WHITE = 0, 0x44, 0x88, 0xDD, 0xFF

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"), "/usr/java/lib/fonts"]


BUTTON_ROW = (880, 984)   # y range of the button row
BUTTON_GAP = 20
LIST_BOTTOM_WITH_BUTTONS = 850
LIST_BOTTOM_NO_BUTTONS = 975


def font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name + ".ttf")
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F = {
    "temp": font("Futura-Bold", 84),
    "wx": font("Helvetica_LT_65_Medium", 22),
    "hour": font("Helvetica_LT_65_Medium", 20),
    "hourt": font("Futura-DemiBold", 24),
    "section": font("Futura-Bold", 24),
    "time": font("Futura-DemiBold", 27),
    "title": font("Helvetica_LT_65_Medium", 27),
    "small_time": font("Futura-DemiBold", 22),
    "small": font("Helvetica_LT_65_Medium", 22),
    "button": font("Futura-Bold", 34),
    "button2": font("Futura-DemiBold", 30),
    "footer": font("Helvetica_LT_65_Medium", 18),
}

WMO_TEXT = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm", 99: "Thunderstorm",
}


def wmo_kind(code):
    if code in (0, 1):
        return "sun"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    if code is None:
        return "cloud"
    return "rain"


# ---------- weather icons (drawn, so they scale cleanly) ----------

def _sun(d, cx, cy, r, fill=BLACK):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    for i in range(8):
        a = i * math.pi / 4
        x0, y0 = cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35
        x1, y1 = cx + math.cos(a) * r * 1.8, cy + math.sin(a) * r * 1.8
        d.line((x0, y0, x1, y1), fill=fill, width=max(2, int(r / 5)))


def _cloud(d, cx, cy, s, fill=BLACK, outline=None):
    # s = overall width
    h = s * 0.42
    parts = [
        (cx - s * 0.30, cy - h * 0.05, s * 0.22),
        (cx - s * 0.05, cy - h * 0.40, s * 0.28),
        (cx + s * 0.25, cy - h * 0.10, s * 0.21),
    ]
    for (x, y, r) in parts:
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    d.rounded_rectangle((cx - s * 0.5, cy - h * 0.15, cx + s * 0.46, cy + h * 0.5), radius=int(h * 0.32), fill=fill)


def _moon(d, cx, cy, r):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLACK)
    o = r * 0.55
    d.ellipse((cx - r + o, cy - r - o * 0.4, cx + r + o, cy + r - o * 0.4), fill=WHITE)


def weather_icon(img, kind, cx, cy, size, night=False):
    d = ImageDraw.Draw(img)
    if night and kind == "sun":
        _moon(d, cx, cy, size * 0.3)
    elif night and kind == "partly":
        _moon(d, cx + size * 0.16, cy - size * 0.14, size * 0.2)
        _cloud(d, cx - size * 0.05, cy + size * 0.12, size * 0.78, fill=WHITE)
        _cloud(d, cx - size * 0.05, cy + size * 0.12, size * 0.70, fill=DARK)
    elif kind == "sun":
        _sun(d, cx, cy, size * 0.25)
    elif kind == "partly":
        _sun(d, cx + size * 0.16, cy - size * 0.14, size * 0.17)
        _cloud(d, cx - size * 0.05, cy + size * 0.12, size * 0.78, fill=WHITE)
        _cloud(d, cx - size * 0.05, cy + size * 0.12, size * 0.70, fill=DARK)
    elif kind == "cloud":
        _cloud(d, cx, cy, size * 0.85, fill=DARK)
    elif kind == "fog":
        for i in range(4):
            y = cy - size * 0.24 + i * size * 0.16
            off = (i % 2) * size * 0.08
            d.rounded_rectangle((cx - size * 0.38 + off, y, cx + size * 0.38 - (size * 0.08 - off), y + size * 0.07), radius=4, fill=DARK)
    else:
        _cloud(d, cx, cy - size * 0.10, size * 0.85, fill=DARK)
        base = cy + size * 0.16
        if kind == "rain":
            for i in range(4):
                x = cx - size * 0.27 + i * size * 0.18
                d.line((x, base, x - size * 0.06, base + size * 0.2), fill=BLACK, width=max(2, size // 22))
        elif kind == "snow":
            for i in range(4):
                x = cx - size * 0.27 + i * size * 0.18
                r = size * 0.035
                d.ellipse((x - r, base + size * 0.06 - r, x + r, base + size * 0.06 + r), fill=BLACK)
                d.ellipse((x - r - size * 0.04, base + size * 0.18 - r, x + r - size * 0.04, base + size * 0.18 + r), fill=BLACK)
        else:  # storm
            pts = [(cx + size * 0.02, base - size * 0.02), (cx - size * 0.10, base + size * 0.14),
                   (cx + size * 0.0, base + size * 0.14), (cx - size * 0.08, base + size * 0.30),
                   (cx + size * 0.12, base + size * 0.08), (cx + size * 0.02, base + size * 0.08)]
            d.polygon(pts, fill=BLACK)


# ---------- helpers ----------

def text_w(d, s, f):
    return d.textlength(str(s).replace("\n", " "), font=f)


def ellipsize(d, s, f, max_w):
    """Cut text to fit max_w pixels, adding an ellipsis. Binary search: fast for any length."""
    s = str(s)[:300]
    if text_w(d, s, f) <= max_w:
        return s
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_w(d, s[:mid] + "…", f) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip() + "…"


MARKERS = ("circle", "square", "ring", "diamond")


def cal_marker(d, marker, x, y, r=7):
    """Small shape that tells calendars apart: circle, square, ring or diamond."""
    if marker == "square":
        d.rectangle((x - r, y - r, x + r, y + r), fill=BLACK)
    elif marker == "ring":
        d.ellipse((x - r, y - r, x + r, y + r), outline=BLACK, width=3)
    elif marker == "diamond":
        d.polygon([(x, y - r - 1), (x + r + 1, y), (x, y + r + 1), (x - r - 1, y)], fill=BLACK)
    else:
        d.ellipse((x - r, y - r, x + r, y + r), fill=BLACK)


def parse_local(s):
    return dt.datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")


# ---------- header ----------
DIVIDER_X = 420
F_DAY = font("Futura-Bold", 62)
F_DATE = font("Futura-Medium", 30)
F_CLOCK = font("Futura-DemiBold", 30)


def draw_header_left(d, now):
    """Big weekday, date below, clock on the date line right-aligned to the divider."""
    clock = now.strftime("%H:%M")
    d.text((M - 2, 22), now.strftime("%A"), font=F_DAY, fill=BLACK)
    d.text((M, 108), now.strftime("%-d %B"), font=F_DATE, fill=DARK)
    d.text((DIVIDER_X - 24 - text_w(d, clock, F_CLOCK), 108), clock, font=F_CLOCK, fill=BLACK)


def clock_box():
    """Area redrawn every minute (no flash) to tick the clock."""
    return (M - 8, 100, DIVIDER_X - 10, 150)


def button_boxes(buttons):
    """[(button, (x0, y0, x1, y1)), ...] for the bottom row, widths by each button's "weight"."""
    buttons = [b for b in (buttons or []) if isinstance(b, dict) and b.get("id")][:4]
    if not buttons:
        return []
    def weight(b):
        try:
            return min(10.0, max(0.2, float(b.get("weight", 1))))
        except (TypeError, ValueError):
            return 1.0

    weights = [weight(b) for b in buttons]
    free = W - 2 * M - BUTTON_GAP * (len(buttons) - 1)
    out, x = [], M
    for b, w in zip(buttons, weights):
        bw = free * w / sum(weights)
        out.append((b, (int(x), BUTTON_ROW[0], int(x + bw), BUTTON_ROW[1])))
        x += bw + BUTTON_GAP
    return out


# ---------- main render ----------
# Each section draws independently: bad data in one never blanks the others.

def _num(v):
    return v is not None and isinstance(v, (int, float))


def _weather_header(img, d, now, weather):
    cur, daily = weather["current"], weather["daily"]
    if not _num(cur.get("temperature_2m")):
        raise ValueError("no current temperature")
    temp = "%d°" % round(cur["temperature_2m"])
    tx = W - M - text_w(d, temp, F["temp"])
    d.text((tx, 22), temp, font=F["temp"], fill=BLACK)
    weather_icon(img, wmo_kind(cur.get("weather_code")), int(tx - 62), 78, 104, night=not cur.get("is_day", 1))
    hi = (daily.get("temperature_2m_max") or [None])[0]
    lo = (daily.get("temperature_2m_min") or [None])[0]
    parts = []
    if _num(hi) and _num(lo):
        parts.append("%d° / %d°" % (round(hi), round(lo)))
    mm_day = (daily.get("precipitation_sum") or [None])[0]
    rain = (daily.get("precipitation_probability_max") or [None])[0]
    if _num(mm_day) and mm_day >= 0.05:
        parts.append("%.1f mm" % mm_day)
    elif _num(rain) and rain >= 10:
        parts.append("rain %d%%" % rain)
    line = " · ".join(parts)
    d.text((W - M - text_w(d, line, F["wx"]), 124), line, font=F["wx"], fill=DARK)


def _hourly(img, d, now, weather, y):
    hours = weather["hourly"]
    times = hours.get("time") or []
    n = len(times)
    temps = hours.get("temperature_2m") or [None] * n
    codes = hours.get("weather_code") or [None] * n
    precip = hours.get("precipitation") or [0] * n
    isday = hours.get("is_day") or [1] * n
    first = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    slots = []
    for i in range(min(n, len(temps), len(codes))):
        try:
            ht = parse_local(times[i])
        except Exception:
            continue
        if ht >= first and ht.hour % 2 == 0 and _num(temps[i]):
            mm = sum((precip[j] if j < len(precip) and _num(precip[j]) else 0) for j in range(i, min(i + 2, n)))
            slots.append((ht, temps[i], codes[i], not (isday[i] if i < len(isday) else 1), mm))
        if len(slots) == 7:
            break
    col = (W - 2 * M) / max(1, len(slots))
    for i, (ht, temp_h, code, night, mm) in enumerate(slots):
        cx = M + col * i + col / 2
        lab = ht.strftime("%H:%M")
        d.text((cx - text_w(d, lab, F["hour"]) / 2, y + 12), lab, font=F["hour"], fill=DARK)
        weather_icon(img, wmo_kind(code), int(cx), y + 62, 44, night=night)
        tl = "%d°" % round(temp_h)
        d.text((cx - text_w(d, tl, F["hourt"]) / 2, y + 88), tl, font=F["hourt"], fill=BLACK)
        ml = ("%.1f mm" % mm) if mm >= 0.05 else "–"
        d.text((cx - text_w(d, ml, F["hour"]) / 2, y + 122), ml, font=F["hour"], fill=BLACK if mm >= 0.05 else MID)


def _events(d, now, events, y, list_bottom):
    today = now.date()
    by_day = {}
    for ev in events or []:
        try:
            s_, e_ = parse_local(ev["start"]), parse_local(ev["end"])
            title = " ".join(str(ev.get("title") or "Busy").split()) or "Busy"  # one line, no tabs/newlines
            item = {"title": title, "s": s_, "e": e_,
                    "allDay": bool(ev.get("allDay")), "marker": ev.get("marker")}
        except Exception:
            continue
        if item["allDay"]:
            day, last = s_.date(), max(s_.date(), (e_ - dt.timedelta(seconds=1)).date())
            while day <= last and day <= today + dt.timedelta(days=7):
                by_day.setdefault(day, []).append(item)
                day += dt.timedelta(days=1)
        else:
            if s_.date() < today <= e_.date() and e_ > now:
                by_day.setdefault(today, []).append(item)  # multi-day event still running
            elif not (e_ <= now and s_.date() == today):
                by_day.setdefault(s_.date(), []).append(item)

    def order(lst):
        return sorted(lst, key=lambda e: (not e["allDay"], e["s"]))

    d.text((M, y), "TODAY", font=F["section"], fill=BLACK)
    y += 38
    todays = order(by_day.get(today, []))
    if not todays:
        d.text((M, y), "Nothing left today", font=F["title"], fill=MID)
        y += 44
    marked = False
    for idx, ev in enumerate(todays):
        if y > list_bottom - 150:
            d.text((M, y), "+ %d more" % (len(todays) - idx), font=F["small"], fill=MID)
            y += 34
            break
        try:
            is_now = not ev["allDay"] and ev["s"] <= now < ev["e"]
            is_next = not ev["allDay"] and not marked and ev["s"] > now
            if is_now or is_next:
                marked = True
                d.rectangle((M - 16, y + 2, M - 10, y + 34), fill=BLACK)
            if ev["allDay"]:
                tlabel = "All day"
            elif ev["s"].date() < today:
                tlabel = "→" + ev["e"].strftime("%H:%M")  # started earlier, show when it ends
            else:
                tlabel = ev["s"].strftime("%H:%M")
            d.text((M, y), tlabel, font=F["time"], fill=BLACK)
            cal_marker(d, ev["marker"], M + 134, y + 18)
            title = ev["title"] + ("  · now" if is_now else "")
            d.text((M + 154, y), ellipsize(d, title, F["title"], W - 2 * M - 154), font=F["title"], fill=BLACK)
        except Exception:
            pass
        y += 46

    y += 10
    day = today + dt.timedelta(days=1)
    while y < list_bottom - 60 and day <= today + dt.timedelta(days=6):
        # later days: skip continuations of events that started earlier (shown on their first day)
        evs = order([e for e in by_day.get(day, []) if e["s"].date() >= day])
        if evs:
            d.line((M, y, W - M, y), fill=LIGHT, width=2)
            y += 12
            d.text((M, y), day.strftime("%a %-d").upper(), font=F["section"], fill=DARK)
            y += 36
            for ev in evs:
                if y > list_bottom - 34:
                    break
                try:
                    tlabel = "All day" if ev["allDay"] else ev["s"].strftime("%H:%M")
                    d.text((M, y), tlabel, font=F["small_time"], fill=DARK)
                    cal_marker(d, ev["marker"], M + 134, y + 14, r=6)
                    d.text((M + 154, y), ellipsize(d, ev["title"], F["small"], W - 2 * M - 154), font=F["small"], fill=DARK)
                except Exception:
                    pass
                y += 34
            y += 6
        day += dt.timedelta(days=1)


def _buttons(d, buttons, button_state):
    boxes = button_boxes(buttons)
    if not boxes:
        return
    d.line((M, BUTTON_ROW[0] - 18, W - M, BUTTON_ROW[0] - 18), fill=BLACK, width=2)
    for b, (x0, y0, x1, y1) in boxes:
        state = button_state.get(b["id"])
        primary = b.get("style", "outline") == "primary"
        filled = primary != (state == "busy")  # busy = inverted, so the tap is visibly acknowledged
        d.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=BLACK if filled else WHITE, outline=BLACK, width=4)
        labels = {"busy": b.get("busy_label", "Working…"), "ok": b.get("ok_label", "Done"),
                  "fail": b.get("fail_label", "Failed")}
        lab = labels.get(state, str(b.get("label", b["id"])))
        f = F["button"] if primary else F["button2"]
        lab = ellipsize(d, lab, f, x1 - x0 - 24)
        bbox = d.textbbox((0, 0), lab, font=f)
        d.text(((x0 + x1) / 2 - text_w(d, lab, f) / 2, (y0 + y1) / 2 - (bbox[3] - bbox[1]) / 2 - bbox[1]),
               lab, font=f, fill=WHITE if filled else BLACK)


def _footer(d, now, status, errors, legend):
    # legend (right): one marker + name per calendar
    x = W - M
    for name, marker in reversed(list(legend or [])[:4]):
        name = str(name)[:14]
        x -= text_w(d, name, F["footer"])
        d.text((x, 996), name, font=F["footer"], fill=MID)
        x -= 16
        cal_marker(d, marker, x, 1007, r=6)
        x -= 22
    foot = "Updated %s" % now.strftime("%H:%M")
    if status:
        foot += " · " + status
    if errors:
        foot += " · " + ", ".join(errors)
    d.text((M, 996), ellipsize(d, foot, F["footer"], x - M - 8), font=F["footer"], fill=BLACK if errors else MID)


def render(now, weather, events, status=None, button_state=None, errors=(), buttons=(), legend=()):
    """now: naive local datetime. weather: Open-Meteo dict or None.
    events: [{title, start, end ("YYYY-MM-DDTHH:MM" local), allDay, marker}].
    buttons: config button dicts. button_state: {button_id: "busy"|"ok"|"fail"}.
    legend: [(calendar name, marker)]."""
    button_state = button_state or {}
    errors = list(errors or [])
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    def section(name, fn, *a):
        try:
            fn(*a)
        except Exception:
            errors.append("%s error" % name)

    if not (isinstance(weather, dict) and isinstance(weather.get("current"), dict)
            and isinstance(weather.get("daily"), dict)):
        weather = None

    section("clock", draw_header_left, d, now)
    d.line((DIVIDER_X, 30, DIVIDER_X, 150), fill=LIGHT, width=2)
    if weather:
        section("weather", _weather_header, img, d, now, weather)
    else:
        d.text((W - M - text_w(d, "weather offline", F["wx"]), 70), "weather offline", font=F["wx"], fill=MID)
    d.line((M, 170, W - M, 170), fill=BLACK, width=2)
    if weather and isinstance(weather.get("hourly"), dict):
        section("forecast", _hourly, img, d, now, weather, 170)
    d.line((M, 334, W - M, 334), fill=BLACK, width=2)
    try:
        has_buttons = bool(button_boxes(buttons))
    except Exception:
        has_buttons, buttons = False, []
    bottom = LIST_BOTTOM_WITH_BUTTONS if has_buttons else LIST_BOTTOM_NO_BUTTONS
    section("calendar", _events, d, now, events, 352, bottom)
    section("buttons", _buttons, d, buttons, button_state)
    section("footer", _footer, d, now, status, list(dict.fromkeys(errors)), legend)
    return img


def render_fallback(now, message, buttons=()):
    """Last-resort screen: clock, date, message, buttons."""
    img = Image.new("L", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    try:
        draw_header_left(d, now)
        d.text((M, 400), message, font=F["title"], fill=BLACK)
        _buttons(d, buttons, {})
    except Exception:
        pass
    return img
