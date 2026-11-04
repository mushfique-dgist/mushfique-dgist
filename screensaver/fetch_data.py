"""Fetch the live numbers the screensaver shows into <state>/snapshot.json.

Every source is free and keyless. A source that fails keeps its value from the previous snapshot,
so one flaky API never blanks a scene.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = {"User-Agent": "mushfique-dgist-readme/1.0 (github.com/mushfique-dgist)"}


def get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8")


def voyager(now, loc):
    q = {
        "format": "json", "COMMAND": "'-31'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'500@399'", "START_TIME": f"'{now:%Y-%m-%d %H:%M}'",
        "STOP_TIME": f"'{now + timedelta(minutes=10):%Y-%m-%d %H:%M}'", "STEP_SIZE": "'10m'", "QUANTITIES": "'20'",
    }
    res = json.loads(get("https://ssd.jpl.nasa.gov/api/horizons.api?" + urllib.parse.urlencode(q)))["result"]
    row = res.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()[0]
    delta_au, deldot = map(float, row.split()[-2:])
    km = delta_au * 149_597_870.7
    return {"km": km, "km_s": deldot, "light_s": km / 299_792.458, "at": now.isoformat()}


def quakes(now, loc):
    feed = json.loads(get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"))
    rows = [{"mag": round(f["properties"]["mag"], 1), "place": f["properties"]["place"] or "", "t": f["properties"]["time"] / 1000}
            for f in feed["features"] if f["properties"]["mag"] is not None]
    return {"events": sorted(rows, key=lambda r: r["t"]), "at": now.isoformat()}


def kp(now, loc):
    last = json.loads(get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"))[-1]
    return {"kp": float(last.get("estimated_kp", last.get("kp_index"))), "time": last["time_tag"], "at": now.isoformat()}


def weather(now, loc):
    q = {
        "latitude": loc["lat"], "longitude": loc["lon"], "timezone": loc.get("tz") or "auto", "forecast_days": 1,
        "current": "temperature_2m,weather_code,cloud_cover,precipitation,rain,snowfall,is_day,wind_speed_10m",
        "daily": "sunrise,sunset",
    }
    w = json.loads(get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)))
    return {**w["current"], "utc_offset_seconds": w["utc_offset_seconds"], "tz_abbr": w.get("timezone_abbreviation", ""),
            "sunrise": w["daily"]["sunrise"][0], "sunset": w["daily"]["sunset"][0], "at": now.isoformat()}


def air(now, loc):
    q = {"latitude": loc["lat"], "longitude": loc["lon"], "current": "us_aqi,pm2_5,pm10", "timezone": loc.get("tz") or "auto"}
    a = json.loads(get("https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode(q)))["current"]
    return {"us_aqi": a.get("us_aqi"), "pm2_5": a.get("pm2_5"), "pm10": a.get("pm10"), "at": now.isoformat()}


def arxiv(now, loc):
    q = {"search_query": "cat:cs.LG", "sortBy": "submittedDate", "sortOrder": "descending", "max_results": 14}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(get("http://export.arxiv.org/api/query?" + urllib.parse.urlencode(q)))
    papers = [{"title": re.sub(r"\s+", " ", e.find("a:title", ns).text).strip(), "id": e.find("a:id", ns).text.rsplit("/", 1)[-1]}
              for e in root.findall("a:entry", ns)]
    if not papers:
        raise ValueError("arXiv returned no entries")
    return {"papers": papers, "at": now.isoformat()}


SOURCES = {"voyager": voyager, "quakes": quakes, "kp": kp, "weather": weather, "air": air, "arxiv": arxiv}


def main():
    state = Path(sys.argv[1])
    snap_path = state / "snapshot.json"
    loc = json.loads((state / "location.json").read_text(encoding="utf-8"))
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        snap = {}
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    moved = snap.get("location", {}).get("city") != loc["city"]
    for name, fn in SOURCES.items():
        try:
            snap[name] = fn(now, loc)
            print(f"ok   {name}")
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
            if moved and name in ("weather", "air"):
                snap.pop(name, None)
    if not loc.get("dgist"):
        from location import DGIST
        for name, fn in (("weather_dgist", weather), ("air_dgist", air)):
            try:
                snap[name] = fn(now, DGIST)
            except Exception as e:
                print(f"FAIL {name}: {e!r}")
    snap["location"] = loc
    snap["at"] = now.isoformat()
    snap_path.write_text(json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
