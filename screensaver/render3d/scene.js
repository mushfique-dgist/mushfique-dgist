// Renders DGIST as a lit miniature. Called from render.mjs in headless Chrome as window.renderCampus(spec).
// World units are metres: x east, y north, z up. three.js is y-up, so world (x, y, z) maps to (x, z, -y).
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { HorizontalTiltShiftShader } from "three/addons/shaders/HorizontalTiltShiftShader.js";
import { VerticalTiltShiftShader } from "three/addons/shaders/VerticalTiltShiftShader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

const V = (x, y, z = 0) => new THREE.Vector3(x, z, -y);

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function inside(px, py, poly) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [x1, y1] = poly[i], [x2, y2] = poly[j];
    if ((y1 > py) !== (y2 > py) && px < x1 + ((py - y1) * (x2 - x1)) / (y2 - y1)) hit = !hit;
  }
  return hit;
}

function distToSegments(px, py, lines) {
  let best = Infinity;
  for (const line of lines) {
    for (let i = 0; i + 1 < line.length; i++) {
      const [x1, y1] = line[i], [x2, y2] = line[i + 1];
      const dx = x2 - x1, dy = y2 - y1, len2 = dx * dx + dy * dy || 1e-9;
      const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
      best = Math.min(best, Math.hypot(px - x1 - t * dx, py - y1 - t * dy));
    }
  }
  return best;
}

// Smooth value noise for patchy forest colour.
function noise2(seed) {
  const r = rng(seed), n = 64, g = Array.from({ length: n * n }, r);
  const at = (i, j) => g[((j % n + n) % n) * n + ((i % n + n) % n)];
  return (x, y) => {
    const i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    return (at(i, j) * (1 - sx) + at(i + 1, j) * sx) * (1 - sy) + (at(i, j + 1) * (1 - sx) + at(i + 1, j + 1) * sx) * sy;
  };
}

function canvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return c;
}

function texture(c, repeat = [1, 1], srgb = true) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat[0], repeat[1]);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 16;
  return t;
}

function canvasTexture(w, h, draw, repeat) {
  const c = canvas(w, h);
  draw(c.getContext("2d"), w, h);
  return texture(c, repeat);
}

// One window bay (3.2 m wide) by one floor (3.6 m tall) per texture tile.
const BAY = 3.2, FLOOR = 3.6;

function facade(style, m) {
  return canvasTexture(64, 72, (g, w, h) => {
    g.fillStyle = m.wall; g.fillRect(0, 0, w, h);
    if (style === "band") {
      const grd = g.createLinearGradient(0, 20, 0, 60);
      grd.addColorStop(0, m.glassHi); grd.addColorStop(1, m.glass);
      g.fillStyle = grd; g.fillRect(0, 22, w, 38);
      g.fillStyle = m.mullion; g.fillRect(w - (m.fin || 3), m.fin ? 0 : 22, m.fin || 3, m.fin ? h : 38);
    } else if (style === "punched") {
      g.fillStyle = m.frame; g.fillRect(12, 14, 40, 44);
      const grd = g.createLinearGradient(0, 18, 0, 54);
      grd.addColorStop(0, m.glassHi); grd.addColorStop(1, m.glass);
      g.fillStyle = grd; g.fillRect(16, 18, 32, 36);
    } else {
      const grd = g.createLinearGradient(0, 0, w * 0.4, h);
      grd.addColorStop(0, m.glassHi); grd.addColorStop(1, m.glass);
      g.fillStyle = grd; g.fillRect(0, 0, w, h);
      g.fillStyle = m.mullion; g.fillRect(0, 0, w, 4); g.fillRect(w - 3, 0, 3, h);
    }
  }, [1 / BAY, 1 / FLOOR]);
}

function litMap(style, share, seed) {
  const r = rng(seed), cells = 8;
  return canvasTexture(64 * cells, 72 * cells, (g) => {
    g.fillStyle = "#000"; g.fillRect(0, 0, 64 * cells, 72 * cells);
    for (let i = 0; i < cells; i++) for (let j = 0; j < cells; j++) {
      if (r() > share) continue;
      const warm = r() < 0.8;
      g.fillStyle = warm ? `hsl(${34 + r() * 10},${85 + r() * 10}%,${58 + r() * 14}%)` : `hsl(205,45%,${76 + r() * 10}%)`;
      const x = i * 64, y = j * 72;
      if (style === "band") g.fillRect(x, y + 24, 64, 34);
      else if (style === "punched") g.fillRect(x + 16, y + 18, 32, 36);
      else g.fillRect(x + 2, y + 4, 60, 66);
    }
  }, [1 / (BAY * cells), 1 / (FLOOR * cells)]);
}

function roofTex(colour, green) {
  return canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = colour; g.fillRect(0, 0, w, h);
    const r = rng(9);
    if (green) {
      for (let i = 0; i < 140; i++) { g.fillStyle = `rgba(${70 + r() * 40},${115 + r() * 45},${50 + r() * 30},.55)`; g.beginPath(); g.arc(r() * w, r() * h, 3 + r() * 7, 0, 7); g.fill(); }
      g.fillStyle = "rgba(225,220,205,.9)"; g.fillRect(0, 60, w, 6); g.fillRect(60, 0, 6, h);
    } else {
      g.fillStyle = "rgba(0,0,0,.05)";
      for (let i = 0; i < w; i += 16) g.fillRect(i, 0, 1, h);
      for (let i = 0; i < 12; i++) { g.fillStyle = `rgba(0,0,0,${0.02 + r() * 0.03})`; g.fillRect(r() * w, r() * h, 10 + r() * 30, 10 + r() * 30); }
    }
  }, [1 / 32, 1 / 32]);
}

function extrude(poly, z0, h) {
  const shape = new THREE.Shape(poly.map(([x, y]) => new THREE.Vector2(x, y)));
  const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false });
  geo.rotateX(-Math.PI / 2);
  geo.translate(0, z0, 0);
  return geo;
}

function flat(poly, y, map) {
  const shape = new THREE.Shape(poly.map(([x, yy]) => new THREE.Vector2(x, yy)));
  const g = new THREE.ShapeGeometry(shape);
  if (map) {
    const pos = g.attributes.position, uv = g.attributes.uv;
    for (let k = 0; k < pos.count; k++) uv.setXY(k, (pos.getX(k) - map.X0) / (map.X1 - map.X0), (pos.getY(k) - map.Y0) / (map.Y1 - map.Y0));
  }
  g.rotateX(-Math.PI / 2);
  g.translate(0, y, 0);
  return g;
}

// Seasonal palettes for the canopy and the lawns (DGIST is in Daegu: ginkgo gold and maple rust in November).
function season(month, day) {
  const d = month * 100 + day;
  const ever = ["#2a5128", "#305a2c", "#376331", "#3f6c36", "#2d5629"];
  if (d >= 1012 && d <= 1128) return {
    name: "autumn", lawn: "#88b452", lawnAlt: "#92bb58", ever, decid: ["#5f7a34", "#71803a", "#867a3a", "#8c6a36", "#6b7436"], decidShare: 0.28,
    street: ["#cda63d", "#bfa244", "#93a043", "#6f913e", "#c47a37"],
  };
  if (d >= 1129 || d <= 310) return {
    name: "winter", lawn: "#a7a174", lawnAlt: "#b0a97b", ever, decid: ["#6f6658", "#7b7062", "#655c51"], decidShare: 0.35,
    street: ["#7d7365", "#887d6e"],
  };
  if (d <= 510) return {
    name: "spring", lawn: "#8cc05a", lawnAlt: "#96c662", ever, decid: ["#6ea24a", "#7cae52", "#5f9645"], decidShare: 0.4,
    street: d >= 328 && d <= 414 ? ["#f2c9d4", "#f6d8e0", "#ecbccb"] : ["#7db651", "#8ac05a"],
  };
  return { name: "summer", lawn: "#82b84e", lawnAlt: "#8bbf55", ever, decid: ["#3f6e33", "#4a7a38", "#568640"], decidShare: 0.4, street: ["#4f8a3c", "#5b9443", "#467f37"] };
}

const COLOURS = {
  floor: "#2b4627", paving: "#e8e4da", plaza: "#dedad0", asphalt: "#8e9399", kerb: "#f2f0ea", lane: "#fbfaf6",
  parking: "#9a9ea4", stall: "#f4f4f0", water: "#3d7ea4", waterRim: "#9cc4d8", track: "#b85a42", field: "#4f9a46", fieldAlt: "#58a54d",
  tennis: "#3f8a6c", court: "#c39a63",
};

window.renderCampus = async function (spec) {
  const { width, height, sky, terrain, outline, buildings, ground, pins } = spec;
  const ss = spec.supersample || 2;
  const night = sky.salt < -4, dusk = sky.salt >= -4 && sky.salt < 10, overcast = sky.cloud;
  const seasonal = season(spec.month, spec.day);
  const W = width * ss, H = height * ss;
  const cv = canvas(W, H);
  document.body.appendChild(cv);
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: false, preserveDrawingBuffer: true, powerPreference: "high-performance" });
  renderer.setSize(W, H, false);
  renderer.setPixelRatio(1);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = night ? 1.0 : 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const [zen, upper, lower, hor] = sky.stops.map((c) => new THREE.Color(c));
  const haze = hor.clone().lerp(upper, 0.25).lerp(new THREE.Color(night ? "#0a0f1c" : "#dfe8ef"), night ? 0.5 : 0.3);
  scene.background = haze;

  // Environment for glass and sheen: the live sky on a sphere.
  const envScene = new THREE.Scene();
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(100, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: { top: { value: zen }, mid: { value: hor }, bottom: { value: new THREE.Color(night ? "#05070b" : "#4d5a40") } },
    vertexShader: "varying vec3 p; void main(){ p = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }",
    fragmentShader: "uniform vec3 top, mid, bottom; varying vec3 p; void main(){ float h = normalize(p).y; vec3 c = h > 0. ? mix(mid, top, pow(h, .5)) : mix(mid, bottom, pow(-h, .35)); gl_FragColor = vec4(c, 1.); }",
  })));
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(envScene, 0.02).texture;
  scene.environmentIntensity = night ? 0.18 : dusk ? 0.55 : 0.7;

  // Camera: a telephoto view from the south, like DGIST's own campus map, fitted to the buildings.
  const cam = spec.camera;
  const camera = new THREE.PerspectiveCamera(cam.fov, width / height, 100, 12000);
  const az = cam.azimuth * Math.PI / 180, el = cam.elevation * Math.PI / 180;
  const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
  const corners = [];
  for (const b of buildings) {
    const pts = b.poly || [[b.cx - b.r, b.cy - b.r], [b.cx + b.r, b.cy + b.r], [b.cx - b.r, b.cy + b.r], [b.cx + b.r, b.cy - b.r]];
    for (const [x, y] of pts) corners.push(V(x, y, b.z0), V(x, y, b.z0 + b.h));
  }
  for (const p of ground.pitch) for (const [x, y] of p.poly) corners.push(V(x, y, 0));
  const box3 = new THREE.Box3().setFromPoints(corners);
  const target = box3.getCenter(new THREE.Vector3()).setY(0);
  const place = (d) => {
    camera.position.copy(target).addScaledVector(dir, d);
    camera.lookAt(target);
    camera.updateMatrixWorld();
    let x0 = 1, x1 = -1, y0 = 1, y1 = -1;
    for (const c of corners) {
      const v = c.clone().project(camera);
      x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y);
    }
    return { x0, x1, y0, y1 };
  };
  let d = 3000;
  for (let pass = 0; pass < 3; pass++) {
    let lo = 300, hi = 9000;
    for (let i = 0; i < 40; i++) {
      d = (lo + hi) / 2;
      const b = place(d);
      const fill = Math.max((b.x1 - b.x0) / 2 / cam.fillX, (b.y1 - b.y0) / 2 / cam.fillY);
      if (fill > 1) lo = d; else hi = d;
    }
    const b = place(d);
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    const halfH = Math.tan(cam.fov * Math.PI / 360) * d, halfW = halfH * width / height;
    const shift = right.multiplyScalar(((b.x0 + b.x1) / 2) * halfW).add(up.multiplyScalar(((b.y0 + b.y1) / 2 + (cam.liftY || 0)) * halfH));
    target.add(shift);
    target.y = 0;
  }
  place(d);
  scene.fog = new THREE.Fog(haze, d * 0.96, d * 2.1);

  // Light: the real sun (or the moon at night), softened by cloud cover.
  const toDir = (alt, azi) => new THREE.Vector3(Math.sin(azi * Math.PI / 180) * Math.cos(alt * Math.PI / 180), Math.sin(alt * Math.PI / 180), -Math.cos(azi * Math.PI / 180) * Math.cos(alt * Math.PI / 180));
  const sunDir = toDir(Math.max(sky.salt, 4), sky.saz), moonDir = toDir(Math.max(sky.malt, 25), sky.maz);
  const warm = Math.max(0, Math.min(1, (sky.salt - 2) / 22));
  const sunColour = new THREE.Color("#ff9a5a").lerp(new THREE.Color("#fff4e6"), warm);
  const hemi = new THREE.HemisphereLight(
    night ? "#5a70b0" : upper.clone().lerp(new THREE.Color("#ffffff"), 0.45),
    night ? "#141a24" : "#5b6a44",
    night ? 1.5 : dusk ? 1.0 + overcast * 0.4 : 1.1 + overcast * overcast * 0.8,
  );
  scene.add(hemi);
  const key = new THREE.DirectionalLight(night ? "#a9bcff" : sunColour, night ? 0.9 : (dusk ? 2.4 : 3.0) * (1 - 0.6 * overcast * overcast));
  key.position.copy(target).addScaledVector(night ? moonDir : sunDir, 3000);
  key.target.position.copy(target);
  key.castShadow = true;
  key.shadow.mapSize.set(8192, 8192);
  Object.assign(key.shadow.camera, { left: -1100, right: 1100, top: 1100, bottom: -1100, near: 500, far: 7000 });
  key.shadow.bias = -0.0003;
  key.shadow.normalBias = 0.5;
  key.shadow.radius = 2;
  scene.add(key, key.target);

  // Ground: one painted texture for the campus, a coarser one for the hills around it.
  const { step, x0: TX0, y0: TY0, nx, ny, h: heights } = terrain;
  const TX1 = TX0 + (nx - 1) * step, TY1 = TY0 + (ny - 1) * step;
  const base = spec.base;
  const heightAt = (x, y) => {
    const gx = (x - TX0) / step, gy = (y - TY0) / step;
    const i = Math.max(0, Math.min(nx - 2, Math.floor(gx))), j = Math.max(0, Math.min(ny - 2, Math.floor(gy)));
    const fx = Math.min(1, Math.max(0, gx - i)), fy = Math.min(1, Math.max(0, gy - j)), Hh = (a, b) => heights[b * nx + a] - base;
    return (Hh(i, j) * (1 - fx) + Hh(i + 1, j) * fx) * (1 - fy) + (Hh(i, j + 1) * (1 - fx) + Hh(i + 1, j + 1) * fx) * fy;
  };
  const outlineLines = [[...outline, outline[0]]];
  const groundZ = (x, y) => {
    if (inside(x, y, outline)) return 0;
    const dd = distToSegments(x, y, outlineLines);
    const t = Math.min(1, dd / 180), s = t * t * (3 - 2 * t);
    return Math.max(0, heightAt(x, y)) * s * 1.35;
  };

  const ox = outline.map((p) => p[0]), oy = outline.map((p) => p[1]);
  const C = { X0: Math.min(...ox) - 30, X1: Math.max(...ox) + 30, Y0: Math.min(...oy) - 30, Y1: Math.max(...oy) + 30 };
  C.k = 4096 / Math.max(C.X1 - C.X0, C.Y1 - C.Y0);
  const T = { X0: TX0, X1: TX1, Y0: TY0, Y1: TY1, k: 2048 / (TX1 - TX0) };
  const at = (m) => (x, y) => [(x - m.X0) * m.k, (m.Y1 - y) * m.k];
  const trace = (g, P, line, close) => {
    g.beginPath();
    line.forEach(([x, y], i) => { const [u, v] = P(x, y); i ? g.lineTo(u, v) : g.moveTo(u, v); });
    if (close) g.closePath();
  };
  const stroke = (g, P, k, line, w, colour, close = false, dash = null) => {
    trace(g, P, line, close);
    g.lineWidth = w * k; g.strokeStyle = colour; g.lineJoin = "round"; g.lineCap = "round";
    g.setLineDash(dash ? dash.map((v) => v * k) : []);
    g.stroke();
    g.setLineDash([]);
  };
  const fill = (g, P, poly, colour) => { trace(g, P, poly, true); g.fillStyle = colour; g.fill(); };
  const roadW = (rd) => (rd.main ? 10 : 6.5);
  const footprints = buildings.map((b) => b.poly || Array.from({ length: 24 }, (_, i) => [b.cx + b.r * Math.cos(i * Math.PI / 12), b.cy + b.r * b.squash * Math.sin(i * Math.PI / 12)]));

  // Lawn reach: grass grows out from the buildings and roads, inside the campus line.
  const lawnLayer = (m, w, h) => {
    const c = canvas(w, h), g = c.getContext("2d"), P = at(m);
    trace(g, P, outline, true); g.save(); g.clip();
    for (const rd of ground.roads) stroke(g, P, m.k, rd.line, 96, "#fff");
    for (const fp of footprints) { stroke(g, P, m.k, fp, 90, "#fff", true); fill(g, P, fp, "#fff"); }
    for (const p of ground.pitch) { stroke(g, P, m.k, p.poly, 30, "#fff", true); fill(g, P, p.poly, "#fff"); }
    for (const p of ground.parking) { stroke(g, P, m.k, p, 20, "#fff", true); fill(g, P, p, "#fff"); }
    g.restore();
    return c;
  };
  const hard = (g, m, colours) => {
    const P = at(m), k = m.k;
    for (const p of ground.water) { fill(g, P, p, colours.water); stroke(g, P, k, p, 1.6, colours.waterRim, true); }
    for (const p of ground.pitch) {
      const cx = p.poly.reduce((a, q) => a + q[0], 0) / p.poly.length, cy = p.poly.reduce((a, q) => a + q[1], 0) / p.poly.length;
      if (p.sport === "soccer") {
        fill(g, P, p.poly, colours.track);
        const inner = p.poly.map(([x, y]) => [cx + (x - cx) * 0.8, cy + (y - cy) * 0.72]);
        fill(g, P, inner, colours.field);
        stroke(g, P, k, inner, 0.5, colours.stall, true);
      } else if ((p.sport || "").includes("tennis")) {
        fill(g, P, p.poly, colours.tennis); stroke(g, P, k, p.poly, 0.5, colours.stall, true);
      } else {
        fill(g, P, p.poly, colours.court); stroke(g, P, k, p.poly, 0.5, colours.stall, true);
      }
    }
    for (const p of ground.parking) {
      fill(g, P, p, colours.parking);
      let best = 0, ang = 0;
      for (let i = 0; i < p.length; i++) {
        const [x1, y1] = p[i], [x2, y2] = p[(i + 1) % p.length], l = Math.hypot(x2 - x1, y2 - y1);
        if (l > best) { best = l; ang = Math.atan2(y2 - y1, x2 - x1); }
      }
      const cx = p.reduce((a, q) => a + q[0], 0) / p.length, cy = p.reduce((a, q) => a + q[1], 0) / p.length;
      trace(g, P, p, true); g.save(); g.clip();
      g.strokeStyle = colours.stall; g.lineWidth = 0.18 * k;
      const ux = Math.cos(ang), uy = Math.sin(ang), vx = -uy, vy = ux;
      for (let s = -150; s < 150; s += 2.6) {
        for (const row of [-3.2, 3.2]) {
          const [a, b] = P(cx + ux * s + vx * row, cy + uy * s + vy * row), [c2, d2] = P(cx + ux * s + vx * (row * 2.4), cy + uy * s + vy * (row * 2.4));
          g.beginPath(); g.moveTo(a, b); g.lineTo(c2, d2); g.stroke();
        }
      }
      g.restore();
    }
    for (const fp of footprints) { stroke(g, P, k, fp, 9, colours.plaza, true); fill(g, P, fp, colours.plaza); }
    for (const p of ground.paths) stroke(g, P, k, p, 3, colours.paving);
    for (const rd of ground.roads) stroke(g, P, k, rd.line, roadW(rd) + 1.6, colours.kerb);
    for (const rd of ground.roads) stroke(g, P, k, rd.line, roadW(rd), colours.asphalt);
    for (const rd of ground.roads) if (rd.main) stroke(g, P, k, rd.line, 0.22, colours.lane, false, [3, 5]);
  };
  const grain = (g, w, h, amount, seed) => {
    const r = rng(seed), img = g.getImageData(0, 0, w, h), px = img.data;
    for (let i = 0; i < px.length; i += 4) { const n = (r() - 0.5) * amount; px[i] += n; px[i + 1] += n; px[i + 2] += n; }
    g.putImageData(img, 0, 0);
  };
  const paintGround = (m, w, h, seed) => {
    const c = canvas(w, h), g = c.getContext("2d");
    g.fillStyle = COLOURS.floor; g.fillRect(0, 0, w, h);
    const lawn = lawnLayer(m, w, h), lg = lawn.getContext("2d");
    lg.globalCompositeOperation = "source-in";
    const grd = lg.createLinearGradient(0, 0, w, h);
    grd.addColorStop(0, seasonal.lawn); grd.addColorStop(0.5, seasonal.lawnAlt); grd.addColorStop(1, seasonal.lawn);
    lg.fillStyle = grd; lg.fillRect(0, 0, w, h);
    g.filter = `blur(${Math.max(1, m.k * 1.2)}px)`; g.drawImage(lawn, 0, 0); g.filter = "none";
    hard(g, m, COLOURS);
    grain(g, w, h, 10, seed);
    return c;
  };

  const campusCanvas = paintGround(C, Math.round((C.X1 - C.X0) * C.k), Math.round((C.Y1 - C.Y0) * C.k), 5);
  const hillCanvas = paintGround(T, 2048, 2048, 6);

  // Night: pools of warm light under the street lamps.
  let campusGlow = null, hillGlow = null;
  const lamps = [];
  if (night || sky.salt < 3) {
    for (const rd of ground.roads) {
      for (let i = 0; i + 1 < rd.line.length; i++) {
        const [x1, y1] = rd.line[i], [x2, y2] = rd.line[i + 1], seg = Math.hypot(x2 - x1, y2 - y1);
        for (let t = 0; t < seg; t += rd.main ? 32 : 40) {
          const side = (lamps.length % 2 ? 1 : -1) * (roadW(rd) / 2 + 1.2);
          lamps.push([x1 + (x2 - x1) * t / seg - (y2 - y1) / seg * side, y1 + (y2 - y1) * t / seg + (x2 - x1) / seg * side, 17]);
        }
      }
    }
    for (const p of ground.paths) {
      for (let i = 0; i + 1 < p.length; i++) {
        const [x1, y1] = p[i], [x2, y2] = p[i + 1], seg = Math.hypot(x2 - x1, y2 - y1);
        for (let t = 0; t < seg; t += 26) lamps.push([x1 + (x2 - x1) * t / seg, y1 + (y2 - y1) * t / seg, 8]);
      }
    }
    const glow = (m, w, h) => {
      const c = canvas(w, h), g = c.getContext("2d"), P = at(m);
      g.fillStyle = "#000"; g.fillRect(0, 0, w, h);
      g.globalCompositeOperation = "lighter";
      for (const [x, y, r] of lamps) {
        const [u, v] = P(x, y), rr = r * m.k;
        const grd = g.createRadialGradient(u, v, 0, u, v, rr);
        grd.addColorStop(0, "rgba(255,200,130,.32)"); grd.addColorStop(0.5, "rgba(255,175,100,.12)"); grd.addColorStop(1, "rgba(255,150,70,0)");
        g.fillStyle = grd; g.fillRect(u - rr, v - rr, rr * 2, rr * 2);
      }
      for (const fp of footprints) { stroke(g, P, m.k, fp, 5, "rgba(255,200,140,.18)", true); }
      return c;
    };
    campusGlow = texture(glow(C, campusCanvas.width, campusCanvas.height));
    hillGlow = texture(glow(T, 2048, 2048));
  }

  const nightTint = new THREE.Color(night ? "#7f8fb4" : "#ffffff");
  const groundMat = (map, glowMap) => new THREE.MeshStandardMaterial({
    map, color: nightTint, roughness: 0.95, metalness: 0,
    emissive: glowMap ? new THREE.Color("#ffffff") : new THREE.Color("#000000"), emissiveMap: glowMap, emissiveIntensity: glowMap ? (night ? 1.6 : 0.6) : 0,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2,
  });
  const campusTex = texture(campusCanvas), hillTex = texture(hillCanvas);
  campusTex.wrapS = campusTex.wrapT = hillTex.wrapS = hillTex.wrapT = THREE.ClampToEdgeWrapping;
  const campusFloor = new THREE.Mesh(flat(outline, 0.05, C), groundMat(campusTex, campusGlow));
  campusFloor.receiveShadow = true;
  scene.add(campusFloor);

  const tSeg = (nx - 1) * 4;
  const tgeo = new THREE.PlaneGeometry(TX1 - TX0, TY1 - TY0, tSeg, tSeg);
  tgeo.rotateX(-Math.PI / 2);
  tgeo.translate((TX0 + TX1) / 2, 0, -(TY0 + TY1) / 2);
  const tpos = tgeo.attributes.position;
  for (let k = 0; k < tpos.count; k++) tpos.setY(k, groundZ(tpos.getX(k), -tpos.getZ(k)) - 0.3);
  tgeo.computeVertexNormals();
  const land = new THREE.Mesh(tgeo, new THREE.MeshStandardMaterial({ map: hillTex, color: nightTint, roughness: 1, emissive: hillGlow ? new THREE.Color("#fff") : new THREE.Color("#000"), emissiveMap: hillGlow, emissiveIntensity: hillGlow ? (night ? 1.6 : 0.6) : 0 }));
  land.receiveShadow = true;
  scene.add(land);

  // Buildings.
  const tex = {};
  const rooftop = [];
  const br = rng(31);
  for (const [bi, b] of buildings.entries()) {
    const m = b.material;
    const bid = [128, (bi + 1) >> 8, (bi + 1) & 255];
    const keyName = `${b.style}|${m.wall}|${m.glass}`;
    tex[keyName] = tex[keyName] || facade(b.style, m);
    const emissive = night || sky.salt < 3 ? litMap(b.style, b.share, b.seed) : null;
    const wall = new THREE.MeshStandardMaterial({
      map: tex[keyName], roughness: b.style === "glass" ? 0.12 : 0.62, metalness: b.style === "glass" ? 0.4 : 0.0,
      envMapIntensity: b.style === "glass" ? 1.4 : 0.6,
      emissive: emissive ? new THREE.Color("#ffffff") : new THREE.Color("#000000"), emissiveMap: emissive, emissiveIntensity: emissive ? (night ? 1.35 : 0.9) : 0,
    });
    const roof = new THREE.MeshStandardMaterial({ map: roofTex(m.roof, b.greenRoof), roughness: 0.85 });
    let mesh;
    if (b.shape === "oval") {
      const g = new THREE.CylinderGeometry(b.r, b.r, b.h, 64, 1, false);
      g.scale(1, 1, b.squash);
      const pos = g.attributes.position, uv = g.attributes.uv;
      for (let k = 0; k < uv.count; k++) uv.setXY(k, uv.getX(k) * 2 * Math.PI * b.r, pos.getY(k) + b.h / 2);
      g.translate(b.cx, b.z0 + b.h / 2, -b.cy);
      mesh = new THREE.Mesh(g, [wall, roof, roof]);
      const rim = new THREE.Mesh(new THREE.TorusGeometry(b.r, 0.5, 6, 64), new THREE.MeshStandardMaterial({ color: "#eef2f4", roughness: 0.5 }));
      rim.rotation.x = Math.PI / 2; rim.scale.set(1, b.squash, 1); rim.position.set(b.cx, b.z0 + b.h, -b.cy);
      rim.userData.id = bid;
      scene.add(rim);
    } else {
      mesh = new THREE.Mesh(extrude(b.poly, b.z0, b.h), [roof, wall]);
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(extrude(b.poly, b.z0, b.h + 0.05), 25),
        new THREE.LineBasicMaterial({ color: night ? "#2a3244" : "#ffffff", transparent: true, opacity: night ? 0.4 : 0.55 }));
      scene.add(edge);
      // Rooftop plant: a few small units so roofs read at miniature scale.
      const xs = b.poly.map((p) => p[0]), ys = b.poly.map((p) => p[1]);
      const area = Math.abs(b.poly.reduce((a, [x1, y1], i) => { const [x2, y2] = b.poly[(i + 1) % b.poly.length]; return a + x1 * y2 - x2 * y1; }, 0)) / 2;
      const units = b.hipped ? 0 : Math.min(6, Math.floor(area / 500));
      for (let u = 0, tries = 0; u < units && tries < 60; tries++) {
        const x = Math.min(...xs) + br() * (Math.max(...xs) - Math.min(...xs)), y = Math.min(...ys) + br() * (Math.max(...ys) - Math.min(...ys));
        if (!inside(x, y, b.poly) || distToSegments(x, y, [[...b.poly, b.poly[0]]]) < 4) continue;
        rooftop.push([x, y, b.z0 + b.h, 2 + br() * 3, 2 + br() * 2.5, 1.2 + br() * 1.2]);
        u++;
      }
    }
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.userData.id = bid;
    scene.add(mesh);
    if (b.hipped) {
      const cx = b.poly.reduce((a, q) => a + q[0], 0) / b.poly.length, cy = b.poly.reduce((a, q) => a + q[1], 0) / b.poly.length;
      const pos = [];
      for (let i = 0; i < b.poly.length; i++) {
        const [x1, y1] = b.poly[i], [x2, y2] = b.poly[(i + 1) % b.poly.length];
        pos.push(x1, b.z0 + b.h, -y1, x2, b.z0 + b.h, -y2, cx, b.z0 + b.h + b.hipped, -cy);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.computeVertexNormals();
      const hm = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: m.roof, roughness: 0.3, metalness: 0.55, side: THREE.DoubleSide }));
      hm.castShadow = true; hm.receiveShadow = true; hm.userData.id = bid;
      scene.add(hm);
    }
  }
  if (rooftop.length) {
    const unit = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0), new THREE.MeshStandardMaterial({ color: "#d9dcdf", roughness: 0.6 }), rooftop.length);
    const mt = new THREE.Matrix4();
    rooftop.forEach(([x, y, z, w, dd, h], i) => { unit.setMatrixAt(i, mt.compose(V(x, y, z), new THREE.Quaternion(), new THREE.Vector3(w, h, dd))); });
    unit.castShadow = true; unit.receiveShadow = true; unit.userData.id = [192, 0, 0];
    scene.add(unit);
  }

  // Trees: a continuous canopy on the hills, ginkgo and cherry rows along campus roads.
  const maskOf = (m, w, h) => {
    const c = canvas(w, h), g = c.getContext("2d");
    g.fillStyle = "#000"; g.fillRect(0, 0, w, h);
    g.drawImage(lawnLayer(m, w, h), 0, 0);
    hard(g, m, Object.fromEntries(Object.keys(COLOURS).map((k) => [k, "#fff"])));
    for (const rd of ground.roads) stroke(g, at(m), m.k, rd.line, roadW(rd) + 9, "#fff");
    return g.getImageData(0, 0, w, h).data;
  };
  const TM = { ...T, k: 1024 / (TX1 - TX0) }, tmask = maskOf(TM, 1024, 1024);
  const CM = { ...C, k: 1 }, cw = Math.round(C.X1 - C.X0), ch = Math.round(C.Y1 - C.Y0), cmask = maskOf(CM, cw, ch);
  const open = (x, y) => {
    if (x > C.X0 && x < C.X1 && y > C.Y0 && y < C.Y1) {
      const u = Math.floor(x - C.X0), v = Math.floor(C.Y1 - y);
      return cmask[(v * cw + u) * 4] < 60;
    }
    const u = Math.floor((x - TX0) * TM.k), v = Math.floor((TY1 - y) * TM.k);
    return u >= 0 && v >= 0 && u < 1024 && v < 1024 && tmask[(v * 1024 + u) * 4] < 60;
  };
  const visible = (x, y, z) => { const v = V(x, y, z).project(camera); return Math.abs(v.x) < 1.06 && v.y > -1.08 && v.y < 1.12; };
  const fr = rng(77), patch = noise2(5), patch2 = noise2(11);
  const trees = [];
  const spacing = 8.5;
  for (let gx = TX0; gx < TX1; gx += spacing) for (let gy = TY0; gy < TY1; gy += spacing) {
    const x = gx + (fr() - 0.5) * spacing * 0.9, y = gy + (fr() - 0.5) * spacing * 0.9;
    const z = groundZ(x, y);
    if (!visible(x, y, z) || !open(x, y)) continue;
    const decid = fr() < seasonal.decidShare * (0.35 + 1.3 * patch(x / 90, y / 90));
    const pal = decid ? seasonal.decid : seasonal.ever;
    const tone = Math.min(pal.length - 1, Math.floor((patch2(x / 60, y / 60) * 0.8 + fr() * 0.2) * pal.length));
    const rad = 4.8 + fr() * 2.4;
    trees.push([x, y, z, rad, rad * (decid ? 0.95 : 1.1), pal[tone], 0.9 + fr() * 0.2]);
  }
  for (const rd of ground.roads) {
    for (let i = 0; i + 1 < rd.line.length; i++) {
      const [x1, y1] = rd.line[i], [x2, y2] = rd.line[i + 1], seg = Math.hypot(x2 - x1, y2 - y1);
      for (let t = 4; t < seg; t += 10) {
        for (const side of [-1, 1]) {
          if (fr() < 0.22) continue;
          const off = (roadW(rd) / 2 + 4.4 + (fr() - 0.5) * 2) * side;
          const x = x1 + (x2 - x1) * t / seg - (y2 - y1) / seg * off, y = y1 + (y2 - y1) * t / seg + (x2 - x1) / seg * off;
          if (!inside(x, y, outline) || footprints.some((fp) => inside(x, y, fp)) || distToSegments(x, y, ground.roads.map((r2) => r2.line)) < roadW(rd) / 2 + 2) continue;
          const rad = 3 + fr() * 1.2;
          trees.push([x, y, 0, rad, rad * 1.2, seasonal.street[Math.floor(fr() * seasonal.street.length)], 0.92 + fr() * 0.16]);
        }
      }
    }
  }
  const hardMask = (() => {
    const c = canvas(cw, ch), g = c.getContext("2d"), P = at(CM);
    g.fillStyle = "#000"; g.fillRect(0, 0, cw, ch);
    hard(g, CM, Object.fromEntries(Object.keys(COLOURS).map((k) => [k, "#fff"])));
    for (const fp of footprints) stroke(g, P, 1, fp, 16, "#fff", true);
    for (const rd of ground.roads) stroke(g, P, 1, rd.line, roadW(rd) + 6, "#fff");
    return g.getImageData(0, 0, cw, ch).data;
  })();
  const grove = noise2(23);
  for (let gx = C.X0; gx < C.X1; gx += 8) for (let gy = C.Y0; gy < C.Y1; gy += 8) {
    const x = gx + (fr() - 0.5) * 7, y = gy + (fr() - 0.5) * 7;
    const u = Math.floor(x - C.X0), v = Math.floor(C.Y1 - y);
    if (u < 0 || v < 0 || u >= cw || v >= ch || cmask[(v * cw + u) * 4] < 60 || hardMask[(v * cw + u) * 4] > 60) continue;
    if (!inside(x, y, outline) || grove(x / 55, y / 55) < 0.6) continue;
    const rad = 3.2 + fr() * 1.8;
    trees.push([x, y, 0, rad, rad * 1.15, (fr() < 0.5 ? seasonal.street : seasonal.ever)[Math.floor(fr() * 3) % 3], 0.9 + fr() * 0.2]);
  }
  const crown = new THREE.IcosahedronGeometry(1, 2);
  const cpos = crown.attributes.position, cn = crown.attributes.normal;
  for (let k = 0; k < cpos.count; k++) { const v = new THREE.Vector3(cpos.getX(k), cpos.getY(k), cpos.getZ(k)).normalize(); cn.setXYZ(k, v.x, v.y, v.z); }
  crown.translate(0, 0.85, 0);
  const L = (night ? moonDir : sunDir).clone().normalize();
  const slopeLight = (x, y, z) => {
    if (z <= 0) return 1;
    const dx = (groundZ(x + 8, y) - groundZ(x - 8, y)) / 16, dy = (groundZ(x, y + 8) - groundZ(x, y - 8)) / 16;
    const n = new THREE.Vector3(-dx, 1, dy).normalize();
    return Math.max(0.55, Math.min(1.3, n.dot(L) / Math.max(0.2, L.y)));
  };
  const forest = new THREE.InstancedMesh(crown, new THREE.MeshStandardMaterial({ roughness: 0.92, envMapIntensity: 0.4 }), trees.length);
  const mtx = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion();
  trees.forEach(([x, y, z, rad, ht, colour, shade], i) => {
    forest.setMatrixAt(i, mtx.compose(V(x, y, z), q, new THREE.Vector3(rad, ht, rad)));
    forest.setColorAt(i, col.set(colour).multiplyScalar(shade * slopeLight(x, y, z)).multiply(nightTint));
  });
  forest.castShadow = true; forest.receiveShadow = true; forest.userData.id = [64, 0, 0];
  scene.add(forest);

  // Composite: ambient occlusion, a little bloom at night, and the tilt-shift that makes it a miniature.
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
  composer.addPass(new RenderPass(scene, camera));
  const ao = new GTAOPass(scene, camera, W, H);
  ao.updateGtaoMaterial({ radius: 9, distanceExponent: 1.6, thickness: 6, scale: 1.0, samples: 16 });
  ao.blendIntensity = night ? 0.7 : 0.95;
  composer.addPass(ao);
  if (night || sky.salt < 3) composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), night ? 0.42 : 0.25, 0.3, night ? 0.82 : 0.9));
  if (!spec.buffers) {
    const hT = new ShaderPass(HorizontalTiltShiftShader), vT = new ShaderPass(VerticalTiltShiftShader);
    hT.uniforms.h.value = (cam.blur || 1.6) / W; vT.uniforms.v.value = (cam.blur || 1.6) / H;
    hT.uniforms.r.value = vT.uniforms.r.value = cam.focus;
    composer.addPass(hT); composer.addPass(vT);
  }
  composer.addPass(new OutputPass());
  composer.render();
  const grab = () => cv.toDataURL("image/png");
  const images = { beauty: grab() };

  // Buffers for the art styles: unlit colour, view normals, linear depth and object ids, all without fog or lines.
  if (spec.buffers) {
    scene.fog = null;
    scene.traverse((o) => { if (o.isLineSegments) o.visible = false; });
    const meshes = [];
    scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
    const unlit = (m) => new THREE.MeshBasicMaterial({ map: m.map || null, color: m.color ? m.color.clone() : new THREE.Color("#ffffff"), side: m.side, toneMapped: false });
    for (const o of meshes) o.material = Array.isArray(o.material) ? o.material.map(unlit) : unlit(o.material);
    renderer.setRenderTarget(null);
    renderer.render(scene, camera);
    images.albedo = grab();

    scene.background = new THREE.Color("#000000");
    const probe = (mode) => new THREE.ShaderMaterial({
      uniforms: { near: { value: camera.near }, far: { value: camera.far }, mode: { value: mode } },
      vertexShader: `#include <common>
        varying vec3 vN; varying float vD;
        void main() {
          #include <beginnormal_vertex>
          #include <defaultnormal_vertex>
          #include <begin_vertex>
          #include <project_vertex>
          vN = normalize(transformedNormal); vD = -mvPosition.z;
        }`,
      fragmentShader: `uniform float near, far; uniform int mode; varying vec3 vN; varying float vD;
        void main() {
          if (mode == 0) { gl_FragColor = vec4(normalize(vN) * 0.5 + 0.5, 1.0); return; }
          float d = clamp((vD - near) / (far - near), 0.0, 1.0) * 255.0;
          gl_FragColor = vec4(floor(d) / 255.0, fract(d), 0.0, 1.0);
        }`,
      side: THREE.DoubleSide,
    });
    scene.overrideMaterial = probe(0); renderer.render(scene, camera); images.normal = grab();
    scene.overrideMaterial = probe(1); renderer.render(scene, camera); images.depth = grab();
    scene.overrideMaterial = null;
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    for (const o of meshes) {
      const [r, g, b] = o.userData.id || [0, 0, 0];
      if (o.isInstancedMesh) o.instanceColor = null;
      o.material = new THREE.MeshBasicMaterial({ color: new THREE.Color(r / 255, g / 255, b / 255), toneMapped: false });
    }
    renderer.render(scene, camera);
    images.id = grab();
  }

  const project = (x, y, z = 0) => {
    const v = V(x, y, z).project(camera);
    return [Math.round(((v.x + 1) / 2) * width * 10) / 10, Math.round(((1 - v.y) / 2) * height * 10) / 10];
  };
  const overlay = {
    roads: ground.roads.filter((rd) => rd.main).map((rd) => rd.line.map(([x, y]) => project(x, y, groundZ(x, y) + 1))),
    paths: ground.paths.map((p) => p.map(([x, y]) => project(x, y, 0.5))),
    pins: Object.fromEntries(Object.entries(pins).map(([k, [x, y, z]]) => [k, project(x, y, z)])),
    horizon: project(target.x, -target.z + 6000, 0)[1],
    trees: trees.length,
    labels: Object.fromEntries(Object.entries(spec.labels || {}).map(([k, [x, y, z]]) => [k, project(x, y, z)])),
    near: camera.near, far: camera.far,
  };
  return { images, overlay };
};
