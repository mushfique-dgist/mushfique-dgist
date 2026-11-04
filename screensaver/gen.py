"""Build the profile's images from <state>/snapshot.json into <out>.

  hero-light.svg, -dark.svg            a painting of DGIST that follows its season, light and weather, with a pin where Mushfique is (campus_painted.py)
  readme/<scene>-light.svg, -dark.svg  the nine screensavers the die opens, one at random
  die.svg                              the shuffle icon for the screensaver room
  manifest.json                        what this build made

A README image cannot fetch or read the clock, so every live number is baked in here and ticks
forward from its build-time value at its real rate.
"""
import base64
import hashlib
import html
import io
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from fontTools import subset
from fontTools.ttLib import TTFont

FONTS = Path(__file__).parent / "fonts"
W, H = 880, 200
LIGHT_DAY_AT = datetime(2026, 11, 19, 2, 17, tzinfo=timezone.utc)
PULSAR_P = 0.714519699726
SCREEN_BG = "#05070b"
EDGE = "#30363d"
PAL = {"ink": "#e6edf3", "muted": "#8b949e", "faint": "#262c36", "warm": "#e3b341", "red": "#ff7b72", "dim": "#5c6570"}

MONO = "'RM',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
LIGHT = "'RML',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SERIF = "'News',Georgia,'Times New Roman',serif"
FACES = {"mono": ("RM", "ReadmeMono-Regular.ttf"), "light": ("RML", "ReadmeMono-Light.ttf"), "serif": ("News", "Newsreader-Italic.ttf")}
ZONE = {"offset": 9 * 3600, "abbr": "KST"}


@dataclass
class Scene:
    title: str
    body: str
    css: str = ""
    defs: str = ""
    fonts: tuple = ("mono",)
    w: int = W
    h: int = H


@lru_cache(None)
def face_css(key, chars):
    family, file = FACES[key]
    f = TTFont(FONTS / file)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern"]
    opts.name_IDs = []
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(text=chars)
    sub.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    return f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{base64.b64encode(buf.getvalue()).decode()}) format('woff2')}}"


@lru_cache(None)
def _metrics():
    f = TTFont(FONTS / FACES["serif"][1])
    return f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm


def serif_width(s, size):
    cmap, hmtx, upm = _metrics()
    return sum(hmtx[cmap.get(ord(ch), cmap[32])][0] for ch in s) * size / upm


def fonts(*names):
    return names


def num(v, d=1):
    s = f"{v:.{d}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def attr(s):
    return escape(s, {'"': "&quot;"})


def text(x, y, s, size, fill, fam=MONO, anchor=None, ls=None, opacity=None):
    a = f' x="{num(x)}" y="{num(y)}" font-family="{fam}" font-size="{size}" fill="{fill}"'
    a += f' text-anchor="{anchor}"' if anchor else ""
    a += f' letter-spacing="{ls}"' if ls else ""
    a += f' opacity="{opacity}"' if opacity is not None else ""
    return f"<text{a}>{escape(s)}</text>"


def svg(title, body, css="", font_names=("mono",), defs="", w=W, h=H):
    clip = f'<clipPath id="scr"><rect width="{w}" height="{h}" rx="12"/></clipPath>'
    return Scene(title, body, css, defs + clip, tuple(font_names), w, h)


def screen(t=None, w=W, h=H):
    return f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="{SCREEN_BG}"/>'


def render(sc, edge=False, base=False):
    chars = "".join(sorted(set(html.unescape("".join(re.findall(r">([^<>]+)<", sc.body)))) | set("0123456789,. ")))
    font_css = "".join(face_css(k, chars) for k in FACES if k in sc.fonts)
    under = screen(w=sc.w, h=sc.h) if base else ""
    over = f'<rect x="0.5" y="0.5" width="{sc.w - 1}" height="{sc.h - 1}" rx="12" fill="none" stroke="{EDGE}"/>' if edge else ""
    reduce = "@media (prefers-reduced-motion:reduce){*{animation-play-state:paused!important}}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sc.w} {sc.h}" width="{sc.w}" height="{sc.h}" role="img" aria-label="{attr(sc.title)}">'
            f"<title>{escape(sc.title)}</title><style>{font_css}{sc.css}{reduce}</style><defs>{sc.defs}</defs>{under}{sc.body}{over}</svg>")


def stamp(iso, fmt="%H:%M"):
    dt = datetime.fromisoformat(iso).astimezone(timezone.utc) + timedelta(seconds=ZONE["offset"])
    return f"{dt:{fmt}} {ZONE['abbr']}"


def odometer(oid, x, y, value, rate, ndigits, size, color, sep=True, fam=LIGHT):
    """Digit strips that roll like a mechanical counter, starting at `value` and gaining `rate` per second.

    Digit k shows floor(v / 10^k) mod 10. Its strip cycles once per 10^(k+1) / rate seconds and starts
    at a negative delay equal to the time already spent in the current cycle. Digits slower than six
    hours per step stay static: their keyframe offsets would underflow and they never move while
    someone is looking. Digits faster than 0.6 s per step jump instead of rolling, so a frame never
    shows two half digits.
    """
    adv = 0.6 * size
    pitch = round(size * 1.3, 2)
    css, body = [], []
    cx = x
    for idx in range(ndigits):
        k = ndigits - 1 - idx
        step = 10**k / rate
        if step > 6 * 3600:
            body.append(f'<text x="{num(cx)}" y="{num(y)}">{int(value // 10**k) % 10}</text>')
        else:
            cycle = 10 * step
            delay = -((value % 10 ** (k + 1)) / rate)
            name = f"{oid}{k}"
            if step < 0.6:
                frames = f"to{{transform:translateY(-{num(10 * pitch, 2)}px)}}"
                timing = "steps(10)"
            else:
                roll = min(0.3, step * 0.4) / cycle
                frames = "".join(
                    f"{i * 10:.7f}%,{(i + 1) * 10 - roll * 100:.7f}%{{transform:translateY(-{num(i * pitch, 2)}px)}}" for i in range(10)
                ) + f"100%{{transform:translateY(-{num(10 * pitch, 2)}px)}}"
                timing = "ease-in-out"
            css.append(f"@keyframes {name}{{{frames}}}.{name}{{animation:{name} {cycle:.6f}s {timing} {delay:.6f}s infinite}}")
            spans = "".join(f'<tspan x="{num(cx)}" y="{num(y + i * pitch)}">{i % 10}</tspan>' for i in range(11))
            body.append(f'<g class="{name}"><text>{spans}</text></g>')
        cx += adv
        if sep and k > 0 and k % 3 == 0:
            body.append(f'<text x="{num(cx - adv * 0.22)}" y="{num(y)}">,</text>')
            cx += adv * 0.55
    top, h = y - size * 1.05, size * 1.4
    defs = (
        f'<linearGradient id="{oid}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset=".16" stop-color="#fff"/><stop offset=".84" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="{oid}m" maskUnits="userSpaceOnUse" x="{num(x - 4)}" y="{num(top)}" width="{num(cx - x + 8)}" height="{num(h)}">'
        f'<rect x="{num(x - 4)}" y="{num(top)}" width="{num(cx - x + 8)}" height="{num(h)}" fill="url(#{oid}g)"/></mask>'
    )
    group = f'<g mask="url(#{oid}m)" font-family="{fam}" font-size="{size}" fill="{color}">{"".join(body)}</g>'
    return defs, group, "".join(css), cx


def starfield(rnd, layers, color="#fff", twinkle=0.2, h=H):
    """Layers of (count, radius, opacity, seconds to cross the screen). Each layer drifts left and wraps."""
    css = ["@keyframes drift{to{transform:translateX(-880px)}}", "@keyframes tw{0%,100%{opacity:var(--o)}50%{opacity:.08}}"]
    out = []
    for li, (count, r, op, period) in enumerate(layers):
        stars = []
        for _ in range(count):
            sx, sy, o = rnd.uniform(0, W), rnd.uniform(0, h), round(op * rnd.uniform(0.5, 1), 2)
            if rnd.random() < twinkle:
                style = f' style="--o:{o};animation:tw {rnd.uniform(2.5, 7):.1f}s ease-in-out {-rnd.uniform(0, 7):.1f}s infinite"'
            else:
                style = f' opacity="{o}"'
            stars.append(f'<circle cx="{num(sx)}" cy="{num(sy)}" r="{r}"{style}/>')
        layer = "".join(stars)
        css.append(f".sl{li}{{animation:drift {period}s linear infinite}}")
        out.append(f'<g class="sl{li}" fill="{color}">{layer}<g transform="translate({W} 0)">{layer}</g></g>')
    return "".join(out), "".join(css)


# ---------- astronomy (low precision, enough to place a disc in a window) ----------

def julian(dt):
    return dt.timestamp() / 86400 + 2440587.5


def sun_ecliptic(jd):
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)
    r = 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2 * g)
    return lam % 360, r


def moon_ecliptic(jd):
    T = (jd - 2451545.0) / 36525
    L = 218.316 + 481267.881 * T
    M = math.radians(134.963 + 477198.867 * T)
    F = math.radians(93.272 + 483202.018 * T)
    D = math.radians(297.850 + 445267.115 * T)
    lam = L + 6.289 * math.sin(M) + 1.274 * math.sin(2 * D - M) + 0.658 * math.sin(2 * D)
    return lam % 360, 5.128 * math.sin(F)


def ecl_to_eq(lam, beta, jd):
    eps = math.radians(23.439 - 0.0000004 * (jd - 2451545.0))
    l, b = math.radians(lam), math.radians(beta)
    ra = math.atan2(math.sin(l) * math.cos(eps) - math.tan(b) * math.sin(eps), math.cos(l))
    dec = math.asin(math.sin(b) * math.cos(eps) + math.cos(b) * math.sin(eps) * math.sin(l))
    return ra, dec


def alt_az(ra, dec, jd, lat, lon):
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360
    ha = math.radians((gmst + lon) % 360) - ra
    p = math.radians(lat)
    alt = math.asin(math.sin(p) * math.sin(dec) + math.cos(p) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(p) - math.sin(p) * math.cos(ha))
    return math.degrees(alt), math.degrees(az) % 360


def mix(a, b, f):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(pa, pb))


# ---------- the nine screensaver scenes ----------

def opt_voyager(s, t):
    v = s["voyager"]
    at = datetime.fromisoformat(v["at"])
    rnd = random.Random(1977)
    stars, star_css = starfield(rnd, [(90, 0.55, 0.55, 520), (28, 0.8, 0.75, 300), (7, 1.1, 0.9, 170)])
    defs = (
        '<linearGradient id="beam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#e7c597" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#e7c597" stop-opacity=".11"/><stop offset="1" stop-color="#e7c597" stop-opacity="0"/></linearGradient>'
    )
    beams = "".join(f'<polygon class="bm{i}" points="{x0 - 30},0 {x0 - 30 + bw},0 {x0 + 30 + bw},{H} {x0 + 30},{H}" fill="url(#beam)"/>'
                    for i, (x0, bw) in enumerate([(128, 40), (166, 24), (214, 54)]))
    css = star_css + "@keyframes breathe{0%,100%{opacity:1}50%{opacity:.45}}"
    css += "".join(f".bm{i}{{animation:breathe {d}s ease-in-out {o}s infinite}}" for i, (d, o) in enumerate([(13, 0), (17, -5), (11, -8)]))
    css += "@keyframes halo{0%,100%{opacity:.12}50%{opacity:.35}}.halo{animation:halo 6s ease-in-out infinite}"
    dot = '<circle class="halo" cx="206" cy="116" r="5" fill="#a9c8ff"/><circle cx="206" cy="116" r="1.5" fill="#bcd4ff"/>'
    odefs, odo, ocss, end = odometer("vk", 330, 112, v["km"], v["km_s"], 11, 40, "#e9edf5")
    secs = round(v["light_s"])
    lt = f"light from it takes {secs // 3600} h {secs % 3600 // 60} m {secs % 60} s to reach us"
    if at < LIGHT_DAY_AT:
        days = (LIGHT_DAY_AT - at).total_seconds() / 86400
        left = f"in {round(days)} days" if days >= 2 else f"in {round(days * 24)} hours"
        event = f"one light-day from Earth on {stamp(LIGHT_DAY_AT.isoformat(), '%d %b %Y, %H:%M')} · {left}"
    else:
        event = "more than one light-day from Earth since 19 Nov 2026"
    body = (
        screen()
        + f'<g clip-path="url(#scr)">{stars}{beams}{dot}</g>'
        + text(330, 52, "VOYAGER 1 · DISTANCE FROM EARTH", 10.5, "#8a93a6", ls="1.6")
        + text(856, 52, f"JPL HORIZONS · {stamp(v['at'])}", 10, "#4f5769", anchor="end", ls="1")
        + odo + text(end + 10, 112, "km", 16, "#8a93a6")
        + text(330, 146, lt, 12, "#b5bdcf")
        + text(330, 168, event, 12, "#e7c597")
    )
    return svg("Voyager 1 distance from Earth, ticking live", body, css + ocss, fonts("mono", "light"), defs + odefs)


def opt_seismo(s, t):
    q = s["quakes"]
    at = datetime.fromisoformat(q["at"]).timestamp()
    events = [e for e in q["events"] if at - 86400 <= e["t"] <= at]
    rnd = random.Random(2026)
    pen, period, base = 690, 120, 112
    trace = [rnd.gauss(0, 0.55) for _ in range(W)]
    for e in events:
        x0 = int((e["t"] - (at - 86400)) / 86400 * W)
        amp = min(78, 5 * 10 ** (0.4 * (e["mag"] - 2.5)))
        length = int(10 + 7 * e["mag"])
        for j in range(length):
            env = 0.3 if j < length * 0.22 else math.exp(-3.2 * (j - length * 0.22) / length)
            trace[(x0 + j) % W] += amp * env * (1 if j % 2 else -1) * rnd.uniform(0.55, 1)
    pts = " ".join(f"{x},{num(base - y)}" for x, y in enumerate(trace))
    hours = "".join(f'<line x1="{num(i * W / 24)}" y1="34" x2="{num(i * W / 24)}" y2="178"/>' for i in range(24))
    labels = "".join(text((e["t"] - (at - 86400)) / 86400 * W + 6, 46, f"M{e['mag']}", 9.5, t["muted"])
                     for e in sorted(events, key=lambda e: -e["mag"])[:3] if e["mag"] >= 4.5)
    paper = (f'<g stroke="{t["faint"]}" stroke-width=".6" opacity=".7">{hours}</g>{labels}'
             f'<polyline points="{pts}" fill="none" stroke="{t["ink"]}" stroke-width="1.1" stroke-linejoin="round"/>')
    content = f'<g class="paper"><g>{paper}</g><g transform="translate({W} 0)">{paper}</g></g>'
    css = f"@keyframes paper{{from{{transform:translateX({pen - W}px)}}to{{transform:translateX({pen - 2 * W}px)}}}}.paper{{animation:paper {period}s linear infinite}}"
    defs = (
        '<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".12" stop-color="#fff"/><stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<mask id="rec" maskUnits="userSpaceOnUse" x="20" y="0" width="{pen - 20}" height="{H}"><rect x="20" y="0" width="{pen - 20}" height="{H}" fill="url(#fade)"/></mask>'
    )
    ys = ";".join(num(base - trace[int(i * W / 440) % W]) for i in range(441))
    pen_dot = (f'<line x1="{pen}" y1="30" x2="{pen}" y2="180" stroke="{t["faint"]}" stroke-width=".8"/>'
               f'<circle cx="{pen}" cy="{base}" r="3" fill="{t["red"]}"><animate attributeName="cy" dur="{period}s" repeatCount="indefinite" values="{ys}"/></circle>')
    grid = "".join(f'<line x1="20" y1="{base + d}" x2="{pen}" y2="{base + d}"/>' for d in (-60, -30, 30, 60))
    big = max(events, key=lambda e: e["mag"]) if events else None
    place = re.sub(r"^.*? of ", "", big["place"]) if big else ""
    place = place if len(place) <= 22 else place[:21] + "…"
    side = 716
    body = (
        f'<g stroke="{t["faint"]}" stroke-width=".6" opacity=".55">{grid}</g>'
        + f'<g mask="url(#rec)">{content}</g>{pen_dot}'
        + text(20, 22, "SEISMOGRAPH · EARTH, LAST 24 HOURS", 10, t["muted"], ls="1.4")
        + text(side, 92, str(len(events)), 40, t["ink"], fam=LIGHT)
        + text(side, 112, "earthquakes, M2.5+", 11, t["muted"])
        + (text(side, 146, f"largest M{big['mag']}", 11, t["ink"]) + text(side, 162, place, 11, t["muted"]) if big else "")
        + text(side, 186, f"USGS · {stamp(q['at'])}", 9.5, t["dim"], ls=".6")
    )
    return svg("Every M2.5+ earthquake on Earth in the last 24 hours, as a seismograph", body, css, fonts("mono", "light"), defs)


OVAL = [66.5, 64.5, 62.4, 60.4, 58.3, 56.3, 54.2, 52.2, 50.1, 48.1]
KP_WORD = ["quiet", "quiet", "unsettled", "unsettled", "active", "G1 storm", "G2 storm", "G3 storm", "G4 storm", "G5 storm"]


def opt_aurora(s, t):
    kp = min(9.0, max(0.0, s["kp"]["kp"]))
    rnd = random.Random(42)
    stars, css = starfield(rnd, [(80, 0.55, 0.6, 900), (18, 0.85, 0.8, 600)])
    height = 52 + 12 * kp
    red = max(0.0, min(0.75, (kp - 3) / 6))
    glow = 0.5 + 0.05 * kp
    defs = (
        f'<linearGradient id="cur" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c2559b" stop-opacity="{num(red, 2)}"/>'
        f'<stop offset=".5" stop-color="#4fe0a0" stop-opacity="{num(glow * 0.45, 2)}"/><stop offset=".9" stop-color="#8affc8" stop-opacity="{num(glow, 2)}"/>'
        '<stop offset="1" stop-color="#b4ffe0" stop-opacity="0"/></linearGradient>'
        '<filter id="ab" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="3.5"/></filter>'
    )
    rays = "".join(f'<rect x="{num(x)}" y="0" width="{num(rnd.uniform(1, 5))}" height="{H}" fill="#fff" opacity="{num(rnd.uniform(0.15, 0.6), 2)}"/>'
                   for x in [rnd.uniform(-60, W + 60) for _ in range(150)])
    defs += (f'<mask id="ray" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#fff" opacity=".5"/>'
             f'<g>{rays}<animateTransform attributeName="transform" type="translate" values="0 0;-40 0;0 0" dur="47s" repeatCount="indefinite"/></g></mask>')
    curtains = []
    for c in range(2 + min(3, int(kp // 2))):
        shapes = []
        phase = [rnd.uniform(0, 6.3) for _ in range(4)]
        base = 128 - c * 9 + rnd.uniform(-6, 6)
        for k in range(4):
            pk = [p + k * 1.7 for p in phase]
            low = [(x, base + 16 * math.sin(x / 140 + pk[0]) + 7 * math.sin(x / 53 + pk[1])) for x in range(-40, W + 81, 40)]
            hi = [(x, y - height * (0.65 + 0.35 * math.sin(x / 90 + pk[2])) - 6 * math.sin(x / 31 + pk[3])) for x, y in reversed(low)]
            shapes.append("M" + " L".join(f"{x},{num(y)}" for x, y in low + hi) + "Z")
        curtains.append(f'<path d="{shapes[0]}" fill="url(#cur)" opacity="{num(0.55 + 0.15 * (c == 0), 2)}">'
                        f'<animate attributeName="d" dur="{rnd.uniform(22, 36):.1f}s" repeatCount="indefinite" values="{";".join(shapes + shapes[:1])}" '
                        f'calcMode="spline" keySplines="{";".join([".45 0 .55 1"] * 4)}"/></path>')
    trees, x = [], -4.0
    while x < W:
        th = rnd.uniform(8, 20)
        trees.append(f"M{num(x)},{H} L{num(x + th * 0.32)},{num(H - 12 - th)} L{num(x + th * 0.64)},{H}Z")
        x += rnd.uniform(4, 11)
    ground = f'<path d="M0,{H} L0,188 Q220,181 440,186 T{W},184 L{W},{H}Z" fill="#06090d"/><path d="{" ".join(trees)}" fill="#030507"/>'
    oval = OVAL[int(kp)] + (OVAL[min(9, int(kp) + 1)] - OVAL[int(kp)]) * (kp - int(kp))
    body = (
        screen()
        + f'<g clip-path="url(#scr)">{stars}<g filter="url(#ab)" mask="url(#ray)">{"".join(curtains)}</g>{ground}</g>'
        + text(22, 30, "AURORA METER", 10, "#8fb5aa", ls="1.6")
        + text(22, 60, f"Kp {kp:.1f} · {KP_WORD[int(round(kp))]}", 22, "#dff7ee", fam=LIGHT)
        + text(22, 80, f"the auroral oval reaches {oval:.1f}° geomagnetic latitude", 10.5, "#90a7a2")
        + text(858, 30, f"NOAA SWPC · {stamp(s['kp']['at'])}", 9.5, "#56706b", anchor="end", ls=".6")
    )
    return svg(f"Aurora meter, planetary Kp {kp:.1f}", body, css, fonts("mono", "light"), defs)


def opt_pulsar(s, t):
    rnd = random.Random(329)
    stars, css = starfield(rnd, [(70, 0.5, 0.5, 1400)], twinkle=0.1)
    cx, cy = 138, 92
    p = f"{PULSAR_P:.9f}"
    css += (f"@keyframes spin{{to{{transform:rotate(360deg)}}}}.beam{{transform-box:view-box;transform-origin:{cx}px {cy}px;animation:spin {p}s linear infinite}}"
            f"@keyframes ring{{from{{transform:scale(.03);opacity:.55}}to{{transform:scale(1);opacity:0}}}}.ring{{transform-box:fill-box;transform-origin:center;animation:ring {PULSAR_P * 3:.9f}s linear infinite}}"
            f"@keyframes core{{0%,100%{{opacity:.55}}6%{{opacity:1}}20%{{opacity:.55}}}}.core{{animation:core {p}s linear infinite}}")
    defs = ('<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#bfe3ff" stop-opacity=".55"/>'
            '<stop offset="1" stop-color="#bfe3ff" stop-opacity="0"/></linearGradient>'
            '<filter id="gl" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3"/></filter>')
    rings = "".join(f'<circle class="ring" cx="{cx}" cy="{cy}" r="150" fill="none" stroke="#9fd2ff" stroke-width=".8" vector-effect="non-scaling-stroke" style="animation-delay:{-i * PULSAR_P:.9f}s"/>' for i in range(3))
    beam = (f'<g class="beam"><polygon points="{cx},{cy} {cx + 130},{cy - 7} {cx + 130},{cy + 7}" fill="url(#bg)"/>'
            f'<polygon points="{cx},{cy} {cx - 130},{cy - 7} {cx - 130},{cy + 7}" fill="url(#bg)"/></g>')
    star = f'<circle class="core" cx="{cx}" cy="{cy}" r="7" fill="#cfeaff" filter="url(#gl)"/><circle cx="{cx}" cy="{cy}" r="2" fill="#f2f9ff"/>'
    x0, x1, y_base = 300, 856, 112
    prof = []
    for i in range(x1 - x0 + 1):
        ph = i / (x1 - x0)
        y = rnd.gauss(0, 0.9) + sum(a * math.exp(-((ph - mu) ** 2) / (2 * sig * sig)) for mu, sig, a in [(0.47, 0.006, 18), (0.5, 0.0045, 70), (0.528, 0.007, 26)])
        prof.append((x0 + i, y_base - y))
    d = "M" + " L".join(f"{x},{num(y)}" for x, y in prof)
    css += "@keyframes sweep{from{stroke-dashoffset:70}to{stroke-dashoffset:-1000}}.sweep{animation:sweep " + p + "s linear infinite}"
    grat = "".join(f'<line x1="{x}" y1="26" x2="{x}" y2="124"/>' for x in range(x0, x1 + 1, 69)) + "".join(
        f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}"/>' for y in (26, 59, 92, 124))
    scope = (f'<g stroke="#1d2a33" stroke-width=".6">{grat}</g><path d="{d}" fill="none" stroke="#3f8f7a" stroke-width="1" opacity=".55"/>'
             f'<path class="sweep" d="{d}" pathLength="1000" fill="none" stroke="#a8ffd8" stroke-width="1.4" stroke-dasharray="70 1000"/>')
    odefs, odo, ocss, end = odometer("pz", 300, 178, 0, 1 / PULSAR_P, 6, 20, "#cfe6f5")
    body = (
        screen() + f'<g clip-path="url(#scr)">{stars}{rings}{beam}{star}{scope}</g>'
        + text(22, 150, "PSR B0329+54", 13, "#d8ecff", ls=".6")
        + text(22, 167, "a neutron star in Camelopardalis,", 10, "#7f93a6")
        + text(22, 181, "about 3,500 light-years away", 10, "#7f93a6")
        + text(300, 146, "PULSE PROFILE, ONE SWEEP PER TURN · 0.7145 S", 9.5, "#5f8a7e", ls="1.2")
        + odo + text(end + 10, 178, "pulses since you opened this page", 10.5, "#7f93a6")
    )
    return svg("Pulsar PSR B0329+54 beating at its real period", body, css + ocss, fonts("mono", "light"), defs + odefs)


def opt_orbit(s, t):
    lam, r = sun_ecliptic(julian(datetime.fromisoformat(s["at"])))
    speed = 29.7847 * math.sqrt(2 / r - 1)
    odefs, odo, ocss, end = odometer("ok", 40, 124, 0, speed, 9, 56, t["ink"])
    ocx, ocy, orr = 742, 100, 64
    theta = math.radians((lam + 180) % 360)
    ex, ey = ocx + orr * math.cos(theta), ocy - orr * math.sin(theta)
    tx, ty = ocx + orr * math.cos(theta - math.radians(28)), ocy - orr * math.sin(theta - math.radians(28))
    css = "@keyframes flow{to{stroke-dashoffset:-60}}.orb{animation:flow 9s linear infinite}"
    orbit = (f'<circle class="orb" cx="{ocx}" cy="{ocy}" r="{orr}" fill="none" stroke="{t["faint"]}" stroke-width="1" stroke-dasharray="2 4"/>'
             f'<path d="M{num(tx)},{num(ty)} A{orr},{orr} 0 0 0 {num(ex)},{num(ey)}" fill="none" stroke="{t["muted"]}" stroke-width="1.2" stroke-linecap="round"/>'
             f'<circle cx="{ocx}" cy="{ocy}" r="9" fill="{t["warm"]}" opacity=".18"/><circle cx="{ocx}" cy="{ocy}" r="4.5" fill="{t["warm"]}"/>'
             f'<circle cx="{num(ex)}" cy="{num(ey)}" r="3.6" fill="{t["ink"]}"/>' + text(ex + 8, ey + 4, "you", 10, t["muted"]))
    body = (
        text(40, 50, "SINCE YOU OPENED THIS PAGE, YOU HAVE TRAVELLED", 10.5, t["muted"], ls="1.6")
        + odo + text(end + 12, 124, "km", 18, t["muted"])
        + text(40, 162, f"around the Sun. Earth is doing {speed:.2f} km/s today.", 12, t["muted"])
        + orbit
    )
    return svg("Kilometres travelled around the Sun since this page opened", body, css + ocss, fonts("mono", "light"), odefs)


WPP_2024, WPP_2026 = 8_161_972_572, 8_300_678_395
WPP_MID_2024 = datetime(2024, 7, 1, tzinfo=timezone.utc)
BIRTHS_S, DEATHS_S = 132e6 / 31_557_600, 63e6 / 31_557_600


def opt_people(s, t):
    rate = (WPP_2026 - WPP_2024) / (2 * 31_557_600)
    pop = WPP_2024 + rate * (datetime.fromisoformat(s["at"]) - WPP_MID_2024).total_seconds()
    rnd = random.Random(8)
    cols, rows, gx, gy, x0, y0 = 105, 9, 8, 8, 24, 22
    defs = (f'<pattern id="dots" x="{x0 - 4}" y="{y0 - 4}" width="{gx}" height="{gy}" patternUnits="userSpaceOnUse">'
            f'<circle cx="4" cy="4" r=".9" fill="{t["faint"]}"/></pattern>')
    loop = 60
    css = ("@keyframes birth{0%{opacity:0}.5%{opacity:1}7%{opacity:0}100%{opacity:0}}.b{opacity:0;animation:birth 60s linear infinite}"
           "@keyframes death{0%{opacity:0}.4%{opacity:.9}2.5%{opacity:0}100%{opacity:0}}.d{opacity:0;animation:death 60s linear infinite}")
    sparks = []
    for cls, n, col, rr in (("b", round(BIRTHS_S * loop), t["warm"], 1.9), ("d", round(DEATHS_S * loop), t["dim"], 1.5)):
        for _ in range(n):
            cx, cy = x0 + gx * rnd.randrange(cols), y0 + gy * rnd.randrange(rows)
            halo = f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="{col}" opacity=".25"/>' if cls == "b" else ""
            sparks.append(f'<g class="{cls}" style="animation-delay:{-rnd.uniform(0, loop):.2f}s">{halo}<circle cx="{cx}" cy="{cy}" r="{rr}" fill="{col}"/></g>')
    odefs, odo, ocss, end = odometer("pp", 24, 160, pop, rate, 10, 38, t["ink"])
    body = (
        f'<rect x="{x0 - 4}" y="{y0 - 4}" width="{cols * gx}" height="{rows * gy}" fill="url(#dots)"/>{"".join(sparks)}' + odo
        + text(end + 18, 140, "people alive right now (estimate)", 11, t["ink"])
        + text(end + 18, 157, f"amber: a birth, about {BIRTHS_S:.1f} a second", 10.5, t["muted"])
        + text(end + 18, 172, f"grey: a death, about {DEATHS_S:.1f} a second", 10.5, t["muted"])
        + text(end + 18, 190, "UN World Population Prospects 2024", 9.5, t["dim"], ls=".4")
    )
    return svg("World population, ticking at the UN estimated rate", body, css + ocss, fonts("mono", "light"), defs + odefs)


def opt_arxiv(s, t):
    papers = s["arxiv"]["papers"][:12]
    pitch, size, maxw = 30, 17, 690
    rows = []
    for i, p in enumerate(papers):
        title = p["title"]
        if serif_width(title, size) > maxw:
            while serif_width(title + "…", size) > maxw:
                title = title[:-1]
            title = title.rstrip(" ,:;-") + "…"
        y = 62 + i * pitch
        rows.append(text(40, y, title, size, t["ink"], fam=SERIF) + text(842, y, p["id"].split("v")[0], 10, t["dim"], anchor="end", ls=".4"))
    block = "".join(rows)
    span = len(papers) * pitch
    css = f"@keyframes credits{{to{{transform:translateY(-{span}px)}}}}.cr{{animation:credits {len(papers) * 5.5}s linear infinite}}"
    defs = ('<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            '<stop offset=".22" stop-color="#fff"/><stop offset=".78" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<mask id="win" maskUnits="userSpaceOnUse" x="0" y="34" width="{W}" height="160"><rect x="0" y="34" width="{W}" height="160" fill="url(#fade)"/></mask>')
    body = (
        text(40, 24, "NEW ON ARXIV · MACHINE LEARNING (cs.LG)", 10, t["muted"], ls="1.4")
        + text(842, 24, stamp(s["arxiv"]["at"], "%d %b %H:%M"), 9.5, t["dim"], anchor="end", ls=".6")
        + f'<g mask="url(#win)"><g class="cr">{block}<g transform="translate(0 {span})">{block}</g></g></g>'
    )
    return svg("Newest machine-learning papers on arXiv, drifting past", body, css, fonts("mono", "serif"), defs)


def opt_pendulum(s, t):
    n, amp, cy = 24, 56, 96
    xs = [70 + i * (740 / (n - 1)) for i in range(n)]
    css = (f"@keyframes sw{{from{{transform:translateY(-{amp}px)}}to{{transform:translateY({amp}px)}}}}"
           ".p{animation-name:sw;animation-timing-function:cubic-bezier(.37,0,.63,1);animation-iteration-count:infinite;animation-direction:alternate}")
    guides, bobs = [], []
    for i, x in enumerate(xs):
        period = 60 / (30 + i)
        guides.append(f'<line x1="{num(x)}" y1="{cy - amp - 8}" x2="{num(x)}" y2="{cy + amp + 8}"/>')
        for g, (lag, op, r) in enumerate([(0.18, 0.12, 4.2), (0.12, 0.22, 4.5), (0.06, 0.38, 4.8), (0, 1, 5)]):
            delay = -(period - lag) if lag else 0
            bobs.append(f'<circle class="p" cx="{num(x)}" cy="{cy}" r="{r}" fill="{t["ink"] if g == 3 else t["muted"]}" opacity="{op}" '
                        f'style="animation-duration:{period / 2:.6f}s;animation-delay:{delay:.6f}s"/>')
    body = (f'<g stroke="{t["faint"]}" stroke-width=".8">{"".join(guides)}</g>{"".join(bobs)}'
            + text(70, 188, "24 pendulums, 30 to 53 swings a minute. They line up again every 60 seconds.", 10.5, t["muted"]))
    return svg("A pendulum wave that realigns every minute", body, css, fonts("mono"))


def bounce_track(rnd, lo, hi, loop, kmin, kmax):
    rng = hi - lo
    v = 2 * rng * rnd.randint(kmin, kmax) / loop
    u0 = rnd.uniform(0, 2)

    def at(tm):
        u = (u0 + v * tm / rng) % 2
        return lo + rng * (u if u <= 1 else 2 - u)

    events = [(n - u0) * rng / v for n in range(math.ceil(u0), math.floor(u0 + v * loop / rng) + 1)]
    return at, [e for e in events if 0 < e < loop]


def opt_mystify(s, t):
    rnd = random.Random(1995)
    loop = 36.0
    palettes = [["#5ec8ff", "#8a7dff", "#ff6fb5", "#ffb35e", "#7dffb0", "#5ec8ff"],
                ["#ff6f7d", "#ffd36f", "#6fffd0", "#6fa8ff", "#d36fff", "#ff6f7d"]]
    polys = []
    for pi in range(2):
        tracks = [bounce_track(rnd, 10, W - 10, loop, 1, 3) if c % 2 == 0 else bounce_track(rnd, 10, H - 10, loop, 4, 8) for c in range(8)]
        times = sorted({0.0, loop, *[e for _, ev in tracks for e in ev]})
        values = ";".join(" ".join(f"{num(tracks[2 * j][0](tm))},{num(tracks[2 * j + 1][0](tm))}" for j in range(4)) for tm in times)
        key_times = ";".join(f"{tm / loop:.5f}" for tm in times)
        for j, op in enumerate([1, 0.6, 0.38, 0.22, 0.12]):
            begin = f"-{loop - j * 0.11:.2f}s" if j else "0s"
            polys.append(
                f'<polygon fill="none" stroke-width="1.2" stroke-linejoin="round" opacity="{op}" points="{values.split(";")[0]}">'
                f'<animate attributeName="points" dur="{loop}s" begin="{begin}" repeatCount="indefinite" keyTimes="{key_times}" values="{values}"/>'
                f'<animate attributeName="stroke" dur="30s" begin="{begin}" repeatCount="indefinite" values="{";".join(palettes[pi])}"/></polygon>')
    body = (screen() + f'<g clip-path="url(#scr)">{"".join(polys)}</g>'
            + text(22, 190, "mystify, after the Windows 95 screensaver", 9, "#3b4352", ls=".4"))
    return svg("Mystify, two bouncing polygons with trails", body, "", fonts("mono"))


SCENES = {
    "voyager": ("Voyager 1", opt_voyager), "seismo": ("Seismograph", opt_seismo), "aurora": ("Aurora meter", opt_aurora),
    "pulsar": ("Pulsar", opt_pulsar), "orbit": ("Since you opened this page", opt_orbit), "people": ("People alive", opt_people),
    "arxiv": ("New on arXiv", opt_arxiv), "pendulum": ("Pendulum wave", opt_pendulum), "mystify": ("Mystify", opt_mystify),
}

# ---------- weather words shared with hero.py ----------

WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog", 51: "light drizzle",
       53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
       77: "snow grains", 80: "showers", 81: "showers", 82: "violent showers", 85: "snow showers", 86: "snow showers",
       95: "thunderstorm", 96: "thunderstorm, hail", 99: "thunderstorm, hail"}
RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
SNOW = {71, 73, 75, 77, 85, 86}
AQI = [(50, "good", "#7bd88f", "#9fb4c8"), (100, "moderate", "#e9cf63", "#c9bfa0"), (150, "unhealthy for some", "#f2a35e", "#c9a882"),
       (200, "unhealthy", "#ef6b5e", "#b98f78"), (300, "very unhealthy", "#b97ad8", "#a08a8f"), (10**9, "hazardous", "#b0485f", "#8f7468")]


def moon_path(cx, cy, r, k, waxing):
    rx = num(r * abs(1 - 2 * k), 2)
    if waxing:
        return f"M{cx},{cy - r} A{r},{r} 0 0 1 {cx},{cy + r} A{rx},{r} 0 0 {1 if k > 0.5 else 0} {cx},{cy - r}Z"
    return f"M{cx},{cy - r} A{r},{r} 0 0 0 {cx},{cy + r} A{rx},{r} 0 0 {0 if k > 0.5 else 1} {cx},{cy - r}Z"


FACES_DIE = [[4], [0, 8], [0, 4, 8], [0, 2, 6, 8], [0, 2, 4, 6, 8], [0, 2, 3, 5, 6, 8]]


def die(rnd, cx, cy, gap=5.0, r=1.25, on="#9aa4b0", off="#2a313b", hold=1.8, fade=0.35):
    """A 3x3 dot die that slowly rolls through its faces in a shuffled order."""
    order = FACES_DIE[:]
    rnd.shuffle(order)
    cycle = hold * len(order)
    css, dots = [], []
    for i in range(9):
        vals = [1 if i in face else 0 for face in order]
        stops = []
        for j, v in enumerate(vals):
            stops.append(f"{j * hold / cycle * 100:.3f}%{{opacity:{v}}}{((j + 1) * hold - fade) / cycle * 100:.3f}%{{opacity:{v}}}")
        stops.append(f"100%{{opacity:{vals[0]}}}")
        css.append(f"@keyframes die{i}{{{''.join(stops)}}}.die{i}{{animation:die{i} {cycle}s ease-in-out infinite}}")
        x, y = cx + (i % 3 - 1) * gap, cy + (i // 3 - 1) * gap
        dots.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}" fill="{off}"/><circle class="die{i}" cx="{num(x)}" cy="{num(y)}" r="{r}" fill="{on}"/>')
    return "".join(dots), "".join(css)


def set_zone(snap):
    """Local time for every caption, from the location's IANA zone; Open-Meteo's offset if the zone is unknown."""
    w = snap.get("weather") or {}
    try:
        local = datetime.fromisoformat(snap["at"]).astimezone(ZoneInfo(snap["location"]["tz"]))
        abbr = local.tzname()
        ZONE.update(offset=local.utcoffset().total_seconds(), abbr=("UTC" + abbr) if abbr[0] in "+-" else abbr)
    except Exception:
        ZONE.update(offset=w.get("utc_offset_seconds", 0), abbr=w.get("tz_abbr") or "UTC")


def die_svg(rnd, on, off):
    dots, css = die(rnd, 10, 10, gap=5, r=1.35, on=on, off=off)
    dots = dots.replace(f'fill="{off}"/><circle class', f'fill="{off}" opacity=".25"/><circle class', 9)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20" role="img" aria-label="another one">'
            f"<title>another one</title><style>{css}@media (prefers-reduced-motion:reduce){{*{{animation-play-state:paused!important}}}}</style>{dots}</svg>")


def main():
    import campus_painted

    state, out = Path(sys.argv[1]), Path(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
    snap = json.loads((state / "snapshot.json").read_text(encoding="utf-8"))
    set_zone(snap)
    (out / "readme").mkdir(parents=True, exist_ok=True)
    built = {}
    for slug, (name, fn) in SCENES.items():
        try:
            built[slug] = fn(snap, PAL)
        except Exception as e:
            print(f"skip {slug}: {e!r}")
    for slug, sc in built.items():
        for theme in ("light", "dark"):
            (out / "readme" / f"{slug}-{theme}.svg").write_text(render(sc, edge=theme == "dark", base=True), encoding="utf-8")
    for theme in ("light", "dark"):
        (out / f"hero-{theme}.svg").write_text(render(campus_painted.campus_hero(snap, theme)), encoding="utf-8")
    for theme, colour in (("light", "#59636e"), ("dark", "#9198a1")):
        (out / f"die-{theme}.svg").write_text(die_svg(random.Random(seed), colour, colour), encoding="utf-8")
    names = {slug: name for slug, (name, _) in SCENES.items()}
    (out / "manifest.json").write_text(json.dumps({"built": snap["at"], "hero": "campus", "scenes": sorted(built), "names": names,
                                                   "location": snap["location"]}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("home: campus | scenes:", " ".join(sorted(built)))


if __name__ == "__main__":
    main()
