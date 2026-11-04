"""The home view: DGIST in miniature under its live sky, with a pin on the building Mushfique is in.

Footprints come from OpenStreetMap and building codes from DGIST (campus.json, built by campus_data.py).
Materials follow DGIST's official campus map: white teaching blocks with blue-teal glass, a round glass
library, the gold pyramid roof of R1, brick research blocks, maroon brick dorm towers with green roofs,
forest on every side. Walls are shaded by the real sun direction and buildings cast shadows by day. Windows
light up floor by floor in a pattern set by the building and the local hour. Animations are transforms,
opacity and SMIL motion only, with no filters.
"""
import json
import math
import random
from pathlib import Path

import hero
from gen import mix, num

DATA = json.loads(Path(__file__).with_name("campus.json").read_text(encoding="utf-8"))
W, H, HORIZON = 880, 380, 58
FLOOR_M = 3.6
PIN = "#ff5a4e"
PATTERN_LEVELS = (0.1, 0.25, 0.4, 0.55, 0.7)
CAMPUS_BOX = (-540, 550, -470, 500)
DGIST_LOC = {"city": "Daegu", "country": "South Korea", "country_code": "KR", "lat": 35.6965, "lon": 128.4560,
             "tz": "Asia/Seoul", "population": 2_400_000, "dgist": True}

# Colours read off DGIST's official campus map. style: band = ribbon windows, punched = framed windows, glass = curtain wall.
MATERIAL = {
    "E": dict(wall="#e7eaeb", glass="#5b93b6", roof="#cfd5d8", style="band"),
    "E1": dict(wall="#dfe6ea", glass="#4b83ad", roof="#c6ced3", style="glass"),
    "E8": dict(wall="#78aacd", glass="#5a95c0", roof="#dde7ed", style="glass"),
    "R1": dict(wall="#eeeae2", glass="#6d91ab", roof="#e3982f", style="band"),
    "R2": dict(wall="#c5653f", glass="#35424f", roof="#d8d2c8", style="punched", frame="#f2d9a8"),
    "R3": dict(wall="#d47a47", glass="#35424f", roof="#d8d2c8", style="punched", frame="#f6dfb0"),
    "R4": dict(wall="#efeeea", glass="#6a8aa3", roof="#d4d4cf", style="band", accent="#c9473f"),
    "R5": dict(wall="#eef1f4", glass="#5b8fc9", roof="#d6dade", style="band", accent="#4d87c7"),
    "R6": dict(wall="#e7e6e1", glass="#7393ab", roof="#d3d2cc", style="band", accent="#d46b63"),
    "R7": dict(wall="#dde2e6", glass="#7a99b0", roof="#cfd5d9", style="band"),
    "H": dict(wall="#8a4136", glass="#2b2526", roof="#7a9e67", style="punched", frame="#efe6dc"),
    "S1": dict(wall="#eef1f2", glass="#8db0c6", roof="#82b065", style="band"),
    "O": dict(wall="#d9d6cf", glass="#7e8f9c", roof="#cfcbc3", style="band"),
}
FLOORS = {"E": 7, "E1": 9, "E8": 5, "R1": 4, "R2": 6, "R3": 6, "R4": 7, "R5": 6, "R6": 4, "R7": 6, "H": 13, "H501": 9, "S1": 3}


def circle(cx, cy, r, n=22):
    return [(round(cx + r * math.cos(2 * math.pi * i / n), 1), round(cy + r * math.sin(2 * math.pi * i / n), 1)) for i in range(n)]


def campus_buildings():
    """OSM footprints with DGIST's shapes put back: the round library and E1's taller glass block."""
    point = {p["code"]: p for p in DATA["points"] if p["code"]}
    out = []
    for b in DATA["buildings"]:
        b = dict(b)
        if "E8" in b["codes"]:
            b["poly"] = circle(point["E8"]["x"], point["E8"]["y"], 23)
        key = next((c for c in b["codes"] if c in MATERIAL or c in FLOORS), None) or b["kind"]
        if b["kind"] == "E" and key != "E8":
            key = "E"
        b["key"] = key
        b["floors"] = FLOORS.get(key, FLOORS.get(b["kind"], b["floors"]))
        out.append(b)
    e1 = point["E1"]
    out.append({"poly": [(e1["x"] - 24, e1["y"] - 15), (e1["x"] + 24, e1["y"] - 15), (e1["x"] + 24, e1["y"] + 15), (e1["x"] - 24, e1["y"] + 15)],
                "codes": ["E1"], "kind": "E", "key": "E1", "floors": FLOORS["E1"]})
    return out


BUILDINGS = campus_buildings()


class Camera:
    """An aerial oblique view from the south, like DGIST's own map: depth recedes up and slightly right."""

    def __init__(self, polys, rot_deg=-9, lean=0.18, top=HORIZON + 22, bottom=H - 48, width=W - 20):
        self.c, self.s_ = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
        corners = [self.rotate(x, y) for poly in polys for x, y in poly]
        self.x0, self.x1 = min(p[0] for p in corners) - 40, max(p[0] for p in corners) + 40
        self.y0, self.y1 = min(p[1] for p in corners) - 30, max(p[1] for p in corners) + 30
        self.lean = lean
        self.s = width / ((self.x1 - self.x0) + (self.y1 - self.y0) * lean)
        self.k = (bottom - top) / ((self.y1 - self.y0) * self.s)
        self.ox, self.oy = (W - width) / 2, bottom
        self.hz = 0.95

    def rotate(self, x, y):
        return x * self.c - y * self.s_, x * self.s_ + y * self.c

    def __call__(self, x, y, z=0.0):
        xr, yr = self.rotate(x, y)
        return (self.ox + (xr - self.x0) * self.s + (yr - self.y0) * self.s * self.lean,
                self.oy - (yr - self.y0) * self.s * self.k - z * self.s * self.hz)

    def depth(self, x, y):
        return self.rotate(x, y)[1]

    def near(self, line, margin=70):
        return all(self.x0 - margin < self.rotate(x, y)[0] < self.x1 + margin and self.y0 - margin < self.rotate(x, y)[1] < self.y1 + margin
                   for x, y in line[::max(1, len(line) // 4)])


def pts(seq):
    return " ".join(f"{num(x)},{num(y)}" for x, y in seq)


def path_d(seq):
    seq = list(seq)
    return f"M{num(seq[0][0])},{num(seq[0][1])}" + "".join(f"l{num(b[0] - a[0])},{num(b[1] - a[1])}" for a, b in zip(seq, seq[1:]))


def simplify(line, tol=2.0):
    """Douglas-Peucker in metres."""
    if len(line) < 3:
        return line
    (x1, y1), (x2, y2) = line[0], line[-1]
    span = math.hypot(x2 - x1, y2 - y1) or 1e-9
    far, idx = 0.0, 0
    for i, (x, y) in enumerate(line[1:-1], 1):
        d = abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / span
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [line[0], line[-1]]
    return simplify(line[:idx + 1], tol)[:-1] + simplify(line[idx:], tol)


def length(line):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:]))


def lit_share(kind, codes, hour):
    """Share of windows lit at this local hour: labs keep late hours, dorms fill up in the evening."""
    if "E8" in codes:
        return 0.7 if hour >= 9 or hour < 1 else 0.08
    if kind == "H":
        return 0.62 if hour >= 18 else 0.38 if hour < 2 else 0.08 if hour < 6 else 0.3 if hour < 9 else 0.15
    if kind in ("E", "R"):
        return 0.45 if hour >= 19 else 0.28 if hour < 2 else 0.12 if hour < 6 else 0.22 if hour < 9 else 0.55
    return 0.35 if 17 <= hour < 22 else 0.05


def dash(cells, w=1.5, gap=1.7):
    """A dasharray that draws only the lit cells of a row of windows."""
    if not any(cells):
        return None
    lead = (w + gap) * (cells.index(True))
    out, pending = (["0", num(lead, 2)] if lead else []), 0.0
    for on in cells[cells.index(True):]:
        if on:
            if pending:
                out.append(num(pending, 2))
            out.append(num(w, 2))
            pending = gap
        else:
            pending += w + gap
    return " ".join(out + [num(pending + 999, 2)])


def window_patterns(rnd, cells=60):
    return "".join(f".w{li}{v}{{stroke-dasharray:{dash([rnd.random() < share for _ in range(cells)]) or '0 999'}}}"
                   for li, share in enumerate(PATTERN_LEVELS) for v in range(3))


def forest_tiles(rnd, night):
    """Two canopy tiles of coprime sizes layered over each other, so the repeat never lines up visibly."""
    greens = ["#26432b", "#2f5233", "#3a6237", "#46713f", "#557f47"] if not night else ["#0a120d", "#0c1610", "#0e1912", "#101c14", "#121f16"]
    tiles = []
    for name, (w, h, n, rmin, rmax) in {"forest": (97, 41, 70, 1.4, 3.4), "canopy": (61, 29, 26, 1.1, 2.6)}.items():
        crowns = "".join(f'<circle cx="{num(rnd.uniform(0, w))}" cy="{num(rnd.uniform(0, h))}" r="{num(rnd.uniform(rmin, rmax))}" fill="{rnd.choice(greens[1:])}"/>' for _ in range(n))
        hi = "" if night else "".join(f'<circle cx="{num(rnd.uniform(0, w))}" cy="{num(rnd.uniform(0, h))}" r="{num(rnd.uniform(.6, 1.3))}" fill="#79a25b" opacity=".55"/>' for _ in range(n // 4))
        ground = f'<rect width="{w}" height="{h}" fill="{greens[0]}"/>' if name == "forest" else ""
        tiles.append(f'<pattern id="{name}" width="{w}" height="{h}" patternUnits="userSpaceOnUse">{ground}{crowns}{hi}</pattern>')
    return "".join(tiles)


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def foreground(pin):
    def draw(sky, rnd, land, W_, H_, horizon):
        cam = Camera([b["poly"] for b in BUILDINGS] + [p["poly"] for p in DATA["ground"]["pitch"]])
        g = DATA["ground"]
        night = sky.salt < -4
        daylight = max(0.0, min(1.0, sky.salt / 14))
        dusk = -4 <= sky.salt < 8
        hour = sky.local.hour
        hor = sky.stops[3]
        defs, body, css = [], [], []

        def tone(colour, k=0.0):
            """A material colour under the current light: k=1 is fully sunlit, k=0 in shade."""
            if night:
                return mix(colour, "#0a0f1c", 0.8)
            shade = mix(colour, "#1d2430", 0.5)
            lit = mix(colour, "#ffb98c", 0.16) if dusk else colour
            return mix(mix(shade, lit, 0.45 + 0.55 * k * max(daylight, 0.35)), hor, 0.06)

        defs.append(forest_tiles(random.Random(7), night))
        edge_y = max(cam(0, cam.y1 + 900)[1], horizon + 10)
        ground = f"M-20,{num(edge_y)} Q{W / 2},{num(edge_y - 8)} {W + 20},{num(edge_y)} L{W + 20},{H} L-20,{H}Z"
        body.append(f'<path d="{ground}" fill="url(#forest)"/><path d="{ground}" fill="url(#canopy)" opacity=".8"/>')
        defs.append(f'<linearGradient id="depth" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{hor}" stop-opacity=".55"/>'
                    f'<stop offset=".35" stop-color="{hor}" stop-opacity=".12"/><stop offset="1" stop-color="{hor}" stop-opacity="0"/></linearGradient>')
        body.append(f'<rect y="{num(edge_y - 8)}" width="{W}" height="{num(H - edge_y + 8)}" fill="url(#depth)"/>')

        def poly(points, fill, extra=""):
            ring = simplify(points, 1.5) if len(points) > 8 else points
            return f'<polygon points="{pts(cam(x, y) for x, y in ring)}" fill="{fill}"{extra}/>'

        def on_campus(line):
            return all(CAMPUS_BOX[0] < x < CAMPUS_BOX[1] and CAMPUS_BOX[2] < y < CAMPUS_BOX[3] for x, y in line[::max(1, len(line) // 4)])

        keep = lambda items: [p for p in items if on_campus(p)]
        lawn = tone("#86b35f", 0.8)
        clip = f'<clipPath id="campus"><polygon points="{pts(cam(x, y) for x, y in DATA["outline"])}"/></clipPath>'
        defs.append(clip)
        skirt = "".join("M" + " L".join(f"{num(px)},{num(py)}" for px, py in (cam(x, y) for x, y in b["poly"])) + "Z" for b in BUILDINGS)
        lanes = "".join(path_d(cam(x, y) for x, y in r["line"]) for r in g["roads"] if sum(inside(p, DATA["outline"]) for p in r["line"]) >= len(r["line"]) * 0.6)
        body.append(f'<g clip-path="url(#campus)" fill="none" stroke="{lawn}" stroke-linejoin="round" stroke-linecap="round">'
                    f'<path d="{skirt}" fill="{lawn}" stroke-width="{num(70 * cam.s, 1)}"/><path d="{lanes}" stroke-width="{num(34 * cam.s, 1)}"/></g>')
        area = lambda p: abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(p, p[1:] + p[:1]))) / 2
        body += [poly(p, tone("#78a655", 0.75)) for p in keep(g["green"]) if len(p) > 3 and area(p) < 15_000]
        water = mix(sky.stops[1], "#3f7fa8", 0.55) if not night else mix(sky.stops[1], "#0a1424", 0.5)
        body += [poly(p, water, ' class="wt"') for p in keep(g["water"])]
        css.append("@keyframes wt{0%,100%{opacity:1}50%{opacity:.85}}.wt{animation:wt 7s ease-in-out infinite}")
        body += [poly(p, tone("#a4a5a2", 0.7)) for p in keep(g["parking"])]
        line_c = tone("#e9efe6", 0.8)
        for p in g["pitch"]:
            if not on_campus(p["poly"]):
                continue
            if p["sport"] == "soccer":
                cx = sum(x for x, _ in p["poly"]) / len(p["poly"])
                cy = sum(y for _, y in p["poly"]) / len(p["poly"])
                inner = [(cx + (x - cx) * 0.78, cy + (y - cy) * 0.7) for x, y in p["poly"]]
                body.append(poly(p["poly"], tone("#b9573f", 0.8)) + poly(inner, tone("#4f9a46", 0.8), f' stroke="{line_c}" stroke-width=".5"'))
            elif "tennis" in p["sport"]:
                body.append(poly(p["poly"], tone("#4f8f72", 0.8), f' stroke="{line_c}" stroke-width=".4"'))
            elif "basketball" in p["sport"]:
                body.append(poly(p["poly"], tone("#c49a66", 0.8)))
        inner = lambda line: sum(inside(p, DATA["outline"]) for p in line) >= len(line) * 0.6
        roads = [dict(r, line=simplify(r["line"])) for r in g["roads"] if (r["main"] and cam.near(r["line"], 160)) or inner(r["line"])]
        paths = [simplify(l) for l in g["paths"] if inner(l)]
        road = tone("#b4b3ae", 0.8) if not night else "#1b1f27"
        for main in (False, True):
            d = "".join(path_d(cam(x, y) for x, y in r["line"]) for r in roads if r["main"] == main)
            if d:
                body.append(f'<path d="{d}" fill="none" stroke="{road}" stroke-width="{2.8 if main else 1.6}" stroke-linecap="round" stroke-linejoin="round"/>')
        if paths:
            body.append(f'<path d="{"".join(path_d(cam(x, y) for x, y in l) for l in paths)}" fill="none" stroke="{tone("#d8d3c6", 0.8)}" stroke-width=".8"/>')

        if not night and sky.salt > 2:
            reach = min(3.0, 1 / math.tan(math.radians(max(sky.salt, 9))))
            off = (-math.sin(math.radians(sky.saz)) * reach, -math.cos(math.radians(sky.saz)) * reach)
            shadows = []
            for b in BUILDINGS:
                h = b["floors"] * FLOOR_M
                dx, dy = off[0] * h, off[1] * h
                quads = [pts(cam(x, y) for x, y in b["poly"])]
                for (x1, y1), (x2, y2) in zip(b["poly"], b["poly"][1:] + b["poly"][:1]):
                    quads.append(pts([cam(x1, y1), cam(x2, y2), cam(x2 + dx, y2 + dy), cam(x1 + dx, y1 + dy)]))
                shadows.append("".join(f'<polygon points="{q}"/>' for q in quads))
            body.append(f'<g fill="#0e1a10" opacity="{num(0.3 * (1 - sky.cloud * 0.6), 2)}">{"".join(shadows)}</g>')

        if night:
            defs.append('<radialGradient id="slg"><stop offset="0" stop-color="#ffd28a" stop-opacity=".45"/><stop offset="1" stop-color="#ffd28a" stop-opacity="0"/></radialGradient>'
                        '<g id="sl"><circle r="3.8" fill="url(#slg)"/><circle cy="-1.2" r=".55" fill="#ffe2a8"/></g>')
            glows = []
            for r in roads:
                if r["main"]:
                    for (x1, y1), (x2, y2) in zip(r["line"], r["line"][1:]):
                        n = int(math.hypot(x2 - x1, y2 - y1) // 60)
                        for i in range(n):
                            gx, gy = cam(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n)
                            glows.append(f'<use href="#sl" x="{num(gx)}" y="{num(gy)}"/>')
            body.append("".join(glows))

        objects = []
        sun_dir = (math.sin(math.radians(sky.saz)), math.cos(math.radians(sky.saz)))
        floor_px = FLOOR_M * cam.s * cam.hz
        for b in BUILDINGS:
            m = MATERIAL.get(b["key"], MATERIAL.get(b["kind"], MATERIAL["O"]))
            poly_m, h = b["poly"], b["floors"] * FLOOR_M
            share = lit_share(b["kind"], b["codes"], hour)
            brnd = random.Random(hash((tuple(b["codes"]), b["floors"], len(poly_m))) ^ sky.seed ^ hour)
            parts, rows, frames = [], {}, []
            for (x1, y1), (x2, y2) in zip(poly_m, poly_m[1:] + poly_m[:1]):
                a, b2, c, d = cam(x1, y1), cam(x2, y2), cam(x2, y2, h), cam(x1, y1, h)
                if (b2[0] - a[0]) * (d[1] - a[1]) - (b2[1] - a[1]) * (d[0] - a[0]) >= 0:
                    continue
                run = math.hypot(x2 - x1, y2 - y1)
                facing = max(0.0, (y2 - y1) / run * sun_dir[0] - (x2 - x1) / run * sun_dir[1])
                base = m["glass"] if m["style"] == "glass" else m["wall"]
                parts.append(f'<polygon points="{pts([a, b2, c, d])}" fill="{tone(base, facing)}"/>')
                if m.get("accent"):
                    ta, tb = cam(x1, y1, h - 1.2), cam(x2, y2, h - 1.2)
                    parts.append(f'<line x1="{num(ta[0])}" y1="{num(ta[1])}" x2="{num(tb[0])}" y2="{num(tb[1])}" stroke="{tone(m["accent"], facing)}" stroke-width="{num(floor_px * 0.5, 2)}"/>')
                if math.hypot(b2[0] - a[0], b2[1] - a[1]) < 4:
                    continue
                for f in range(b["floors"]):
                    z = f * FLOOR_M + 1.8
                    p1 = cam(x1 + (x2 - x1) * 0.04, y1 + (y2 - y1) * 0.04, z)
                    p2 = cam(x1 + (x2 - x1) * 0.96, y1 + (y2 - y1) * 0.96, z)
                    seg = f"M{num(p1[0])},{num(p1[1])}l{num(p2[0] - p1[0])},{num(p2[1] - p1[1])}"
                    rows.setdefault(brnd.randrange(3), []).append(seg)
                    frames.append(seg)
            if frames:
                allrows = "".join(frames)
                if m["style"] == "punched":
                    rid = f"r{len(defs)}"
                    defs.append(f'<path id="{rid}" d="{allrows}"/>')
                    parts.append(f'<use href="#{rid}" fill="none" stroke="{tone(m["frame"], 0.7)}" stroke-width="{num(floor_px * 0.5, 2)}" stroke-dasharray="2.6 1" opacity=".85"/>')
                    parts.append(f'<use href="#{rid}" fill="none" stroke="{tone(m["glass"], 0.3) if not night else "#141217"}" stroke-width="{num(floor_px * 0.3, 2)}" stroke-dasharray="1.8 1.8" stroke-dashoffset="-.4"/>')
                elif m["style"] == "band":
                    glass = mix(tone(m["glass"], 0.6), sky.stops[1], 0.25) if not night else "#0d1520"
                    parts.append(f'<path d="{allrows}" fill="none" stroke="{glass}" stroke-width="{num(floor_px * 0.48, 2)}"/>')
                else:
                    sheen = mix(tone(m["glass"], 0.9), "#ffffff", 0.25) if not night else "#18222e"
                    parts.append(f'<path d="{allrows}" fill="none" stroke="{sheen}" stroke-width=".5" opacity=".6"/>')
                if night or daylight < 0.15:
                    level = min(range(len(PATTERN_LEVELS)), key=lambda i: abs(PATTERN_LEVELS[i] - share))
                    warm = "#ffd58a" if b["kind"] == "H" else ("#ffe6b8" if "E8" in b["codes"] else "#f4e3c0")
                    width = num(floor_px * (0.42 if m["style"] == "punched" else 0.48), 2)
                    for v, segs in rows.items():
                        parts.append(f'<path class="w{level}{v}" d="{"".join(segs)}" fill="none" stroke="{warm}" stroke-width="{width}"/>')
                    if brnd.random() < 0.5:
                        parts.append(f'<path class="lamp w{min(4, level + 1)}{brnd.randrange(3)}" style="animation-duration:{brnd.uniform(40, 150):.0f}s;animation-delay:{-brnd.uniform(0, 150):.0f}s" '
                                     f'd="{brnd.choice(frames)}" fill="none" stroke="{warm}" stroke-width="{width}"/>')
            roof = tone(m["roof"], 1.0)
            edge = mix(roof, "#ffffff", 0.12) if night else mix(roof, "#000000", 0.14)
            if b["key"] == "R1":
                cx, cy = sum(x for x, _ in poly_m) / len(poly_m), sum(y for _, y in poly_m) / len(poly_m)
                apex = cam(cx, cy, h + 9)
                faces = []
                for (x1, y1), (x2, y2) in zip(poly_m, poly_m[1:] + poly_m[:1]):
                    run = math.hypot(x2 - x1, y2 - y1)
                    k = 0.35 + 0.65 * max(0.0, (y2 - y1) / run * sun_dir[0] - (x2 - x1) / run * sun_dir[1])
                    faces.append((cam.depth((x1 + x2) / 2, (y1 + y2) / 2), f'<polygon points="{pts([cam(x1, y1, h), cam(x2, y2, h), apex])}" fill="{tone(m["roof"], k)}" stroke="{edge}" stroke-width=".3"/>'))
                parts += [f for _, f in sorted(faces, key=lambda f: -f[0])]
            else:
                parts.append(f'<polygon points="{pts(cam(x, y, h) for x, y in poly_m)}" fill="{roof}" stroke="{edge}" stroke-width=".4"/>')
                if "E8" in b["codes"]:
                    point = next(p for p in DATA["points"] if p["code"] == "E8")
                    parts.append(f'<polygon points="{pts(cam(x, y, h + 0.2) for x, y in circle(point["x"], point["y"], 13, 16))}" fill="{tone("#9cc3dc", 1)}"/>')
            objects.append((max(cam.depth(x, y) for x, y in poly_m), "".join(parts)))
        css.append("@keyframes lamp{0%,72%{opacity:1}73%,100%{opacity:.05}}.lamp{animation:lamp steps(1) infinite}" + window_patterns(random.Random(sky.seed ^ hour)))

        tree_c, tree_hi = (tone("#3e6b39", 0.8), tone("#6a9a4c", 0.9)) if not night else ("#0c1511", "#101c15")
        for i, r in enumerate((1.9, 2.4, 3.0)):
            defs.append(f'<g id="t{i}"><ellipse cx="1.4" cy="5.2" rx="{r}" ry="{num(r * 0.42)}" fill="#0e1a10" opacity="{".22" if not night else ".3"}"/>'
                        f'<circle r="{r}" fill="{tree_c}"/><circle cx="{num(-r * 0.3)}" cy="{num(-r * 0.3)}" r="{num(r * 0.55)}" fill="{tree_hi}"/></g>')
        spots = []
        for r in roads:
            for (x1, y1), (x2, y2) in zip(r["line"], r["line"][1:]):
                seg = math.hypot(x2 - x1, y2 - y1)
                for i in range(int(seg // 20)):
                    t = (i + land.random()) / max(1, seg // 20)
                    side = land.choice([-1, 1]) * 9 / seg
                    spots.append((x1 + (x2 - x1) * t - (y2 - y1) * side, y1 + (y2 - y1) * t + (x2 - x1) * side))
        land.shuffle(spots)
        boxes = [(min(x for x, _ in b["poly"]) - 7, max(x for x, _ in b["poly"]) + 7, min(y for _, y in b["poly"]) - 7, max(y for _, y in b["poly"]) + 7) for b in BUILDINGS]
        placed = 0
        for x, y in spots:
            if placed >= 150:
                break
            if any(x0 < x < x1 and y0 < y < y1 for x0, x1, y0, y1 in boxes):
                continue
            cx, cy = cam(x, y, 5)
            objects.append((cam.depth(x, y), f'<use href="#t{land.randrange(3)}" x="{num(cx)}" y="{num(cy)}"/>'))
            placed += 1
        body += [part for _, part in sorted(objects, key=lambda o: -o[0])]

        if not night and sky.cloud > 0.15:
            defs.append('<radialGradient id="cs"><stop offset="0" stop-color="#0c1a10" stop-opacity=".22"/><stop offset="1" stop-color="#0c1a10" stop-opacity="0"/></radialGradient>')
            period = max(90, 600 - sky.wind * 15)
            for _ in range(2 + round(sky.cloud * 3)):
                cy, rx = rnd.uniform(edge_y + 20, H - 60), rnd.uniform(110, 190)
                body.append(f'<g class="cshadow" style="--a:{num(W + rx)}px;--b:{num(-rx)}px;animation-duration:{period:.0f}s;animation-delay:{-rnd.uniform(0, period):.0f}s">'
                            f'<ellipse cy="{num(cy)}" rx="{num(rx)}" ry="{num(rx * 0.32)}" fill="url(#cs)"/></g>')
            css.append("@keyframes cshadow{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}.cshadow{animation:cshadow linear infinite}")

        mains = sorted((r["line"] for r in roads if r["main"]), key=lambda l: -length(l))
        if mains:
            bus = ('<rect x="-3.6" y="-3.8" width="7.2" height="3" rx=".9" fill="#f2f4f5"/><rect x="-3" y="-3.3" width="6" height=".9" fill="#4c7fb0"/>' if not night
                   else '<rect x="-3.6" y="-3.8" width="7.2" height="3" rx=".9" fill="#2a313c"/><rect x="-3" y="-3.3" width="6" height=".9" fill="#ffe0a0"/><circle cx="3.8" cy="-1.6" r="1.8" fill="#fff2c8" opacity=".5"/>')
            body.append(f'<g>{bus}<animateMotion dur="{length(mains[0]) / 9:.0f}s" repeatCount="indefinite" keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(cam(x, y) for x, y in mains[0])}"/></g>')
            if night:
                for i, line in enumerate(mains[1:3]):
                    body.append(f'<g><circle r=".9" fill="#fff4d0"/><circle cx="1.6" r=".9" fill="#fff4d0"/>'
                                f'<animateMotion dur="{length(line) / 13:.0f}s" begin="-{i * 7}s" repeatCount="indefinite" path="{path_d(cam(x, y) for x, y in line)}"/></g>')
        if 7 <= hour < 23:
            walkers = []
            for i, line in enumerate(sorted(paths, key=lambda l: -length(l))[:8]):
                if length(line) < 40:
                    continue
                colour = ["#f0b37a", "#8fb3e8", "#f3efe6", "#e07a6e"][i % 4] if not night else "#cdd6e0"
                walkers.append(f'<circle r=".85" fill="{colour}"><animateMotion dur="{length(line) / 1.3:.0f}s" begin="-{land.uniform(0, 60):.0f}s" repeatCount="indefinite" '
                               f'keyPoints="0;1;0" keyTimes="0;.5;1" calcMode="linear" path="{path_d(cam(x, y) for x, y in line)}"/></circle>')
            body.append("".join(walkers))

        if pin:
            if pin == "dorms":
                (px_m, py_m), z, tag = DATA["dorm_centre"], FLOORS["H"] * FLOOR_M, "Dorms"
            else:
                point = next(p for p in DATA["points"] if p["code"] == pin)
                px_m, py_m, tag = point["x"], point["y"], pin
                home = next((b for b in BUILDINGS if pin in b["codes"]), None)
                z = (home["floors"] if home else 6) * FLOOR_M + (9 if pin == "R1" else 0)
            sx, sy = cam(px_m, py_m, z)
            body.append(
                f'<g transform="translate({num(sx)} {num(sy)})">'
                f'<ellipse class="ring" rx="10" ry="3.6" fill="none" stroke="{PIN}" stroke-width="1.1"/><ellipse rx="2.8" ry="1.1" fill="#000" opacity=".35"/>'
                f'<g class="bob"><path d="M0,-1C-2,-5.4 -5.6,-8 -5.6,-11.6A5.6,5.6 0 1 1 5.6,-11.6C5.6,-8 2,-5.4 0,-1Z" fill="{PIN}" stroke="#ffffff" stroke-width=".6"/><circle cy="-11.6" r="2.1" fill="#fff"/>'
                f'<g transform="translate(0 -23)"><rect x="{num(-len(tag) * 2.7 - 4.5)}" y="-6" width="{num(len(tag) * 5.4 + 9)}" height="9.6" rx="4.8" fill="#0d1117" opacity=".82"/>'
                f'<text y="1.1" text-anchor="middle" font-family="{hero.GMONO}" font-size="6.8" letter-spacing=".6" fill="#ffffff">{tag}</text></g></g></g>')
            css.append("@keyframes ring{0%{transform:scale(.3);opacity:.9}100%{transform:scale(1.6);opacity:0}}.ring{transform-box:fill-box;transform-origin:center;animation:ring 2.4s ease-out infinite}"
                       "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.6px)}}.bob{animation:bob 2.4s ease-in-out infinite}")
        defs.append('<linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05070b" stop-opacity="0"/><stop offset="1" stop-color="#05070b" stop-opacity=".6"/></linearGradient>')
        body.append(f'<rect y="{H - 66}" width="{W}" height="66" fill="url(#scrim)"/>')
        body.append(f'<text x="{W - 12}" y="{H - 6}" text-anchor="end" font-family="{hero.GMONO}" font-size="5.5" fill="#ffffff" opacity=".3">map © OpenStreetMap</text>')
        return defs, body, css
    return draw


def campus_hero(s, theme):
    """DGIST's own sky and weather always light the campus; the caption says where Mushfique is."""
    loc = s["location"]
    campus = loc.get("campus") or {}
    pin = campus.get("code") or ("dorms" if campus.get("zone") == "dorms" else None)
    if loc.get("dgist") or campus:
        label, snap = "DGIST" + (f" · {'DORMS' if pin == 'dorms' else pin}" if pin else ""), s
    else:
        w = s.get("weather") or {}
        label = f"Away · {loc['city']}" + (f" {round(w['temperature_2m'])}°C" if w.get("temperature_2m") is not None else "")
        snap = dict(s, location=DGIST_LOC, weather=s.get("weather_dgist") or w, air=s.get("air_dgist") or s.get("air"))
    return hero.scene(snap, theme, W=W, H=H, HORIZON=HORIZON, foreground=foreground(pin), label=label)
