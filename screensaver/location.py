"""Decide where the "Student at DGIST" strip shows, at city level, and write it to a state file.

Sources, in order:
1. A phone report sent as workflow_dispatch inputs (CITY and COUNTRY, or LAT and LON).
2. The last phone report, while it is less than three days old.
3. The GitHub profile's location field, if it names a place outside Korea.
4. DGIST.

Only a city name and that city's own centre coordinates are stored. Coordinates from a phone are
rounded to 0.1 degree before any lookup.
"""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "mushfique-dgist-readme/1.0 (github.com/mushfique-dgist)"}
PHONE_TTL = timedelta(days=3)
DGIST = {
    "city": "Daegu", "country": "South Korea", "country_code": "KR", "lat": 35.6965, "lon": 128.4560,
    "tz": "Asia/Seoul", "population": 2_400_000, "elevation": 60, "dgist": True,
}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def km_between(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371 * math.acos(max(-1.0, min(1.0, c)))


def geocode(name, country_code="", country_name=""):
    q = {"name": name, "count": 10, "language": "en", "format": "json"}
    if len(country_code) == 2:
        q["countryCode"] = country_code.upper()
    hits = get_json("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(q)).get("results") or []
    if country_name:
        want = country_name.lower()
        hits = [g for g in hits if want in g.get("country", "").lower() or want == g.get("country_code", "").lower()]
    if not hits:
        return None
    g = hits[0]
    return {
        "city": g["name"][:40], "country": g.get("country", "")[:40], "country_code": g.get("country_code", ""),
        "lat": round(g["latitude"], 3), "lon": round(g["longitude"], 3), "tz": g.get("timezone", "UTC"),
        "population": g.get("population") or 0, "elevation": g.get("elevation") or 0, "dgist": False,
    }


def reverse(lat, lon):
    q = {"lat": round(lat, 1), "lon": round(lon, 1), "format": "jsonv2", "zoom": 10, "accept-language": "en"}
    a = get_json("https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(q)).get("address", {})
    city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county") or a.get("state")
    return city, a.get("country_code", "")


def at_dgist(loc):
    return km_between((loc["lat"], loc["lon"]), (DGIST["lat"], DGIST["lon"])) < 40


def campus_spot(lat, lon):
    """A position on campus as {"code": "E3"} for academic buildings or {"zone": "dorms"} anywhere near the dorms."""
    import json as _json
    from pathlib import Path as _Path
    data = _json.loads((_Path(__file__).with_name("campus.json")).read_text(encoding="utf-8"))
    lat0, lng0 = data["origin"]
    x, y = (lon - lng0) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 110540
    if not (-540 < x < 550 and -470 < y < 500):
        return None
    dx, dy = data["dorm_centre"]
    dorm = any(b["kind"] == "H" and inside((x, y), b["poly"]) for b in data["buildings"]) or math.hypot(x - dx, y - dy) < 170
    if dorm:
        return {"zone": "dorms"}
    for b in data["buildings"]:
        if b["codes"] and b["kind"] != "H" and inside((x, y), b["poly"]):
            pts = [p for p in data["points"] if p["code"] in b["codes"]]
            return {"code": min(pts, key=lambda p: math.hypot(p["x"] - x, p["y"] - y))["code"]}
    near = min((p for p in data["points"] if p["code"] and not p["code"].startswith("H")), key=lambda p: math.hypot(p["x"] - x, p["y"] - y))
    return {"code": near["code"]} if math.hypot(near["x"] - x, near["y"] - y) < 60 else {"zone": "campus"}


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


PRECISE_TTL = timedelta(hours=6)
ROUGH_M = 75  # a fix less sure than this places no building pin


def from_precise(value, now):
    """LOC holds "lat,lon,unix-seconds[,accuracy-m]" from the phone. Only the building code or the city ever leaves this function."""
    fields = [v.strip() for v in value.split(",")]
    lat, lon = float(fields[0]), float(fields[1])
    if len(fields) > 2 and now - datetime.fromtimestamp(float(fields[2]), timezone.utc) > PRECISE_TTL:
        return None
    spot = campus_spot(lat, lon)
    if spot and "code" in spot and len(fields) > 3 and float(fields[3] or 0) > ROUGH_M:
        spot = {"zone": "campus"}
    if spot:
        return {**DGIST, "campus": spot}
    return from_report("", "", round(lat, 1), round(lon, 1))


def from_report(city, country, lat, lon):
    if city:
        loc = geocode(city, country)
    elif lat and lon:
        name, cc = reverse(round(float(lat), 1), round(float(lon), 1))
        loc = geocode(name, cc) if name else None
    else:
        return None
    if loc and at_dgist(loc):
        loc = dict(DGIST)
    return loc


def from_profile(user):
    """Use the profile's location field only when it reads "City, Country" and the country matches."""
    field = (get_json(f"https://api.github.com/users/{user}").get("location") or "").strip()
    if "," not in field or any(k in field.lower() for k in ("korea", "daegu", "dgist")):
        return None
    city, country = field.split(",", 1)
    loc = geocode(city.strip(), country_name=country.strip())
    if not loc or loc["country_code"] == "KR":
        return None
    return loc


def resolve(current, env, now):
    precise = env.get("LOC", "").strip()
    report = from_precise(precise, now) if precise else None
    report = report or from_report(env.get("CITY", "").strip(), env.get("COUNTRY", "").strip(), env.get("LAT", "").strip(), env.get("LON", "").strip())
    if report:
        return {**report, "source": "phone", "reported": now.isoformat()}
    if current.get("source") == "phone" and now - datetime.fromisoformat(current["reported"]) < PHONE_TTL:
        return current
    try:
        profile = from_profile(env.get("GH_USER", "mushfique-dgist"))
    except Exception as e:
        print(f"profile lookup failed: {e!r}")
        profile = None
    if profile:
        return {**profile, "source": "profile"}
    return {**DGIST, "source": "default"}


def main():
    path = sys.argv[1]
    try:
        current = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        current = {}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        loc = resolve(current, os.environ, now)
    except Exception as e:
        print(f"location lookup failed, keeping the last one: {e!r}")
        loc = current or {**DGIST, "source": "default"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(loc, f, indent=1, ensure_ascii=False)
    print(f"location: {loc['city']}, {loc['country']} ({loc['source']})")


if __name__ == "__main__":
    main()
