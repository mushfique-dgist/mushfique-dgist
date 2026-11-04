// OwnTracks (HTTP mode) posts the phone's position here. The exact position goes into the repository's private LOC
// variable as "lat,lon,unix,accuracy"; the workflow turns it into a building code, "dorms" or a city before anything is
// published. The workflow is asked to redraw only when the phone moved, or when the last reading had expired.
import { timingSafeEqual } from "node:crypto";

const REPO = "mushfique-dgist/mushfique-dgist";
const MOVED_M = 40;
const EXPIRED_S = 6 * 3600;

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
  const tst = Number(msg.tst) || Math.floor(Date.now() / 1000);

  const prev = await github("/actions/variables/LOC").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [plat, plon, ptst] = (prev?.value || "").split(",").map(Number);
  if (Number.isFinite(ptst) && ptst > tst) return res.status(200).json([]); // a queued older fix arriving late

  const value = [msg.lat.toFixed(6), msg.lon.toFixed(6), tst, Math.round(Number(msg.acc) || 0)].join(",");
  const saved = await github("/actions/variables/LOC", { method: "PATCH", body: JSON.stringify({ name: "LOC", value }) });
  if (!saved.ok) return res.status(502).json([]);

  const moved = !Number.isFinite(plat) || metres(plat, plon, msg.lat, msg.lon) > MOVED_M || tst - ptst > EXPIRED_S;
  if (moved) await github("/actions/workflows/screensaver.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: "main" }) }).catch(() => null);
  return res.status(200).json([]);
}
