/** External browser adapter: observations come from served DOM and real network responses. */
import fs from 'node:fs/promises';
import { observeFonts } from './font_capture.mjs';
import { snapshotDocument } from './dom_capture.mjs';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const [baseUrl, scenario, output, playwrightPath, executablePath] = process.argv.slice(2);
const startedAt = new Date().toISOString();
const module = await import(pathToFileURL(playwrightPath).href);
const { chromium } = module.default ?? module;
const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const sessionId = randomUUID();
const history = [];
const requests = [];
const screenshots = [];
await context.addInitScript({ content: `window.__pilotObserved = []; window.addEventListener('pilot:result', event => { const snapshot = (${snapshotDocument.toString()})(); snapshot.properties.payment_result = event.detail.response.outcome; window.__pilotObserved.push({ phase: 'before-ui-transition', response: event.detail.response, guard_results: event.detail.guard_results, snapshot }); });` });
await context.addInitScript({ content: `window.__pilotActions = []; window.addEventListener('click', event => { const target = event.target.closest('[data-action]'); if (target) window.__pilotActions.push({ event: event.type, is_trusted: event.isTrusted, semantic_id: target.dataset.semantic, action_id: target.dataset.action, test_id: target.dataset.testId, snapshot: (${snapshotDocument.toString()})() }); }, true);` });
page.on('framenavigated', frame => { if (frame === page.mainFrame()) history.push(frame.url()); });
page.on('request', request => requests.push({ observed_at: new Date().toISOString(), url: request.url(), method: request.method(), body: request.postData() }));

async function observe(target) {
  const fonts = await observeFonts(target);
  return { ...await target.evaluate(snapshotDocument), fonts };
}

async function screenshot(target, screen) {
  const path = output.replace(/\.json$/, `.${screen}.png`);
  await target.screenshot({ path, fullPage: true, animations: 'disabled' });
  return { path, screen_id: screen, url: target.url() };
}

try {
  const target = new URL(baseUrl);
  if (scenario === 'denied') target.searchParams.set('actor', 'visitor');
  if (scenario === 'error') target.searchParams.set('service', 'failure');
  if (scenario === 'storage_error') target.searchParams.set('service', 'storage');
  await page.goto(target.href);
  await page.waitForSelector('[data-semantic="checkout.pay"]');
  if (scenario === 'invalid') await page.locator('#amount').fill('0');
  if (scenario === 'edit') await page.locator('#amount').fill('5');
  let before = await observe(page);
  const actorId = before.properties.actor;
  if (scenario === 'save') screenshots.push(await screenshot(page, 'checkout'));
  let after;
  let network = null;
  let navigation = null;
  if (scenario === 'edit') {
    await page.locator('#amount').fill('10');
    await page.locator('#amount').blur();
    after = await observe(page);
  } else if (scenario === 'inspect') {
    after = await observe(page);
  } else if (scenario === 'back') {
    const previousUrl = page.url();
    await page.goto(new URL('details', baseUrl).href);
    await page.waitForURL('**/details');
    before = await observe(page);
    screenshots.push(await screenshot(page, 'details'));
    await page.goBack();
    after = await observe(page);
    navigation = { event: 'back', previous_url: previousUrl, history: [...history], context_id: sessionId,
      before_url: before.url, after_url: page.url(), surface_present: !page.isClosed() };
  } else if (scenario === 'close') {
    const popup = await context.newPage();
    await popup.goto(new URL('receipt', baseUrl).href);
    before = await observe(popup);
    screenshots.push(await screenshot(popup, 'receipt'));
    await popup.close();
    after = { visible: !popup.isClosed(), surface_present: context.pages().includes(popup), url: popup.isClosed() ? null : popup.url() };
    navigation = { event: 'close', context_id: sessionId, parent_open: !page.isClosed(), remaining_pages: context.pages().length };
  } else if (['invalid', 'denied'].includes(scenario)) {
    await page.getByRole('button', { name: 'Pay', exact: true }).click();
    await page.locator('output').filter({ hasText: scenario }).waitFor();
    await page.waitForLoadState('networkidle');
    after = await observe(page);
    if (requests.some(request => request.method === 'POST')) throw new Error('Rejected UI action sent a POST');
  } else {
    const awaited = page.waitForResponse(response => response.url() === `${baseUrl}payments` && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Pay', exact: true }).click();
    const response = await awaited;
    const body = await response.json();
    await page.locator('output').filter({ hasText: body.outcome }).waitFor();
    const request = response.request();
    network = { request: { url: request.url(), method: request.method(), headers: await request.allHeaders(), body: request.postDataJSON() },
      response: { observed_at: new Date().toISOString(), status: response.status(), headers: await response.allHeaders(), body } };
    after = await observe(page);
  }
  const data = { kind: 'penflow-runtime-pilot-raw', version: 1, source_kind: 'runtime-capture', scenario_id: scenario,
    session_id: sessionId, actor_id: actorId, producer_process_id: process.pid, started_at: startedAt,
    captured_at: new Date().toISOString(), browser_version: browser.version(),
    before, after, network, navigation, history, requests, screenshots,
    pre_transition: await page.evaluate(() => window.__pilotObserved), actions: await page.evaluate(() => window.__pilotActions) };
  await fs.writeFile(output, `${JSON.stringify(data, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ scenario, session_id: sessionId, output })}\n`);
} finally {
  await context.close();
  await browser.close();
}
