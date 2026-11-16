// The page against the API it talks to: every number on screen must be the API's answer for the same
// request. Expected values come from the running API, never from saved files, so the tests hold on any
// data version (the sample or the full data).
import { readFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext, type Download, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
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

/** What the page sends on load: the first preset over the whole series, describing the newest month.
 * Both the Argentina data and the global data have a "parana-delta" preset, which the tests below use. */
function initial(): QueryRequest {
	return { area: { preset: meta.presets[0].id }, start: meta.series_start, end: meta.series_end, month: meta.series_end, baseline: 'median' };
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

/** Open one of the left panel's tabs (the page opens on Area). */
async function panel(page: Page, name: 'Area' | 'Dates' | 'Layer' | 'Data') {
	await page.getByRole('tab', { name, exact: true }).click();
}

async function setMonth(page: Page, id: 'start' | 'end' | 'month', ym: string) {
	await panel(page, 'Dates');
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
	await expect(page.locator('.answer .trend p')).toHaveText(r.stats.trend.sentence);
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

test('the time bar switches the map between the month and the range', async ({ page }) => {
	await open(page);
	await panel(page, 'Layer');
	const monthBtn = page.getByRole('button', { name: 'Selected month', exact: true });
	const rangeBtn = page.getByRole('button', { name: 'Date range', exact: true });
	const bar = page.getByRole('slider', { name: 'Month' });
	const box = (await bar.boundingBox())!;
	const y = box.y + box.height / 2;

	// Dragging across the bars sets the dates and shows the range on the map.
	await page.mouse.move(box.x + box.width * 0.3, y);
	await page.mouse.down();
	await page.mouse.move(box.x + box.width * 0.5, y, { steps: 5 });
	await page.mouse.up();
	await expect(rangeBtn).toHaveAttribute('aria-pressed', 'true');

	// Clicking a bar picks that month and shows it on the map.
	await page.mouse.click(box.x + box.width * 0.4, y);
	await expect(monthBtn).toHaveAttribute('aria-pressed', 'true');

	// Whole series is a range again.
	await page.getByRole('button', { name: 'Whole series' }).click();
	await expect(rangeBtn).toHaveAttribute('aria-pressed', 'true');

	// Arrow keys step the month.
	await bar.focus();
	await page.keyboard.press('ArrowLeft');
	await expect(monthBtn).toHaveAttribute('aria-pressed', 'true');
});

test('the season chart adds up each season', async ({ page }) => {
	await open(page);
	const sec = page.locator('section[aria-labelledby="season-cycle-title"]');
	const usualRow = () => sec.locator('table tbody tr').first().locator('td');
	const perMonth = await usualRow().allTextContents();
	await sec.getByRole('button', { name: 'So far this season' }).click();
	await expect(sec.getByRole('button', { name: 'So far this season' })).toHaveAttribute('aria-pressed', 'true');
	const soFar = await usualRow().allTextContents();
	// A running total never falls, and ends at least as high as any single month. The usual running
	// total needs seasons with all twelve months complete; the sample (a few days kept per month) has
	// none, so there it is empty throughout.
	const n = (t: string) => Number(t.replace(/[^0-9.]/g, ''));
	const known = soFar.filter((t) => t !== '–').map(n);
	expect(known.length === 0 || known.length === 12).toBe(true);
	for (let i = 1; i < known.length; i++) expect(known[i]).toBeGreaterThanOrEqual(known[i - 1]);
	if (known.length) expect(Math.max(...known)).toBeGreaterThanOrEqual(Math.max(...perMonth.filter((t) => t !== '–').map(n)));
});

test('downloads match the API', async ({ page, request }) => {
	await open(page);
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await setMonth(page, 'start', '2020-08');
	await setMonth(page, 'end', '2020-09');
	const body = { area: { preset: 'parana-delta' }, start: '2020-08', end: '2020-09' };
	const r = await api(request, { ...body, month: '2020-09', baseline: 'median' });
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	await panel(page, 'Data');

	const [monthly] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /^Download CSV/ }).click()]);
	expect(monthly.suggestedFilename()).toBe('firecal-parana-delta-2020-08_2020-09-monthly.csv');
	expect(await text(monthly)).toBe(monthsToCsv(r.months));

	const res = await request.post('/api/export.csv', { data: body });
	if (meta.export_limit == null) {
		// No hotspot file (the global data): no button, and the API refuses with a message.
		expect(res.status()).toBe(404);
		await expect(page.getByRole('button', { name: 'Hotspots CSV' })).toHaveCount(0);
		await expect(page.locator('#hotspot-note')).toContainText('not available');
	} else {
	expect(res.ok()).toBeTruthy();
	const [hotspots] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Hotspots CSV' }).click()]);
	expect(hotspots.suggestedFilename()).toBe('firecal-parana-delta-2020-08_2020-09-hotspots.csv');
	expect(await text(hotspots)).toBe(await res.text());
	}

	const hex = page.getByRole('button', { name: /Hexagon CSV/ });
	await expect(hex).toContainText(`${r.cells!.length.toLocaleString('en-US')} hexagons`);
	const [cells] = await Promise.all([page.waitForEvent('download'), hex.click()]);
	const rows = (await text(cells)).trim().split('\n');
	expect(rows.length - 1).toBe(r.cells!.length);

	// A saved chart carries its title, the area and dates, its description and its legend.
	const yearly = page.getByRole('group', { name: 'Download Yearly totals' });
	const [img] = await Promise.all([page.waitForEvent('download'), yearly.getByRole('button', { name: 'SVG' }).click()]);
	expect(img.suggestedFilename()).toBe('firecal-parana-delta-2020-08_2020-09-yearly.svg');
	const svg = await text(img);
	for (const s of ['>Yearly totals<', 'August 2020 to September 2020<', 'converted so MODIS years are on the VIIRS scale', '>Satellite record:<', '>Terra MODIS<'])
		expect(svg).toContain(s);
});

test('an export over the row cap shows the server message', async ({ page, request }) => {
	const body = { area: { preset: meta.presets[0].id }, start: meta.series_start, end: meta.series_end };
	const res = await request.post('/api/export.csv', { data: body });
	test.skip(res.status() !== 413, 'this data fits under the export cap');
	const msg = (await res.json()).error as string;
	await open(page);
	await panel(page, 'Data');
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
	await expect(page.locator('.notice[role=alert]')).toHaveText('The query failed: boom');
});

test('clicking a calendar month describes it', async ({ page, request }) => {
	await open(page);
	await page.getByRole('button', { name: 'Paraná Delta' }).click();
	await setMonth(page, 'start', '2020-01');
	await setMonth(page, 'end', '2020-12');
	const r = await api(request, { area: { preset: 'parana-delta' }, start: '2020-01', end: '2020-12', month: '2020-12', baseline: 'median' });
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	// The map shows the date range until a calendar month is clicked.
	await panel(page, 'Layer');
	await page.getByRole('button', { name: 'Date range', exact: true }).click();
	// One cell per month in order, so August 2020 is the eighth.
	await calendar(page).locator('.cell').nth(7).click();
	const aug = await api(request, { area: { preset: 'parana-delta' }, start: '2020-01', end: '2020-12', month: '2020-08', baseline: 'median' });
	await expect(sentence(page)).toHaveText(aug.stats.sentence);
	await expect(page.getByRole('button', { name: 'Selected month', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('each search names the continent whose model it used, and the methods show its numbers', async ({ page, request }) => {
	test.skip(Object.keys(meta.continents ?? {}).length < 2, 'one study area, one model');
	await open(page);
	for (const p of meta.presets) {
		const r = await api(request, { ...initial(), area: { preset: p.id } });
		await page.getByRole('button', { name: p.name }).click();
		await expect(sentence(page)).toHaveText(r.stats.sentence);
		const name = r.continent!.replace(/_/g, ' ');
		const info = meta.continents![r.continent!];
		if (r.continent === 'World') {
			await expect(areaMeta(page)).toContainText('No fire here in any year');
		} else if (!info.fitted) {
			await expect(areaMeta(page)).toContainText(`${name} (`);
			await expect(areaMeta(page)).toContainText('has no model');
		} else {
			const pct = `${(r.continent_share! * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })} %`;
			await expect(areaMeta(page)).toContainText(`Converted with the ${name} model, which holds ${pct} of this area's fire-days.`);
			// The full methods open in a dialog from the "Limits for this answer" card.
			await page.getByRole('button', { name: 'Methods and limits' }).click();
			const methods = page.getByRole('dialog', { name: 'Methods and limits' });
			await expect(methods).toBeVisible();
			await expect(methods.locator('h3', { hasText: 'How well the conversion works' })).toHaveText(`How well the conversion works: ${name}`);
			const aqua = info.validation.aqua;
			const pctCell = (n: number) => `${n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 2 })} %`;
			await expect(methods.locator('tr', { hasText: 'Aqua MODIS' })).toContainText(pctCell(aqua.whole_area_typical_error_pct));
			await page.keyboard.press('Escape');
			await expect(methods).toBeHidden();
		}
	}
});

test('a shared link opens the same search, and the address bar follows each change', async ({ page, request }) => {
	const req: QueryRequest = { area: { preset: 'parana-delta' }, start: '2010-01', end: '2015-12', month: '2012-08', baseline: 'mean' };
	const r = await api(request, req);
	await page.goto('/?preset=parana-delta&start=2010-01&end=2015-12&month=2012-08&baseline=mean');
	await expect(sentence(page)).toHaveText(r.stats.sentence);
	await setMonth(page, 'month', '2013-09');
	await expect(page).toHaveURL(/[?&]month=2013-09(&|$)/);
	await expect(page).toHaveURL(/[?&]preset=parana-delta(&|$)/);
	// A box travels as numbers.
	const box: QueryRequest = { area: { bbox: [-60, -34, -58.5, -32.5] }, start: '2019-01', end: '2021-12', month: '2020-08', baseline: 'median' };
	const rb = await api(request, box);
	await page.goto('/?bbox=-60,-34,-58.5,-32.5&start=2019-01&end=2021-12&month=2020-08');
	await expect(sentence(page)).toHaveText(rb.stats.sentence);
	// The described month may lie outside the dates shown, and the link keeps it.
	const outside: QueryRequest = { area: { preset: 'parana-delta' }, start: '2019-01', end: '2020-12', month: '2012-08', baseline: 'median' };
	const ro = await api(request, outside);
	await page.goto('/?preset=parana-delta&start=2019-01&end=2020-12&month=2012-08');
	await expect(sentence(page)).toHaveText(ro.stats.sentence);
	await expect(page).toHaveURL(/[?&]month=2012-08(&|$)/);
});

test('a link with unknown or out-of-range parts falls back to the defaults', async ({ page, request }) => {
	const r = await api(request, { ...initial(), area: { preset: meta.presets.find((p) => p.id === 'argentina-box')?.id ?? meta.presets[0].id } });
	await page.goto('/?preset=nowhere&start=1990-01&end=2999-12&month=13-2020&baseline=mode');
	await expect(sentence(page)).toHaveText(r.stats.sentence);
});

// Automated accessibility scan (axe-core) against WCAG 2.2 A and AA, on every panel tab. It finds
// only what can be checked by machine; keyboard and screen-reader use still need testing by hand.
for (const scheme of ['light', 'dark'] as const)
test(`no automated accessibility violations on any panel (${scheme})`, async ({ page }) => {
	await page.emulateMedia({ colorScheme: scheme });
	await open(page);
	const scan = async (where: string) => {
		const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
		const found = r.violations.map((v) => `${scheme} ${where}: ${v.id} (${v.impact}): ${v.help}\n    ${v.nodes.map((n) => n.target.join(' ')).slice(0, 5).join('\n    ')}`);
		expect(found, found.join('\n')).toEqual([]);
	};
	await scan('Area');
	for (const tab of ['Dates', 'Layer', 'Data'] as const) {
		await panel(page, tab);
		await scan(tab);
	}
});

