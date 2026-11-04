"""The profile's home view: the live sky over wherever Mushfique is, with "Student at DGIST" set small in the corner.

Layered ridges with depth haze, drifting mist, parallax clouds, the real sun and moon (setting behind the
hills), stars, shooting stars, birds, campus lights and the current weather. Every animation is a transform or
an opacity change and nothing uses a filter, so it stays cheap to render.
"""
import base64
import hashlib
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import gen
from gen import AQI, RAIN, SNOW, WMO, alt_az, ecl_to_eq, julian, mix, moon_ecliptic, moon_path, num, sun_ecliptic, svg

gen.FACES.update({"geist": ("GR", "Geist-Regular.ttf"), "gmono": ("GM", "GeistMono-Regular.ttf")})
GEIST = "'GR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
GMONO = "'GM',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
GRAIN = base64.b64encode((Path(__file__).with_name("grain.png")).read_bytes()).decode()
W, H = 880, 220
HORIZON = 150          # where altitude 0 meets the far range
ALT_SPAN = 42          # degrees of sky between the horizon and the top edge

# sun altitude -> zenith, upper, lower, horizon
PALETTE = [
    (-90, "#03050c", "#060a17", "#0a1022", "#111830"), (-18, "#04060f", "#080d1e", "#0e1530", "#18203d"),
    (-12, "#070b22", "#0f1636", "#1b224a", "#2d3060"), (-7, "#0e1640", "#1d2758", "#3a3c6e", "#6a5276"),
    (-3, "#18255a", "#33427a", "#7a6386", "#d58468"), (1, "#24477f", "#4f6fa6", "#a990a8", "#f2a875"),
    (6, "#2a5c9e", "#5487c2", "#93b3d6", "#efcfa8"), (15, "#2862aa", "#4d8acc", "#86b4e0", "#cfe2f1"),
    (90, "#2259a6", "#4581c8", "#78a9db", "#bcd6ee"),
]


@dataclass
class Sky:
    salt: float
    saz: float
    malt: float
    maz: float
    illum: float
    waxing: bool
    facing: float
    cloud: float
    code: int
    wind: float
    temp: float | None
    aqi: int | None
    band: tuple
    stops: tuple
    seed: int
    city: str
    country: str
    dgist: bool
    population: int
    local: datetime

    @property
    def night(self):
        return self.salt < -5

    @property
    def low(self):
        return -5 <= self.salt < 7


def sky_state(s):
    loc, w, air = s["location"], s.get("weather") or {}, s.get("air") or {}
    at = datetime.fromisoformat(s["at"])
    jd = julian(at)
    slam, _ = sun_ecliptic(jd)
    salt, saz = alt_az(*ecl_to_eq(slam, 0, jd), jd, loc["lat"], loc["lon"])
    mlam, mbeta = moon_ecliptic(jd)
    malt, maz = alt_az(*ecl_to_eq(mlam, mbeta, jd), jd, loc["lat"], loc["lon"])
    elong = (mlam - slam) % 360
    cloud = (w.get("cloud_cover") or 0) / 100
    stops = PALETTE[-1][1:]
    for (a0, *c0), (a1, *c1) in zip(PALETTE, PALETTE[1:]):
        if a0 <= salt <= a1:
            stops = tuple(mix(x, y, (salt - a0) / (a1 - a0)) for x, y in zip(c0, c1))
            break
    grey = cloud ** 1.5 * 0.7
    target = ("#7f8a97", "#939eaa", "#a9b2bc", "#c2c8ce") if salt > 0 else ("#0b0e15", "#11151e", "#181c27", "#252532")
    stops = tuple(mix(c, g, grey) for c, g in zip(stops, target))
    pop = loc.get("population") or 0
    if salt < -5 and pop > 50_000:
        stops = stops[:3] + (mix(stops[3], "#3e2c33", 0.3),)
    aqi = air.get("us_aqi")
    return Sky(salt, saz, malt, maz, (1 - math.cos(math.radians(elong))) / 2, elong < 180, 180 if loc["lat"] >= 0 else 0,
               cloud, w.get("weather_code") or 0, w.get("wind_speed_10m") or 0, w.get("temperature_2m"), aqi,
               next(b for b in AQI if (aqi or 0) <= b[0]), stops,
               int(hashlib.sha1(loc["city"].encode("utf-8")).hexdigest()[:8], 16), loc["city"], loc["country"],
               bool(loc.get("dgist")), pop, at + timedelta(seconds=gen.ZONE["offset"]))


def smooth(points):
    """Catmull-Rom through the points, as cubic Bezier segments."""
    d = f"M{num(points[0][0])},{num(points[0][1])}"
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{num(c1[0])},{num(c1[1])} {num(c2[0])},{num(c2[1])} {num(p2[0])},{num(p2[1])}"
    return d


def range_line(rnd, base, amp, step, octaves=3):
    phases = [rnd.uniform(0, 6.3) for _ in range(octaves)]
    pts = []
    for x in range(-40, W + 41, step):
        y = base - amp * sum((0.55 ** k) * (0.5 + 0.5 * math.sin(x / (170 / (k + 1)) + phases[k])) for k in range(octaves)) / 1.6
        pts.append((x, y))
    return pts


def ridged(rnd, base, amp, step, octaves, sharp):
    """Ridged noise: 1 - |sin| has cusps at its peaks, which reads as mountains rather than dunes."""
    phases = [rnd.uniform(0, 100) for _ in range(octaves)]
    pts = []
    for x in range(-40, W + 41, step):
        v, a, f = 0.0, 1.0, 1 / 150
        for k in range(octaves):
            v += a * (1 - abs(math.sin(x * f + phases[k]))) ** sharp
            a, f = a * 0.5, f * 2.15
        pts.append((x, base - amp * v / 1.9))
    return pts


def cumulus(rnd):
    """A cloud 100 units wide on a flat base at y=0: overlapping circles that merge into one silhouette."""
    parts = [f'<rect x="-46" y="-9" width="92" height="9" rx="4.5"/>']
    n = rnd.randint(4, 6)
    for i in range(n):
        t = (i + 0.5) / n
        r = (9 + 14 * math.sin(math.pi * t) ** 1.3) * rnd.uniform(0.8, 1.1)
        parts.append(f'<circle cx="{num(-40 + 80 * t + rnd.uniform(-3, 3))}" cy="{num(-r * 0.62)}" r="{num(r)}"/>')
    return "".join(parts)


def caption(sky):
    return " ".join(x for x in [f"{round(sky.temp)}°C" if sky.temp is not None else "", WMO.get(sky.code, "")] if x)


def scene(s, theme, W=880, H=220, HORIZON=150, foreground=None, label=None):
    """The shared sky, far range and weather. `foreground(sky, rnd, land, W, H, HORIZON)` replaces the hills when given."""
    sky = sky_state(s)
    rnd = random.Random(sky.seed ^ int(sky.local.timestamp()) // 1800)
    land = random.Random(sky.seed)
    zen, upper, lower, hor = sky.stops
    defs, body, css = [], [], []

    defs.append(f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{zen}"/><stop offset=".38" stop-color="{upper}"/>'
                f'<stop offset=".7" stop-color="{lower}"/><stop offset="1" stop-color="{hor}"/></linearGradient>')
    body.append(f'<rect width="{W}" height="{HORIZON + 30}" fill="url(#sky)"/>')

    def place(alt, az):
        d = ((az - sky.facing + 540) % 360) - 180
        if abs(d) > 74:
            return None
        return (d + 80) / 160 * W, HORIZON - alt / ALT_SPAN * HORIZON

    if sky.salt < -6:
        n = int(110 * (1 - sky.cloud * 0.85) * min(1, (-6 - sky.salt) / 6))
        stars = []
        for _ in range(n):
            sx, sy = rnd.uniform(4, W - 4), HORIZON * rnd.random() ** 1.5 * 0.95
            o = round(rnd.uniform(0.25, 0.9) * (1 - sy / HORIZON * 0.6), 2)
            r = rnd.choice([0.4, 0.5, 0.6, 0.75, 1.0])
            if rnd.random() < 0.22:
                stars.append(f'<circle cx="{num(sx)}" cy="{num(sy)}" r="{r}" style="--o:{o};animation:tw {rnd.uniform(3, 8):.1f}s ease-in-out {-rnd.uniform(0, 8):.1f}s infinite"/>')
            else:
                stars.append(f'<circle cx="{num(sx)}" cy="{num(sy)}" r="{r}" opacity="{o}"/>')
        body.append(f'<g fill="#fff">{"".join(stars)}</g>')
        css.append("@keyframes tw{0%,100%{opacity:var(--o)}50%{opacity:.06}}")
        if sky.cloud < 0.5:
            sx, sy = rnd.uniform(260, 760), rnd.uniform(12, 50)
            defs.append('<linearGradient id="ss" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".9"/></linearGradient>')
            body.append(f'<g transform="translate({num(sx)} {num(sy)}) rotate(160)"><rect class="ss" x="0" y="-.5" width="70" height="1" rx=".5" fill="url(#ss)"/></g>')
            css.append("@keyframes ss{0%,93%{opacity:0;transform:translateX(0)}94%{opacity:1}97.5%{opacity:0;transform:translateX(-120px)}100%{opacity:0;transform:translateX(-120px)}}"
                       f".ss{{animation:ss {rnd.uniform(19, 27):.1f}s ease-out {-rnd.uniform(0, 20):.1f}s infinite}}")

    sun = place(sky.salt, sky.saz)
    if sun and sky.salt > -12:
        warm = sky.salt < 10
        core = "#ffb070" if sky.salt < 3 else ("#ffd8a6" if warm else "#fff4dc")
        strength = max(0.0, min(1.0, (sky.salt + 12) / 10)) * (1 - sky.cloud * 0.55)
        defs.append(f'<radialGradient id="sg"><stop offset="0" stop-color="{core}" stop-opacity="{num(0.7 * strength, 2)}"/>'
                    f'<stop offset=".25" stop-color="{core}" stop-opacity="{num(0.28 * strength, 2)}"/><stop offset="1" stop-color="{core}" stop-opacity="0"/></radialGradient>')
        gy = min(sun[1], HORIZON + 4)
        body.append(f'<ellipse class="glow" cx="{num(sun[0])}" cy="{num(gy)}" rx="330" ry="150" fill="url(#sg)"/>')
        css.append("@keyframes glow{0%,100%{opacity:1}50%{opacity:.82}}.glow{animation:glow 9s ease-in-out infinite}")
        if sky.salt > -1.2 and sky.cloud < 0.9:
            body.append(f'<circle cx="{num(sun[0])}" cy="{num(sun[1])}" r="11" fill="#fff8ec" opacity="{num(1 - sky.cloud * 0.6, 2)}"/>')
    moon = place(sky.malt, sky.maz)
    if moon and sky.malt > -1 and sky.illum > 0.03 and sky.salt < 4:
        mx, my = round(moon[0], 1), round(moon[1], 1)
        defs.append('<radialGradient id="mg"><stop offset="0" stop-color="#efe6d2" stop-opacity=".2"/><stop offset="1" stop-color="#efe6d2" stop-opacity="0"/></radialGradient>')
        body.append(f'<circle cx="{mx}" cy="{my}" r="44" fill="url(#mg)"/><circle cx="{mx}" cy="{my}" r="7.5" fill="#efe6d2" opacity=".08"/>'
                    f'<path d="{moon_path(mx, my, 7.5, sky.illum, sky.waxing)}" fill="#f3ecd9"/>')

    if sky.night:
        lit, shade = "#3d4458", "#1b202c"
    elif sky.low:
        lit, shade = "#ffd7c0", "#8a6f80"
    else:
        lit, shade = mix("#ffffff", "#b2bac4", sky.cloud ** 2), mix("#b9c3cf", "#79838f", sky.cloud)
    if sky.cloud > 0.75:
        cover = min(1.0, (sky.cloud - 0.75) / 0.25)
        defs.append(f'<linearGradient id="deck" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{shade}" stop-opacity="{num(0.75 * cover, 2)}"/>'
                    f'<stop offset=".7" stop-color="{lit}" stop-opacity="{num(0.45 * cover, 2)}"/><stop offset="1" stop-color="{lit}" stop-opacity="0"/></linearGradient>')
        body.append(f'<rect width="{W}" height="{HORIZON}" fill="url(#deck)"/>')
    defs.append(f'<linearGradient id="cu" gradientUnits="userSpaceOnUse" x1="0" y1="-30" x2="0" y2="1"><stop offset="0" stop-color="{lit}"/>'
                f'<stop offset=".55" stop-color="{mix(lit, shade, 0.35)}"/><stop offset="1" stop-color="{shade}"/></linearGradient>'
                f'<radialGradient id="ci"><stop offset="0" stop-color="{lit}" stop-opacity=".5"/><stop offset="1" stop-color="{lit}" stop-opacity="0"/></radialGradient>')
    clouds = round(sky.cloud * 7)
    for layer, (share, speed, scale, op) in enumerate([(0.4, 1.0, 0.7, 0.75), (0.6, 1.7, 1.0, 0.92)]):
        period = max(70, 760 - sky.wind * 20) / speed
        for _ in range(round(clouds * share)):
            k = rnd.uniform(0.8, 1.6) * scale
            cw = 100 * k
            cy = rnd.uniform(40, 104) * (0.8 if layer == 0 else 1) * HORIZON / 150
            cid = f"c{len(defs)}"
            defs.append(f'<g id="{cid}">{cumulus(rnd)}</g>')
            shape = f'<use href="#{cid}"/>'
            body.append(f'<g class="drift" style="--a:{num(W + cw)}px;--b:{num(-cw)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                        f'<g transform="translate(0 {num(cy)}) scale({num(k, 2)} {num(k * rnd.uniform(0.75, 1), 2)})">'
                        f'<g transform="scale(1.07 1.1)" fill="{lit}" opacity="{num(op * 0.18, 2)}">{shape}</g><g fill="url(#cu)" opacity="{op}">{shape}</g></g></g>')
    for _ in range(round(sky.cloud * 3) if sky.cloud > 0.2 else 0):
        cw, cy = rnd.uniform(160, 320), rnd.uniform(14, 44)
        period = max(120, 1100 - sky.wind * 25)
        body.append(f'<g class="drift" style="--a:{num(W + cw)}px;--b:{num(-cw)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                    f'<ellipse cx="{num(cw / 2)}" cy="{num(cy)}" rx="{num(cw / 2)}" ry="3.2" fill="url(#ci)"/>'
                    f'<ellipse cx="{num(cw * 0.55)}" cy="{num(cy + 5)}" rx="{num(cw * 0.3)}" ry="2" fill="url(#ci)"/></g>')
    css.append("@keyframes drift{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}.drift{animation:drift linear infinite}")

    if not sky.night and sky.code < 45 and sky.cloud < 0.85:
        birds = "".join(f'<path class="flap" style="animation-delay:{-i * 0.17:.2f}s" transform="translate({dx} {dy})" d="M-3.2,0 Q-1.6,-1.6 0,0 Q1.6,-1.6 3.2,0"/>'
                        for i, (dx, dy) in enumerate([(0, 0), (-9, 4), (-17, 1), (-12, -5)]))
        by = rnd.uniform(55, 95) * HORIZON / 150
        body.append(f'<g class="flock" style="--a:-40px;--b:{W + 60}px"><g transform="translate(0 {num(by)})" fill="none" stroke="{mix(shade, "#1b2330", 0.6)}" stroke-width=".9" stroke-linecap="round" opacity=".7">{birds}</g></g>')
        css.append("@keyframes flock{0%{transform:translateX(var(--a))}60%,100%{transform:translateX(var(--b))}}"
                   f".flock{{animation:flock {rnd.uniform(70, 95):.0f}s linear {-rnd.uniform(0, 40):.0f}s infinite}}"
                   "@keyframes flap{0%,100%{transform:scaleY(1)}50%{transform:scaleY(-.5)}}.flap{transform-box:fill-box;transform-origin:center;animation:flap .55s ease-in-out infinite}")

    far_c = mix(hor, "#070a12", 0.5) if sky.night else mix(mix(hor, lower, 0.5), "#1a2332", 0.2)
    mid_c = mix(hor, "#05070b", 0.78) if sky.night else mix(hor, "#0c121b", 0.55)
    near_c = mix(hor, "#05070b", 0.93 if sky.night else 0.82)
    rim = mix(hor, "#ffe2c4" if sky.low else "#ffffff", 0.5)
    far = ridged(land, HORIZON + 8, 50 * min(1, HORIZON / 150 * 1.2), 6, 4, 1.6)
    mid = ridged(land, HORIZON + 30, 26, 8, 3, 1.1)
    near = range_line(land, HORIZON + 46, 9, 16, octaves=2)
    mist_c = mix(hor, "#ffffff", 0.18 if not sky.night else 0.04)
    mist_o = 0.42 if sky.code in (45, 48) else (0.22 if not sky.night else 0.12)
    defs.append(f'<linearGradient id="mist" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mist_c}" stop-opacity="0"/>'
                f'<stop offset=".6" stop-color="{mist_c}" stop-opacity="{mist_o}"/><stop offset="1" stop-color="{mist_c}" stop-opacity="0"/></linearGradient>')
    if sky.aqi:
        haze = min(0.5, sky.aqi / 250 * 0.55)
        defs.append(f'<linearGradient id="haze" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky.band[3]}" stop-opacity="0"/>'
                    f'<stop offset="1" stop-color="{sky.band[3]}" stop-opacity="{num(haze, 2)}"/></linearGradient>')
        body.append(f'<rect y="{HORIZON - 70}" width="{W}" height="90" fill="url(#haze)"/>')
    defs.append(f'<path id="farline" d="{smooth(far)} L{W + 40},{H} L-40,{H}Z"/>')
    body.append(f'<use href="#farline" fill="{far_c}"/><use href="#farline" fill="none" stroke="{rim}" stroke-width=".7" opacity="{".12" if sky.night else ".3"}"/>')
    body.append(f'<g class="mist" style="--a:-30px;--b:30px"><rect x="-40" y="{HORIZON + 4}" width="{W + 80}" height="30" fill="url(#mist)"/></g>')
    if foreground:
        fdefs, fbody, fcss = foreground(sky, rnd, land, W, H, HORIZON)
        defs += fdefs
        body += fbody
        css += fcss
    else:
        body.append(f'<path d="{smooth(mid)} L{W + 40},{H} L-40,{H}Z" fill="{mid_c}"/>')
        body.append(f'<g class="mist" style="--a:24px;--b:-24px;animation-duration:47s"><rect x="-40" y="{HORIZON + 24}" width="{W + 80}" height="24" fill="url(#mist)"/></g>')
        css.append("@keyframes mist{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}.mist{animation:mist 61s ease-in-out infinite alternate}")
        if sky.salt < -3:
            lights = []
            n = 24 if sky.dgist else max(6, min(46, int(math.log10(max(sky.population, 10)) * 7 - 16)))
            lo, hi = (330, 560) if sky.dgist else (60, W - 60)
            for _ in range(n):
                lx = land.uniform(lo, hi)
                ly = min(y for x, y in mid if abs(x - lx) <= 30) + land.uniform(4, 12)
                tw = f' style="animation:lamp {rnd.uniform(30, 120):.0f}s steps(1) {-rnd.uniform(0, 120):.0f}s infinite"' if rnd.random() < 0.18 else ""
                lights.append(f'<circle cx="{num(lx)}" cy="{num(ly)}" r="{num(land.uniform(0.5, 1.1), 2)}" opacity="{num(land.uniform(0.5, 1), 2)}"{tw}/>')
            body.append(f'<g fill="#f7d38c">{"".join(lights)}</g>')
            css.append("@keyframes lamp{0%,70%{opacity:1}71%,100%{opacity:.12}}")
        body.append(f'<path d="{smooth(near)} L{W + 40},{H} L-40,{H}Z" fill="{near_c}"/>')

    if sky.code in RAIN or sky.code in SNOW:
        rain = sky.code in RAIN
        for layer, (n, op, size, dur) in enumerate([(80, 0.2, 0.5, 0.8), (45, 0.38, 0.8, 0.55)] if rain else [(60, 0.55, 0.9, 11), (30, 0.85, 1.5, 7)]):
            drops = []
            for _ in range(n):
                dx, dy = rnd.uniform(0, W + 40), rnd.uniform(0, H)
                drops.append(f'<line x1="{num(dx)}" y1="{num(dy)}" x2="{num(dx - 3)}" y2="{num(dy + 10 + 5 * layer)}"/>' if rain
                             else f'<circle cx="{num(dx)}" cy="{num(dy)}" r="{size}"/>')
            tile = "".join(drops)
            paint = f'stroke="#dfe7f1" stroke-width="{size}" opacity="{op}"' if rain else f'fill="#f5f8fb" opacity="{op}"'
            css.append(f"@keyframes f{layer}{{from{{transform:translate(0,-{H}px)}}to{{transform:translate(-{60 if rain else 26}px,0)}}}}.f{layer}{{animation:f{layer} {dur}s linear infinite}}")
            body.append(f'<g class="f{layer}" {paint}>{tile}<g transform="translate(0 {H})">{tile}</g></g>')
    if sky.code >= 95:
        css.append("@keyframes flash{0%,92%,95%,100%{opacity:0}93%{opacity:.5}96%{opacity:.32}97.5%{opacity:0}}.flash{animation:flash 13s linear infinite}")
        body.append(f'<rect class="flash" width="{W}" height="{H}" fill="#eef2ff"/>')

    defs.append('<radialGradient id="vig" cx=".5" cy=".42" r=".75"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".32"/></radialGradient>'
                f'<pattern id="grain" width="64" height="64" patternUnits="userSpaceOnUse"><image width="64" height="64" href="data:image/png;base64,{GRAIN}"/></pattern>'
                f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="14"/></clipPath>')
    body.append(f'<rect width="{W}" height="{H}" fill="url(#vig)"/><rect width="{W}" height="{H}" fill="url(#grain)" opacity=".05"/>')

    where = "Daegu, Korea" if sky.dgist else f"{sky.city}, {sky.country}"
    bits = [label or where, f"{sky.local:%H:%M} {gen.ZONE['abbr']}", caption(sky)]
    line = "  ·  ".join(x for x in bits if x).upper()
    aqi = f'<tspan dx="12" fill="{sky.band[2]}" font-size="7">●</tspan><tspan dx="5">AQI {sky.aqi}</tspan>' if sky.aqi is not None else ""
    text = (f'<text x="22" y="{H - 19}" font-family="{GEIST}" font-size="13" letter-spacing=".2" fill="#eef2f7" opacity=".92">Student at DGIST</text>'
            f'<text x="858" y="{H - 19}" text-anchor="end" font-family="{GMONO}" font-size="8.5" letter-spacing="1.3" fill="#eef2f7" opacity=".55">{gen.escape(line)}{aqi}</text>')
    edge = f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#30363d"/>' if theme == "dark" else ""
    full = f'<g clip-path="url(#frame)">{"".join(body)}</g>{text}{edge}'
    title = f"Student at DGIST. The sky over {where} right now: {caption(sky)}" + (f", AQI {sky.aqi} ({sky.band[1]})" if sky.aqi is not None else "")
    return svg(title, full, "".join(css), ("geist", "gmono"), "".join(defs), W, H)


def hero_horizon(s, theme):
    return scene(s, theme)


HEROES = {"horizon": hero_horizon}
CHOSEN = "horizon"
