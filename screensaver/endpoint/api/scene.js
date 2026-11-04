// One random screensaver per page load for the README's surprise toggle: never the home view and never the
// scene this instance served last. GitHub's image proxy fetches again on each view because of no-store.
const BASE = "https://raw.githubusercontent.com/mushfique-dgist/mushfique-dgist/output/readme/";
const SCENES = ["voyager", "seismo", "aurora", "pulsar", "orbit", "people", "arxiv", "pendulum", "mystify"];
const FRESH_MS = 5 * 60 * 1000;
const cache = new Map();
let last = "";

async function load(file) {
  const hit = cache.get(file);
  if (hit && Date.now() - hit.at < FRESH_MS) return hit.body;
  const res = await fetch(BASE + file);
  if (!res.ok) {
    if (hit) return hit.body;
    throw new Error(`${file}: HTTP ${res.status}`);
  }
  const body = await res.text();
  cache.set(file, { body, at: Date.now() });
  return body;
}

export async function GET(request) {
  const theme = new URL(request.url).searchParams.get("theme") === "dark" ? "dark" : "light";
  const pool = SCENES.filter((s) => s !== last);
  const scene = pool[Math.floor(Math.random() * pool.length)];
  last = scene;
  try {
    return new Response(await load(`${scene}-${theme}.svg`), {
      headers: { "content-type": "image/svg+xml; charset=utf-8", "cache-control": "no-cache, no-store, must-revalidate, max-age=0", "x-scene": scene },
    });
  } catch {
    return Response.redirect(`${BASE}${SCENES[0]}-${theme}.svg`, 302);
  }
}
