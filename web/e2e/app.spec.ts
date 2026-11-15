// The page against the API it talks to: every number on screen must be the API's answer for the same
// request. Expected values come from the running API, never from saved files, so the tests hold on any
// data version (the sample or the full data).
import { readFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Download, type Page } from '@playwright/test';
import type { Meta, QueryRequest, QueryResponse } from '../src/lib/types';
import { monthsToCsv } from '../src/lib/download';

let meta: Meta;

test.beforeAll(async ({ request }) => {
	const res = await request.get('/api/meta');
	expect(res.ok(), 'GET /api/meta').toBeTruthy();
	meta = await res.json();
});

// Only the app's own server: the basemap tiles and anything else external are refused, so the tests
// need no network and send nothing out.
test.beforeEach(async ({ page, baseURL }) => {
	const own = new URL(baseURL!).origin;
	await page.route('**/*', (route) => (route.request().url().startsWith(own) ? route.continue() : route.abort()));
});

async function api(request: APIRequestContext, body: QueryRequest): Promise<QueryResponse> {
	const res = await request.post('/api/query', { data: body });
	expect(res.ok(), `POST /api/query ${JSON.stringify(body)}`).toBeTruthy();
	return res.json();
}

/** What the page sends on load: the first preset over the whole series, describing the newest month. */
function initial(): QueryRequest {
	return { area: { preset: 'argentina-box' }, start: meta.series_start, end: meta.series_end, month: meta.series_end, baseline: 'median' };
}

const sentence = (page: Page) => page.locator('.answer .sentence');
const areaMeta = (page: Page) => page.locator('.area-meta');
const calendar = (page: Page) => page.locator('svg[aria-roledescription="calendar heatmap"]');
const hexText = (r: QueryResponse) =>
	`${r.area.hexagons.toLocaleString('en-US')} hexagons at level ${r.area.resolution}, ${r.area.active_hexagons.toLocaleString('en-US')} with any fire`;

async function open(page: Page) {
	await page.goto('/');
	await expect(sentence(page)).toBeVisible();
}

async function setMonth(page: Page, id: 'start' | 'end' | 'month', ym: string) {
	await page.locator(`#${id}-y`).selectOption(ym.slice(0, 4));
	await page.locator(`#${id}-m`).selectOption(String(Number(ym.slice(5))));
}

async function text(d: Download) {
	return readFile((await d.path())!, 'utf8');
}

test('loads the newest month from the API', async ({ page, request }) => {
	const r = await api(request, initial());
	await open(page);
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	await expect(areaMeta(page)).toContainText(hexText(r));
	const eyebrow = page.locator('#answer-title');
	if (meta.in_progress) {
		await expect(eyebrow).toContainText('so far');
		await expect(page.locator('.answer')).toContainText('Month in progress');
	} else {
		await expect(eyebrow).not.toContainText('so far');
	}
	await expect(calendar(page)).toBeVisible();
	await expect(calendar(page).locator('.cell')).toHaveCount(r.months.length);
});

test('every preset shows the API answer', async ({ page, request }) => {
	await open(page);
	for (const p of meta.presets) {
		const r = await api(request, { ...initial(), area: { preset: p.id } });
		await page.getByRole('button', { name: p.name }).click();
		await expect(sentence(page)).toHaveText(r.stats.sentence);
		await expect(areaMeta(page)).toContainText(`${p.name}: ${hexText(r)}`);
		await expect(page.locator('#answer-title')).toContainText(p.name);
	}
});

test('dates and baseline change the answer', async ({ page, request }) => {
	await open(page);
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await setMonth(page, 'start', '2015-01');
	await setMonth(page, 'end', '2022-12');
	await setMonth(page, 'month', '2020-08');
	const median = await api(request, { area: { preset: 'parana-delta' }, start: '2015-01', end: '2022-12', month: '2020-08', baseline: 'median' });
	await expect(sentence(page)).toHaveText(median.stats.sentence);
	await expect(page.locator('#answer-title')).toContainText('August 2020');

	await page.getByLabel('Average (mean)').check();
	const mean = await api(request, { area: { preset: 'parana-delta' }, start: '2015-01', end: '2022-12', month: '2020-08', baseline: 'mean' });
	await expect(sentence(page)).toHaveText(mean.stats.sentence);
	await expect(page.locator('.answer')).toContainText(new RegExp(`Rank\\s*${mean.stats.rank}\\s*of ${mean.stats.of}`));
});

test('a custom box runs a new search', async ({ page, request }) => {
	await open(page);
	await page.getByRole('tab', { name: 'Custom box' }).click();
	const bbox: [number, number, number, number] = [-59.5, -33.8, -58.8, -33.0];
	await page.locator('#box-minLon').fill(String(bbox[0]));
	await page.locator('#box-minLat').fill(String(bbox[1]));
	await page.locator('#box-maxLon').fill(String(bbox[2]));
	await page.locator('#box-maxLat').fill(String(bbox[3]));
	await page.getByRole('button', { name: 'Show this box' }).click();
	const r = await api(request, { ...initial(), area: { bbox } });
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	await expect(areaMeta(page)).toContainText(hexText(r));
	await expect(page.locator('#answer-title')).toContainText('Box -59.50, -33.80, -58.80, -33.00');
});

test('a circle runs a new search', async ({ page, request }) => {
	await open(page);
	await page.getByRole('tab', { name: 'Circle' }).click();
	await page.locator('#circle-lat').fill('-33.4');
	await page.locator('#circle-lon').fill('-59.2');
	await page.locator('#circle-r').fill('30');
	await page.getByRole('button', { name: 'Show this circle' }).click();
	const r = await api(request, { ...initial(), area: { point: [-59.2, -33.4], radius_km: 30 } });
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	await expect(areaMeta(page)).toContainText(hexText(r));
});

test('an invalid box is caught before any search', async ({ page }) => {
	await open(page);
	const before = await sentence(page).textContent();
	let queried = false;
	page.on('request', (req) => {
		if (req.url().endsWith('/api/query')) queried = true;
	});
	await page.getByRole('tab', { name: 'Custom box' }).click();
	await page.locator('#box-minLon').fill('-58');
	await page.locator('#box-maxLon').fill('-59');
	await page.getByRole('button', { name: 'Show this box' }).click();
	await expect(page.locator('#box-maxLon-err')).toHaveText('East (max) longitude must be greater than west (min).');
	await expect(page.locator('#box-maxLon')).toBeFocused();
	expect(queried).toBe(false);
	await expect(sentence(page)).toHaveText(before!);
});

test('downloads match the API', async ({ page, request }) => {
	await open(page);
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await setMonth(page, 'start', '2020-08');
	await setMonth(page, 'end', '2020-09');
	const body = { area: { preset: 'parana-delta' }, start: '2020-08', end: '2020-09' };
	const r = await api(request, { ...body, month: '2020-09', baseline: 'median' });
	await expect(sentence(page)).toHaveText(r.stats.sentence);

	const [monthly] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /^Download CSV/ }).click()]);
	expect(monthly.suggestedFilename()).toBe('firecal-parana-delta-2020-08_2020-09-monthly.csv');
	expect(await text(monthly)).toBe(monthsToCsv(r.months));

	const res = await request.post('/api/export.csv', { data: body });
	expect(res.ok()).toBeTruthy();
	const [hotspots] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Hotspots CSV' }).click()]);
	expect(hotspots.suggestedFilename()).toBe('firecal-parana-delta-2020-08_2020-09-hotspots.csv');
	expect(await text(hotspots)).toBe(await res.text());

	const hex = page.getByRole('button', { name: /Hexagon CSV/ });
	await expect(hex).toContainText(`${r.cells!.length.toLocaleString('en-US')} hexagons`);
	const [cells] = await Promise.all([page.waitForEvent('download'), hex.click()]);
	const rows = (await text(cells)).trim().split('\n');
	expect(rows.length - 1).toBe(r.cells!.length);
});

test('an export over the row cap shows the server message', async ({ page, request }) => {
	const body = { area: { preset: 'argentina-box' }, start: meta.series_start, end: meta.series_end };
	const res = await request.post('/api/export.csv', { data: body });
	test.skip(res.status() !== 413, 'this data fits under the export cap');
	const msg = (await res.json()).error as string;
	await open(page);
	await page.getByRole('button', { name: 'Hotspots CSV' }).click();
	await expect(page.locator('.downloads [role=alert]')).toHaveText(msg);
});

test('without the API the page says so', async ({ page }) => {
	await page.route('**/api/meta', (route) => route.fulfill({ status: 503, json: { error: 'down for maintenance' } }));
	await page.goto('/');
	await expect(page.locator('main [role=alert]')).toHaveText('Could not load firecal data: down for maintenance');
	await expect(sentence(page)).toHaveCount(0);
});

test('a failed query is reported', async ({ page }) => {
	await open(page);
	await page.route('**/api/query', (route) => route.fulfill({ status: 500, json: { error: 'boom' } }));
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await expect(page.locator('main > .notice[role=alert]')).toHaveText('The query failed: boom');
});

test('clicking a calendar month describes it', async ({ page, request }) => {
	await open(page);
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await setMonth(page, 'start', '2020-01');
	await setMonth(page, 'end', '2020-12');
	const r = await api(request, { area: { preset: 'parana-delta' }, start: '2020-01', end: '2020-12', month: '2020-12', baseline: 'median' });
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	// One cell per month in order, so August 2020 is the eighth.
	await calendar(page).locator('.cell').nth(7).click();
	const aug = await api(request, { area: { preset: 'parana-delta' }, start: '2020-01', end: '2020-12', month: '2020-08', baseline: 'median' });
	await expect(sentence(page)).toHaveText(aug.stats.sentence);
});
