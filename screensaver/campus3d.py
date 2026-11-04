"""The home view, rendered: DGIST as a lit 3D miniature with the live sky, plus an SVG layer for motion and the pin.

render3d/scene.js draws the campus in three.js (terrain from SRTM, OSM footprints, materials from DGIST's campus
map, soft shadows, ambient occlusion, tilt-shift) in headless Chrome. This module builds its input, encodes the
frame as AVIF and wraps it in an SVG that adds what must move: clouds, weather, the shuttle, walkers, night cars
and the pin.
"""
import base64
import io
import json
import math
import random
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import campus
import hero
from gen import escape, mix, num, svg

HERE = Path(__file__).parent
TERRAIN = json.loads((HERE / "terrain.json").read_text(encoding="utf-8"))
W, H = 880, 440
SCALE = 1.5
SUPERSAMPLE = 2
BASE_ELEVATION = 64
FLOOR = 3.6

# Materials read off DGIST's 2024 campus map.
LOOK = {
    "podium": dict(style="band", wall="#e8ebee", glass="#5b95c2", glassHi="#a9d0ea", mullion="#d3dbe1", roof="#cfd5d9"),
    "wing": dict(style="band", wall="#eef1f3", glass="#4f8fc4", glassHi="#a6d2ef", mullion="#dbe2e7", roof="#d3d8dc"),
    "spine": dict(style="glass", wall="#d4e6f1", glass="#6aa6d0", glassHi="#d2ebf7", mullion="#f1f5f8", roof="#cfe4f0"),
    "E1": dict(style="glass", wall="#d8e5ee", glass="#3d79ab", glassHi="#8cbfe2", mullion="#eef2f5", roof="#c9d0d5"),
    "E8": dict(style="glass", wall="#a9c7da", glass="#5288b0", glassHi="#c7e0ee", mullion="#eef3f6", roof="#86b26a"),
    "E16": dict(style="glass", wall="#b6d0dc", glass="#3f7f94", glassHi="#9fd0dd", mullion="#e6eef1", roof="#cfd5d9"),
    "R1": dict(style="band", wall="#f3f1ec", glass="#5d8db0", glassHi="#b2d1e4", mullion="#e6e3dc", roof="#e8962c"),
    "R2": dict(style="band", wall="#f2f0ec", glass="#4b7ea4", glassHi="#a7c9de", mullion="#ee8a2e", fin=14, roof="#d9d6cf"),
    "R3": dict(style="band", wall="#f3f1ea", glass="#5285aa", glassHi="#adcde1", mullion="#f0c13a", fin=12, roof="#d9d6cf"),
    "R4": dict(style="band", wall="#eeeeec", glass="#557f9e", glassHi="#a9c6d9", mullion="#d6463c", fin=10, roof="#d6d6d2"),
    "R5": dict(style="glass", wall="#e9eef2", glass="#5a92bd", glassHi="#c4def0", mullion="#f4f6f8", roof="#d8dde0"),
    "R6": dict(style="band", wall="#e6e5e1", glass="#5a7d98", glassHi="#a8c3d6", mullion="#cfcdc7", roof="#d3d1cc"),
    "R7": dict(style="band", wall="#f0f2f4", glass="#5088b5", glassHi="#a8cbe3", mullion="#dde3e8", roof="#d3d8dc"),
    "S1": dict(style="band", wall="#f3f5f6", glass="#33536b", glassHi="#7c9bb0", mullion="#e6e9ec", roof="#7fae63"),
    "H": dict(style="punched", wall="#9b4f3c", glass="#2b2f36", glassHi="#5a6672", frame="#efe4d8", mullion="#efe4d8", roof="#79a663"),
    "O": dict(style="band", wall="#e2dfd8", glass="#6d8aa0", glassHi="#b2c7d5", mullion="#d2cec6", roof="#d2cec6"),
}



def box(cx, cy, w, d, angle=0.0):
    c, s = math.cos(angle), math.sin(angle)
    return [(round(cx + x * c - y * s, 1), round(cy + x * s + y * c, 1)) for x, y in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]


def ccw(poly):
    area = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))
    return poly if area > 0 else poly[::-1]


def buildings(hour, seed):
    point = {p["code"]: (p["x"], p["y"]) for p in campus.DATA["points"] if p["code"]}
    rnd = random.Random(seed)
    out = []

    def add(poly, look, floors, kind="E", codes=(), z0=0.0, green=False, **extra):
        out.append(dict(poly=ccw(poly) if poly else None, z0=z0, h=floors * FLOOR, style=LOOK[look]["style"], material=LOOK[look],
                        greenRoof=green, share=campus.lit_share(kind, list(codes), hour), seed=rnd.randrange(1 << 30), codes=list(codes), **extra))

    e = [point[f"E{i}"] for i in range(1, 7)]
    axis = math.atan2(e[5][1] - e[1][1], e[5][0] - e[1][0]) - math.pi / 2
    for b in campus.DATA["buildings"]:
        codes = b["codes"]
        if "E2" in codes:
            add(b["poly"], "podium", 1.2, codes=(), green=True)
        elif "E8" in codes or not b["poly"]:
            continue
        elif b["kind"] == "H":
            add(b["poly"], "H", 12 if "H501" in codes else 15, kind="H", codes=codes, green=True)
        elif codes:
            look = codes[0] if codes[0] in LOOK else "O"
            floors = {"R1": 3, "R2": 7, "R3": 8, "R4": 8, "R5": 5, "R6": 6, "R7": 6, "S1": 3}.get(codes[0], 6)
            add(b["poly"], look, floors, kind=codes[0][0], codes=codes, green=codes[0] == "S1", hipped=7 if codes[0] == "R1" else None)
        else:
            add(b["poly"], "O", 3, kind="O")
    for i, code in enumerate(["E2", "E3", "E4", "E5", "E6"]):
        x, y = point[code]
        add(box(x + 2, y, 94, 19, axis), "wing", 8, codes=[code], z0=0, green=i % 2 == 0)
    x4, y4 = point["E4"]
    x5, y5 = point["E5"]
    add(box((x4 + x5) / 2 - 30, (y4 + y5) / 2, 30, 18, axis), "wing", 5, codes=["E9"])
    sx, sy = point["E7"]
    length = math.hypot(e[5][0] - e[1][0], e[5][1] - e[1][1]) + 30
    mx, my = (e[1][0] + e[5][0]) / 2 + (sx - point["E3"][0]), (e[1][1] + e[5][1]) / 2
    add(box(mx, my, 22, length, axis), "spine", 3, codes=["E7"])
    add(box(*point["E1"], 46, 30, axis), "E1", 12, codes=["E1"])
    ex, ey = point["E8"]
    out.append(dict(poly=None, shape="oval", cx=ex, cy=ey, r=26, squash=0.82, z0=0, h=5 * FLOOR, style="glass", material=LOOK["E8"],
                    greenRoof=True, share=campus.lit_share("E", ["E8"], hour), seed=rnd.randrange(1 << 30), codes=["E8"]))
    r5x, r5y = point["R5"]
    add(box(r5x + 20, r5y + 78, 34, 30), "E16", 4, codes=["E16"])
    return out


def pin_anchor(pin, built):
    if pin == "dorms":
        x, y = campus.DATA["dorm_centre"]
        return x, y, 15 * FLOOR + 4
    for b in built:
        if pin in b["codes"]:
            if b.get("shape") == "oval":
                return b["cx"], b["cy"], b["h"] + 3
            xs, ys = [p[0] for p in b["poly"]], [p[1] for p in b["poly"]]
            return sum(xs) / len(xs), sum(ys) / len(ys), b["z0"] + b["h"] + (b.get("hipped") or 0) + 3
    x, y = next((p["x"], p["y"]) for p in campus.DATA["points"] if p["code"] == pin)
    return x, y, 30


LABELS = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E16", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "S1", "H501", "dorms"]


def render(sky, pin, buffers=None):
    """Render the campus. With `buffers` (a folder), also keep the raw frame and its colour, normal, depth and id buffers there."""
    built = buildings(sky.local.hour, sky.seed ^ sky.local.hour)
    g = campus.DATA["ground"]
    inner = lambda line: sum(campus.inside(p, campus.DATA["outline"]) for p in line) >= len(line) * 0.6
    near = lambda line: all(-700 < x < 760 and -650 < y < 640 for x, y in line)
    ground = {
        "roads": [dict(line=campus.simplify(r["line"]), main=r["main"]) for r in g["roads"] if (r["main"] and near(r["line"])) or inner(r["line"])],
        "paths": [campus.simplify(p) for p in g["paths"] if inner(p)],
        "parking": [ccw(p) for p in g["parking"] if inner(p)],
        "water": [ccw(p) for p in g["water"] if near(p)],
        "pitch": [dict(p, poly=ccw(p["poly"])) for p in g["pitch"] if near(p["poly"])],
    }
    pins = {pin: pin_anchor(pin, built)} if pin else {}
    spec = {
        "width": round(W * SCALE), "height": round(H * SCALE), "base": BASE_ELEVATION, "terrain": TERRAIN,
        "outline": ccw(campus.DATA["outline"]), "buildings": built, "ground": ground, "pins": pins,
        "sky": {"salt": sky.salt, "saz": sky.saz, "malt": sky.malt, "maz": sky.maz, "cloud": sky.cloud, "stops": list(sky.stops)},
        "camera": {"fov": 14, "azimuth": 40, "elevation": 33, "fillX": 0.96, "fillY": 0.9, "liftY": 0.0, "focus": 0.45, "blur": 3.0},
        "month": sky.local.month, "day": sky.local.day, "supersample": SUPERSAMPLE,
        "labels": {code: pin_anchor(code, built) for code in LABELS}, "buffers": bool(buffers),
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        run = subprocess.run(["node", str(HERE / "render3d" / "render.mjs"), str(tmp / "spec.json"), str(tmp / "frame.png"), str(tmp / "overlay.json")],
                             capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stderr[-2000:])
        print(run.stdout.strip(), run.stderr.strip()[:300])
        frame = Image.open(tmp / "frame.png").convert("RGB").resize((spec["width"], spec["height"]), Image.LANCZOS)
        overlay = json.loads((tmp / "overlay.json").read_text(encoding="utf-8"))
        if buffers:
            Path(buffers).mkdir(parents=True, exist_ok=True)
            for f in tmp.glob("frame*.png"):
                f.replace(Path(buffers) / f.name)
            (Path(buffers) / "overlay.json").write_text(json.dumps(dict(overlay, codes=[b["codes"] for b in built])), encoding="utf-8")
    buf = io.BytesIO()
    frame.save(buf, "AVIF", quality=60, speed=5)
    return buf.getvalue(), overlay, frame


def path_d(points):
    k = 1 / SCALE
    return "M" + " L".join(f"{num(x * k)},{num(y * k)}" for x, y in points)


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
    avif, overlay, _ = render(sky, pin)
    rnd = random.Random(sky.seed ^ int(sky.local.timestamp()) // 1800)
    night = sky.salt < -4
    horizon = overlay["horizon"] / SCALE
    defs, body, css = [], [f'<image width="{W}" height="{H}" href="data:image/avif;base64,{base64.b64encode(avif).decode()}"/>'], []

    if sky.cloud > 0.15 and horizon > 30:
        lit, shade = ("#3d4458", "#1b202c") if night else (("#ffd7c0", "#8a6f80") if sky.low else ("#ffffff", "#aeb8c3"))
        defs.append(f'<linearGradient id="cu" gradientUnits="userSpaceOnUse" x1="0" y1="-30" x2="0" y2="1"><stop offset="0" stop-color="{lit}"/><stop offset="1" stop-color="{shade}"/></linearGradient>')
        period = max(80, 700 - sky.wind * 18)
        for i in range(1 + round(sky.cloud * 3)):
            k = rnd.uniform(0.5, 0.9)
            cid = f"c{i}"
            defs.append(f'<g id="{cid}">{hero.cumulus(rnd)}</g>')
            cy = rnd.uniform(horizon * 0.35, horizon * 0.85)
            body.append(f'<g class="drift" style="--a:{num(W + 100 * k)}px;--b:{num(-100 * k)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                        f'<g transform="translate(0 {num(cy)}) scale({num(k, 2)})" fill="url(#cu)" opacity=".9"><use href="#{cid}"/></g></g>')
        css.append("@keyframes drift{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}.drift{animation:drift linear infinite}")
    if not night and sky.cloud > 0.2:
        defs.append('<radialGradient id="cs"><stop offset="0" stop-color="#0c1a10" stop-opacity=".2"/><stop offset="1" stop-color="#0c1a10" stop-opacity="0"/></radialGradient>')
        period = max(90, 600 - sky.wind * 15)
        for _ in range(2 + round(sky.cloud * 2)):
            cy, rx = rnd.uniform(horizon + 40, H - 50), rnd.uniform(120, 200)
            body.append(f'<g class="drift" style="--a:{num(W + rx)}px;--b:{num(-rx)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                        f'<ellipse cy="{num(cy)}" rx="{num(rx)}" ry="{num(rx * 0.3)}" fill="url(#cs)"/></g>')
    roads = sorted(overlay["roads"], key=lambda l: -sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(l, l[1:])))
    if roads:
        bus = ('<rect x="-3.4" y="-3.6" width="6.8" height="2.8" rx=".9" fill="#f4f6f7"/><rect x="-2.8" y="-3.1" width="5.6" height=".9" fill="#3f78ad"/>' if not night
               else '<rect x="-3.4" y="-3.6" width="6.8" height="2.8" rx=".9" fill="#2a313c"/><rect x="-2.8" y="-3.1" width="5.6" height=".9" fill="#ffe0a0"/><circle cx="3.6" cy="-1.5" r="2" fill="#fff2c8" opacity=".55"/>')
        body.append(f'<g>{bus}<animateMotion dur="150s" repeatCount="indefinite" keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(roads[0])}"/></g>')
        if night:
            for i, line in enumerate(roads[1:4]):
                body.append(f'<g><circle r=".9" fill="#fff4d0"/><circle cx="1.6" r=".9" fill="#fff4d0"/><animateMotion dur="{60 + 20 * i}s" begin="-{i * 9}s" repeatCount="indefinite" path="{path_d(line)}"/></g>')
    if 7 <= sky.local.hour < 23:
        for i, line in enumerate(sorted(overlay["paths"], key=len, reverse=True)[:8]):
            if len(line) < 2:
                continue
            colour = ["#f0b37a", "#8fb3e8", "#f3efe6", "#e07a6e"][i % 4] if not night else "#cdd6e0"
            body.append(f'<circle r=".9" fill="{colour}"><animateMotion dur="{80 + 25 * i}s" begin="-{rnd.uniform(0, 60):.0f}s" repeatCount="indefinite" keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(line)}"/></circle>')
    if sky.code in hero.RAIN or sky.code in hero.SNOW:
        rain = sky.code in hero.RAIN
        for layer, (n, op, size, dur) in enumerate([(80, 0.22, 0.5, 0.8), (45, 0.38, 0.8, 0.55)] if rain else [(60, 0.55, 0.9, 11), (30, 0.85, 1.5, 7)]):
            drops = "".join(f'<line x1="{num(x)}" y1="{num(y)}" x2="{num(x - 3)}" y2="{num(y + 10)}"/>' if rain else f'<circle cx="{num(x)}" cy="{num(y)}" r="{size}"/>'
                            for x, y in ((rnd.uniform(0, W + 40), rnd.uniform(0, H)) for _ in range(n)))
            paint = f'stroke="#dfe7f1" stroke-width="{size}" opacity="{op}"' if rain else f'fill="#f5f8fb" opacity="{op}"'
            css.append(f"@keyframes f{layer}{{from{{transform:translate(0,-{H}px)}}to{{transform:translate(-{60 if rain else 26}px,0)}}}}.f{layer}{{animation:f{layer} {dur}s linear infinite}}")
            body.append(f'<g class="f{layer}" {paint}>{drops}<g transform="translate(0 {H})">{drops}</g></g>')
    if pin and pin in overlay["pins"]:
        px, py = (v / SCALE for v in overlay["pins"][pin])
        tag = "Dorms" if pin == "dorms" else pin
        body.append(
            f'<g transform="translate({num(px)} {num(py)})">'
            f'<ellipse class="ring" rx="10" ry="3.6" fill="none" stroke="{campus.PIN}" stroke-width="1.1"/><ellipse rx="2.8" ry="1.1" fill="#000" opacity=".35"/>'
            f'<g class="bob"><path d="M0,-1C-2,-5.4 -5.6,-8 -5.6,-11.6A5.6,5.6 0 1 1 5.6,-11.6C5.6,-8 2,-5.4 0,-1Z" fill="{campus.PIN}" stroke="#ffffff" stroke-width=".6"/><circle cy="-11.6" r="2.1" fill="#fff"/>'
            f'<g transform="translate(0 -23)"><rect x="{num(-len(tag) * 2.7 - 4.5)}" y="-6" width="{num(len(tag) * 5.4 + 9)}" height="9.6" rx="4.8" fill="#0d1117" opacity=".82"/>'
            f'<text y="1.1" text-anchor="middle" font-family="{hero.GMONO}" font-size="6.8" letter-spacing=".6" fill="#ffffff">{tag}</text></g></g></g>')
        css.append("@keyframes ring{0%{transform:scale(.3);opacity:.9}100%{transform:scale(1.6);opacity:0}}.ring{transform-box:fill-box;transform-origin:center;animation:ring 2.4s ease-out infinite}"
                   "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.6px)}}.bob{animation:bob 2.4s ease-in-out infinite}")
    defs.append('<linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05070b" stop-opacity="0"/><stop offset="1" stop-color="#05070b" stop-opacity=".62"/></linearGradient>'
                f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="14"/></clipPath>')
    body.append(f'<rect y="{H - 70}" width="{W}" height="70" fill="url(#scrim)"/>')
    import gen
    bits = [label, f"{sky.local:%H:%M} {gen.ZONE['abbr']}", hero.caption(sky)]
    line = "  ·  ".join(x for x in bits if x).upper()
    aqi = f'<tspan dx="12" fill="{sky.band[2]}" font-size="7">●</tspan><tspan dx="5">AQI {sky.aqi}</tspan>' if sky.aqi is not None else ""
    text = (f'<text x="22" y="{H - 19}" font-family="{hero.GEIST}" font-size="13" letter-spacing=".2" fill="#eef2f7" opacity=".94">Student at DGIST</text>'
            f'<text x="858" y="{H - 19}" text-anchor="end" font-family="{hero.GMONO}" font-size="8.5" letter-spacing="1.3" fill="#eef2f7" opacity=".6">{escape(line)}{aqi}</text>'
            f'<text x="{W - 12}" y="{H - 6}" text-anchor="end" font-family="{hero.GMONO}" font-size="5.5" fill="#ffffff" opacity=".35">map © OpenStreetMap · terrain SRTM</text>')
    edge = f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#30363d"/>' if theme == "dark" else ""
    full = f'<g clip-path="url(#frame)">{"".join(body)}</g>{text}{edge}'
    title = f"Student at DGIST. A live miniature of the DGIST campus: {hero.caption(sky)}" + (f", AQI {sky.aqi}" if sky.aqi is not None else "")
    return svg(title, full, "".join(css), ("geist", "gmono"), "".join(defs), W, H)
