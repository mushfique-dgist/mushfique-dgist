// node render.mjs <spec.json> <out.png> <overlay.json>
// Bundles scene.js, renders it once in headless Chrome, and writes the frame plus the projected overlay anchors.
// With spec.buffers set, it also writes <out>-albedo.png, -normal.png, -depth.png and -id.png beside the frame.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const [specPath, outPng, outOverlay] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(specPath, "utf8"));

const bundle = await build({ entryPoints: [join(here, "scene.js")], bundle: true, format: "iife", write: false, minify: true, logLevel: "error" });
const chrome = process.env.CHROME_PATH || (process.platform === "win32" ? "C:/Program Files/Google/Chrome/Application/chrome.exe" : "/usr/bin/google-chrome");
const gl = process.env.CAMPUS_GL || "swiftshader";
const browser = await chromium.launch({
  executablePath: chrome,
  args: [`--use-angle=${gl}`, "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"],
});
const page = await browser.newPage({ viewport: { width: spec.width, height: spec.height } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await page.setContent("<!doctype html><body style='margin:0;background:#000'></body>");
await page.addScriptTag({ content: bundle.outputFiles[0].text });
const t0 = Date.now();
const result = await page.evaluate((s) => window.renderCampus(s), spec);
const ms = Date.now() - t0;
await browser.close();
if (errors.length) console.error("page errors:", errors.slice(0, 5));
for (const [name, url] of Object.entries(result.images)) {
  writeFileSync(name === "beauty" ? outPng : outPng.replace(/\.png$/, `-${name}.png`), Buffer.from(url.split(",")[1], "base64"));
}
writeFileSync(outOverlay, JSON.stringify(result.overlay));
console.log(`rendered ${spec.width}x${spec.height} in ${ms} ms with ${gl}`);
