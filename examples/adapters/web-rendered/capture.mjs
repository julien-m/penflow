/** Optional external Playwright runner; the Penflow package never imports this file. */
import { writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { captureRenderedDocument } from "./dom-capture.mjs";

const [url, output, widthValue, heightValue, moduleName = "playwright", executablePath] = process.argv.slice(2);
const width = Number(widthValue);
const height = Number(heightValue);
if (!url || !output || !Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
	throw new Error("Usage: node capture.mjs <url> <output.json> <width> <height> [playwright-module-or-entry] [browser-executable]");
}
const requireFromCaller = createRequire(pathToFileURL(resolve("package.json")));
const modulePath = requireFromCaller.resolve(moduleName);
// The caller selects its existing runner installation; no browser is downloaded.
const imported = await import(pathToFileURL(modulePath).href);
const { chromium } = imported.default ?? imported;
const browser = await chromium.launch({ executablePath, headless: true });
try {
	const page = await browser.newPage({ viewport: { width, height } });
	page.setDefaultTimeout(10000);
	await page.goto(url, { waitUntil: "load", timeout: 10000 });
	await page.evaluate(async () => {
		let timer;
		try {
			await Promise.race([
				Promise.all([document.fonts.ready, ...Array.from(document.images).map((image) => image.decode())]),
				new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("Font/image measurement readiness timed out")), 10000); }),
			]);
		} finally {
			clearTimeout(timer);
		}
	});
	const actual = await page.evaluate(captureRenderedDocument);
	actual.capture = { browser: browser.version(), observed_at: new Date().toISOString() };
	await writeFile(output, `${JSON.stringify(actual, null, 2)}\n`);
	process.stdout.write(`${JSON.stringify({ output, screens: actual.screens.length })}\n`);
} finally {
	await browser.close();
}
