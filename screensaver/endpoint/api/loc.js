// OwnTracks (HTTP mode) posts the phone's position here. The exact position goes into the repository's private LOC
// variable as "lat,lon,unix,accuracy"; the workflow turns it into a building code, "dorms" or a city before anything is
// published. The workflow is asked to redraw only when the phone moved, or when the last reading had expired.
import { timingSafeEqual } from "node:crypto";

const REPO = "mushfique-dgist/mushfique-dgist";
const MOVED_M = 40;
const EXPIRED_S = 6 * 3600;
const REDRAW_S = 25 * 60;
const ROUGH_M = 75; // matches location.py: a fix worse than this places no building pin

const same = (a, b) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

function metres(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180, x = (lon2 - lon1) * r * Math.cos(((lat1 + lat2) / 2) * r), y = (lat2 - lat1) * r;
  return Math.hypot(x, y) * 6371000;
}

const github = (path, init = {}) =>
  fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${process.env.GH_TOKEN}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "dgist-location-relay" },
  });

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json([]);
  const [, password = ""] = Buffer.from((req.headers.authorization || "").replace(/^Basic\s+/i, ""), "base64").toString().split(":");
  if (!process.env.LOC_PASSWORD || !same(password, process.env.LOC_PASSWORD)) return res.status(401).json([]);

  const msg = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  if (msg._type !== "location" || typeof msg.lat !== "number" || typeof msg.lon !== "number") return res.status(200).json([]);
  const now = Math.floor(Date.now() / 1000);
  // A ping (t "p") means "still here": OwnTracks may resend the last fix with its old time, so it counts as now.
  const tst = msg.t === "p" ? now : Number(msg.tst) || now;
  console.log(`report t=${msg.t || "-"} age=${now - (Number(msg.tst) || now)}s acc=${Math.round(Number(msg.acc) || 0)}m`);

  const prev = await github("/actions/variables/LOC").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [plat, plon, ptst] = (prev?.value || "").split(",").map(Number);
  if (Number.isFinite(ptst) && ptst > tst) return res.status(200).json([]); // a queued older fix arriving late

  // Indoors a fix is often 100 m+ off. If a rough fix still overlaps the last good one, keep the good position and only
  // refresh its time, so the building pin does not blink out. A rough fix clearly elsewhere still replaces it.
  const acc = Math.round(Number(msg.acc) || 0);
  const [, , , pacc] = (prev?.value || "").split(",").map(Number);
  const keep = acc > ROUGH_M && Number.isFinite(plat) && pacc <= ROUGH_M && tst - ptst < EXPIRED_S && metres(plat, plon, msg.lat, msg.lon) <= acc + 30;
  const value = keep ? [plat.toFixed(6), plon.toFixed(6), tst, pacc].join(",") : [msg.lat.toFixed(6), msg.lon.toFixed(6), tst, acc].join(",");
  const saved = await github("/actions/variables/LOC", { method: "PATCH", body: JSON.stringify({ name: "LOC", value }) });
  if (!saved.ok) return res.status(502).json([]);

  const moved = !keep && (!Number.isFinite(plat) || metres(plat, plon, msg.lat, msg.lon) > MOVED_M || tst - ptst > EXPIRED_S);
  // GitHub's half-hourly schedule often skips runs, so a report also redraws when the last run is over 25 minutes old.
  const last = moved ? null : await github("/actions/workflows/screensaver.yml/runs?per_page=1").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const stale = !moved && (!last?.workflow_runs?.length || now - Date.parse(last.workflow_runs[0].created_at) / 1000 > REDRAW_S);
  if (moved || stale) await github("/actions/workflows/screensaver.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: "main" }) }).catch(() => null);
  return res.status(200).json([]);
}
