"""The home view: a painting of DGIST that follows the campus's season, light and weather, with live motion on top.

The paintings in paintings/ are made offline (sim/render_variants.py renders the 3D campus for each season and light,
sim/codex_paint.py paints it in the chosen film-background style, sim/build_paintings.py encodes them). Each is
<season>-<light>.avif at 1320x742, where light is day, golden, dusk, night or overcast, plus winter-snow.
paintings/geometry.json holds the roads, paths and building anchors projected into the same 16:9 frame, so the shuttle,
walkers and pin land on the painted campus.
"""
import base64
import json
import math
import random
from pathlib import Path

import campus
import hero
from gen import escape, num, svg

HERE = Path(__file__).parent / "paintings"
GEOMETRY = json.loads((HERE / "geometry.json").read_text(encoding="utf-8"))
W, H = 880, 495
FOG = {45, 48}


def season(local):
    d = local.month * 100 + local.day
    if 1012 <= d <= 1128:
        return "autumn"
    if d >= 1129 or d <= 310:
        return "winter"
    return "spring" if d <= 510 else "summer"


def painting(sky):
    """Pick the painting for DGIST's sky right now."""
    when = season(sky.local)
    light = "night" if sky.salt < -6 else "dusk" if sky.salt < 2 else "golden" if sky.salt < 12 else "day"
    if light in ("day", "golden"):
        if sky.code in hero.SNOW and when == "winter":
            light = "snow"
        elif sky.cloud >= 0.8 or sky.code in hero.RAIN or sky.code in hero.SNOW or sky.code in FOG:
            light = "overcast"
    name = f"{when}-{light}"
    if not (HERE / f"{name}.avif").exists():
        name = f"{when}-day"
    return name


def path_d(points):
    return "M" + " L".join(f"{num(x)},{num(y)}" for x, y in points)


def length(line):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:]))


def campus_hero(s, theme):
    loc = s["location"]
    spot = loc.get("campus") or {}
    pin = spot.get("code") or ("dorms" if spot.get("zone") == "dorms" else None)
    if loc.get("dgist") or spot:
        label, snap = "DGIST" + (f" · {'DORMS' if pin == 'dorms' else pin}" if pin else ""), s
    else:
        w = s.get("weather") or {}
        label = f"Away · {loc['city']}" + (f" {round(w['temperature_2m'])}°C" if w.get("temperature_2m") is not None else "")
        snap = dict(s, location=campus.DGIST_LOC, weather=s.get("weather_dgist") or w, air=s.get("air_dgist") or s.get("air"))
    sky = hero.sky_state(snap)
    name = painting(sky)
    image = base64.b64encode((HERE / f"{name}.avif").read_bytes()).decode()
    rnd = random.Random(sky.seed ^ int(sky.local.timestamp()) // 1800)
    night = name.endswith(("night", "dusk"))
    defs, css = [], []
    body = [f'<image width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice" href="data:image/avif;base64,{image}"/>']

    if not night and sky.cloud > 0.25 and not name.endswith(("overcast", "snow")):
        defs.append('<radialGradient id="cs"><stop offset="0" stop-color="#0d1a12" stop-opacity=".22"/><stop offset="1" stop-color="#0d1a12" stop-opacity="0"/></radialGradient>')
        period = max(90, 600 - sky.wind * 15)
        for _ in range(2 + round(sky.cloud * 2)):
            cy, rx = rnd.uniform(60, H - 70), rnd.uniform(130, 220)
            body.append(f'<g class="drift" style="--a:{num(W + rx)}px;--b:{num(-rx)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                        f'<ellipse cy="{num(cy)}" rx="{num(rx)}" ry="{num(rx * 0.32)}" fill="url(#cs)"/></g>')
        css.append("@keyframes drift{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}.drift{animation:drift linear infinite}")

    roads = sorted(GEOMETRY["roads"], key=length, reverse=True)
    if roads:
        bus = ('<rect x="-3.6" y="-3.8" width="7.2" height="3" rx="1" fill="#f6f4ee"/><rect x="-3" y="-3.3" width="6" height="1" fill="#3f78ad"/>' if not night
               else '<rect x="-3.6" y="-3.8" width="7.2" height="3" rx="1" fill="#2a313c"/><rect x="-3" y="-3.3" width="6" height="1" fill="#ffe0a0"/><circle cx="3.8" cy="-1.6" r="2.2" fill="#fff2c8" opacity=".5"/>')
        body.append(f'<g>{bus}<animateMotion dur="150s" repeatCount="indefinite" keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(roads[0])}"/></g>')
        if night:
            for i, line in enumerate(roads[1:4]):
                body.append(f'<g><circle r="1" fill="#fff4d0"/><circle cx="1.8" r="1" fill="#fff4d0"/><animateMotion dur="{60 + 20 * i}s" begin="-{i * 9}s" repeatCount="indefinite" path="{path_d(line)}"/></g>')
    if 7 <= sky.local.hour < 23 and not name.endswith("snow"):
        for i, line in enumerate(sorted(GEOMETRY["paths"], key=length, reverse=True)[:8]):
            if len(line) < 2:
                continue
            colour = ["#f0b37a", "#8fb3e8", "#f6f2ea", "#e07a6e"][i % 4] if not night else "#d5dce6"
            body.append(f'<circle r="1" fill="{colour}"><animateMotion dur="{80 + 25 * i}s" begin="-{rnd.uniform(0, 60):.0f}s" repeatCount="indefinite" keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(line)}"/></circle>')

    if sky.code in hero.RAIN or sky.code in hero.SNOW:
        rain = sky.code in hero.RAIN
        for layer, (n, op, size, dur) in enumerate([(90, 0.22, 0.55, 0.8), (50, 0.38, 0.85, 0.55)] if rain else [(70, 0.55, 1.0, 11), (35, 0.85, 1.6, 7)]):
            drops = "".join(f'<line x1="{num(x)}" y1="{num(y)}" x2="{num(x - 3)}" y2="{num(y + 10)}"/>' if rain else f'<circle cx="{num(x)}" cy="{num(y)}" r="{size}"/>'
                            for x, y in ((rnd.uniform(0, W + 40), rnd.uniform(0, H)) for _ in range(n)))
            paint = f'stroke="#dfe7f1" stroke-width="{size}" opacity="{op}"' if rain else f'fill="#f5f8fb" opacity="{op}"'
            css.append(f"@keyframes f{layer}{{from{{transform:translate(0,-{H}px)}}to{{transform:translate(-{60 if rain else 26}px,0)}}}}.f{layer}{{animation:f{layer} {dur}s linear infinite}}")
            body.append(f'<g class="f{layer}" {paint}>{drops}<g transform="translate(0 {H})">{drops}</g></g>')

    if pin and pin in GEOMETRY["anchors"]:
        px, py = GEOMETRY["anchors"][pin]
        tag = "Dorms" if pin == "dorms" else pin
        body.append(
            f'<g transform="translate({num(px)} {num(py)})">'
            f'<ellipse class="ring" rx="11" ry="4" fill="none" stroke="{campus.PIN}" stroke-width="1.2"/><ellipse rx="3" ry="1.2" fill="#000" opacity=".35"/>'
            f'<g class="bob"><path d="M0,-1C-2.2,-5.9 -6.1,-8.7 -6.1,-12.6A6.1,6.1 0 1 1 6.1,-12.6C6.1,-8.7 2.2,-5.9 0,-1Z" fill="{campus.PIN}" stroke="#ffffff" stroke-width=".7"/><circle cy="-12.6" r="2.3" fill="#fff"/>'
            f'<g transform="translate(0 -25)"><rect x="{num(-len(tag) * 2.9 - 5)}" y="-6.5" width="{num(len(tag) * 5.8 + 10)}" height="10.4" rx="5.2" fill="#0d1117" opacity=".82"/>'
            f'<text y="1.2" text-anchor="middle" font-family="{hero.GMONO}" font-size="7.2" letter-spacing=".6" fill="#ffffff">{tag}</text></g></g></g>')
        css.append("@keyframes ring{0%{transform:scale(.3);opacity:.9}100%{transform:scale(1.6);opacity:0}}.ring{transform-box:fill-box;transform-origin:center;animation:ring 2.4s ease-out infinite}"
                   "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.6px)}}.bob{animation:bob 2.4s ease-in-out infinite}")

    defs.append('<linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05070b" stop-opacity="0"/><stop offset="1" stop-color="#05070b" stop-opacity=".62"/></linearGradient>'
                f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="14"/></clipPath>')
    body.append(f'<rect y="{H - 74}" width="{W}" height="74" fill="url(#scrim)"/>')
    import gen
    bits = [label, f"{sky.local:%H:%M} {gen.ZONE['abbr']}", hero.caption(sky)]
    line = "  ·  ".join(x for x in bits if x).upper()
    aqi = f'<tspan dx="12" fill="{sky.band[2]}" font-size="7">●</tspan><tspan dx="5">AQI {sky.aqi}</tspan>' if sky.aqi is not None else ""
    text = (f'<text x="22" y="{H - 20}" font-family="{hero.GEIST}" font-size="13" letter-spacing=".2" fill="#eef2f7" opacity=".95">Student at DGIST</text>'
            f'<text x="858" y="{H - 20}" text-anchor="end" font-family="{hero.GMONO}" font-size="8.5" letter-spacing="1.3" fill="#eef2f7" opacity=".62">{escape(line)}{aqi}</text>')
    edge = f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#30363d"/>' if theme == "dark" else ""
    full = f'<g clip-path="url(#frame)">{"".join(body)}</g>{text}{edge}'
    title = f"Student at DGIST. A painting of the DGIST campus that follows its sky: {hero.caption(sky)}" + (f", AQI {sky.aqi}" if sky.aqi is not None else "")
    return svg(title, full, "".join(css), ("geist", "gmono"), "".join(defs), W, H)
