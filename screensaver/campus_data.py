"""Turn OpenStreetMap ways and DGIST's official building points into campus.json (local metres).

Run by hand when the campus changes:
  python campus_data.py <osm-buildings.json> <osm-ground.json> <dgist-points.json> <osm-outline.json>
Inputs are Overpass `out tags geom` dumps and DGIST's Cyber Campus Tour points.
Map data © OpenStreetMap contributors (ODbL).
"""
import json
import math
import sys
from pathlib import Path

LAT0, LNG0 = 35.7040, 128.4578
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540

# Buildings OpenStreetMap does not have yet: official point, width x depth in metres, floors.
MISSING = {"R5": (56, 32, 6), "R6": (64, 40, 4), "H501": (70, 18, 8), "S1": (72, 46, 3)}
FLOORS = {"E": 6, "R": 6, "H": 9, "S": 3}


def xy(lat, lng):
    return round((lng - LNG0) * KX, 1), round((lat - LAT0) * KY, 1)


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def area(poly):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1])) / 2


def ccw(poly):
    return poly if area(poly) > 0 else poly[::-1]


def main(bfile, gfile, pfile, ofile):
    points = [dict(p, x=xy(p["lat"], p["lng"])[0], y=xy(p["lat"], p["lng"])[1]) for p in json.loads(Path(pfile).read_text(encoding="utf-8"))["points"]]
    buildings = []
    for e in json.loads(Path(bfile).read_text(encoding="utf-8"))["elements"]:
        poly = ccw([xy(g["lat"], g["lon"]) for g in e["geometry"]][:-1])
        t = e["tags"]
        codes = [p["code"] for p in points if p["code"] and inside((p["x"], p["y"]), poly)]
        if not codes:
            cx, cy = sum(x for x, _ in poly) / len(poly), sum(y for _, y in poly) / len(poly)
            near = min((p for p in points if p["code"]), key=lambda p: math.hypot(p["x"] - cx, p["y"] - cy))
            if math.hypot(near["x"] - cx, near["y"] - cy) < 35:
                codes = [near["code"]]
        kind = "H" if t.get("building") == "dormitory" else (codes[0][0] if codes else "O")
        levels = t.get("building:levels", "")
        floors = int(levels) if levels.isdigit() else FLOORS.get(kind, 4)
        buildings.append({"poly": poly, "codes": codes, "kind": kind, "floors": floors})
    for code, (w, d, floors) in MISSING.items():
        p = next(p for p in points if p["code"] == code)
        poly = [(p["x"] - w / 2, p["y"] - d / 2), (p["x"] + w / 2, p["y"] - d / 2), (p["x"] + w / 2, p["y"] + d / 2), (p["x"] - w / 2, p["y"] + d / 2)]
        buildings.append({"poly": [(round(a, 1), round(b, 1)) for a, b in poly], "codes": [code], "kind": code[0], "floors": floors, "approx": True})

    ground = {"roads": [], "paths": [], "water": [], "green": [], "pitch": [], "parking": []}
    for e in json.loads(Path(gfile).read_text(encoding="utf-8"))["elements"]:
        t, line = e["tags"], [xy(g["lat"], g["lon"]) for g in e["geometry"]]
        hw = t.get("highway")
        if hw in ("tertiary", "tertiary_link", "secondary", "primary", "unclassified", "residential", "service"):
            ground["roads"].append({"line": line, "main": hw.startswith(("tertiary", "secondary", "primary"))})
        elif hw in ("footway", "path", "pedestrian", "track", "steps"):
            ground["paths"].append(line)
        elif t.get("natural") == "water":
            ground["water"].append(line[:-1])
        elif t.get("leisure") in ("park", "garden", "playground") or t.get("natural") in ("wood", "scrub", "grassland") or t.get("landuse") in ("grass", "forest", "recreation_ground"):
            ground["green"].append(line[:-1])
        elif t.get("leisure") in ("pitch", "stadium", "sports_centre", "track"):
            ground["pitch"].append({"poly": line[:-1], "sport": t.get("sport", ""), "kind": t.get("leisure")})
        elif t.get("amenity") == "parking":
            ground["parking"].append(line[:-1])
    dorms = [b for b in buildings if b["kind"] == "H" and not b.get("approx")]
    dorm_centre = (round(sum(sum(x for x, _ in b["poly"]) / len(b["poly"]) for b in dorms) / len(dorms), 1),
                   round(sum(sum(y for _, y in b["poly"]) / len(b["poly"]) for b in dorms) / len(dorms), 1))
    outline = [xy(g["lat"], g["lon"]) for g in json.loads(Path(ofile).read_text(encoding="utf-8"))["elements"][0]["geometry"]][:-1]
    out = {"origin": [LAT0, LNG0], "buildings": buildings, "ground": ground, "points": points, "dorm_centre": dorm_centre, "outline": outline,
           "attribution": "Map data © OpenStreetMap contributors (ODbL); building codes and points from DGIST"}
    Path(__file__).with_name("campus.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    named = sum(1 for b in buildings if b["codes"])
    print(f"{len(buildings)} buildings ({named} with codes), {sum(len(v) for v in ground.values())} ground features, dorm centre {dorm_centre}")
    for b in buildings:
        if b["codes"]:
            print(" ", ",".join(b["codes"]), b["kind"], b["floors"], "floors", "approx" if b.get("approx") else "osm", f"{abs(area(b['poly'])):.0f} m2")


if __name__ == "__main__":
    main(*sys.argv[1:5])
