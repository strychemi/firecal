<script lang="ts">
	// firecal: the map fills the window. Left: area, dates, layer and data panels. Right: the answer,
	// charts and methods. Bottom: the whole series as a time bar (drag = date range, click = month,
	// play = step through the months).
	import '../app.css';
	import '#lib/panels.css';
	import { onDestroy, onMount } from 'svelte';
	import { exportHotspots, fetchMeta } from '#lib/api.ts';
	import { cellsToCsv, downloadBlob, monthsToCsv } from '#lib/download.ts';
	import { continentName, fmt, isGlobal, monthLabel, monthRange, monthShortLabel, SOURCE_LABEL, SOURCES } from '#lib/format.ts';
	import { ERA_VAR } from '#lib/scales.ts';
	import type { Area, BBox, Baseline, CellValue, Meta, MonthRow, QueryResponse, YearMonth } from '#lib/types.ts';
	import FullMap from '#lib/map/FullMap.svelte';
	import { cachedQuery, classOf, quantileBreaks, seqColors, stepColor, type RGB, type RGBA, type Tool } from '#lib/map/helpers.ts';
	import AreaPicker from '#lib/components/AreaPicker.svelte';
	import MonthPicker from '#lib/components/MonthPicker.svelte';
	import AnswerCard from '#lib/components/AnswerCard.svelte';
	import CalendarHeatmap from '#lib/components/CalendarHeatmap.svelte';
	import YearlyBars from '#lib/components/YearlyBars.svelte';
	import SeasonCycle from '#lib/components/SeasonCycle.svelte';
	import MethodsPanel from '#lib/components/MethodsPanel.svelte';
	import TimeBar from '#lib/components/TimeBar.svelte';
	import { cellToLatLng } from 'h3-js';
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { MAX_LINK_POINTS, fromParams, toParams } from '#lib/share.ts';

	let meta = $state<Meta | null>(null);
	let fatal = $state('');

	// Request
	let area = $state<Area>({ preset: 'argentina-box' });
	let areaName = $state('Study region');
	let start = $state<YearMonth>('');
	let end = $state<YearMonth>('');
	let month = $state<YearMonth>('');
	let baseline = $state<Baseline>('median');

	// Responses
	let series = $state<MonthRow[]>([]);
	let data = $state<QueryResponse | null>(null);
	let dataAreaName = $state('');
	// The area behind the numbers on screen, which may differ from `area` while a new one loads.
	let dataArea: Area | null = null;
	// The area of the hexagons on screen, as text: the map fits only once these match the chosen area.
	let dataAreaKey = $state('');
	let busy = $state(false);
	let notice = $state('');
	let seq = 0;
	let seriesSeq = 0;

	// Panels and layer settings
	type Measure = 'month' | 'range';
	type Tab = 'area' | 'dates' | 'layer' | 'data';
	const TABS: [Tab, string][] = [
		['area', 'Area'],
		['dates', 'Dates'],
		['layer', 'Layer'],
		['data', 'Data']
	];
	let measure = $state<Measure>('month');
	let opacity = $state(0.85);
	let extruded = $state(false);
	let outline = $state(true);
	let tool = $state<Tool>('move');
	let tab = $state<Tab>('area');
	let leftOpen = $state(true);
	let rightOpen = $state(true);
	let colors = $state<RGB[]>([]);
	let lastView = $state<{ bbox: BBox; clipped: boolean } | null>(null);
	let fitKey = $state('');

	// Playback
	let playing = $state(false);
	let speed = $state<1 | 2 | 4>(1);
	let timer: ReturnType<typeof setTimeout> | undefined;

	// Light or dark follows the system setting (app.css tokens); the hexagon colours are read from
	// the tokens, so re-read them when the setting changes.
	let media: MediaQueryList | null = null;
	const recolor = () => (colors = seqColors());
	onMount(async () => {
		media = window.matchMedia('(prefers-color-scheme: dark)');
		media.addEventListener('change', recolor);
		colors = seqColors();
		if (window.innerWidth < 760) {
			leftOpen = false;
			rightOpen = false;
		}
		try {
			const m = await fetchMeta();
			meta = m;
			// A shared link sets the search; anything missing or invalid in it falls back to the defaults.
			const shared = fromParams(new URL(window.location.href).searchParams, m);
			start = shared.start ?? m.series_start;
			end = shared.end ?? m.series_end;
			month = shared.month ?? end;
			if (shared.baseline) baseline = shared.baseline;
			const first = m.presets.find((p) => p.id === 'argentina-box') ?? m.presets[0];
			if (shared.area) setArea(shared.area, shared.areaName!);
			else if (first) setArea({ preset: first.id }, first.name);
			else setArea({ bbox: m.region.bbox }, 'Whole region');
		} catch (e) {
			fatal = `Could not load firecal data: ${e instanceof Error ? e.message : String(e)}`;
		}
	});
	onDestroy(() => {
		clearTimeout(timer);
		media?.removeEventListener('change', recolor);
	});

	// Tabs: arrow keys, Home and End move between them, and selection follows focus.
	function tabKey(e: KeyboardEvent) {
		const i = TABS.findIndex(([id]) => id === tab);
		const n = TABS.length;
		const j = { ArrowRight: i + 1, ArrowLeft: i - 1 + n, Home: 0, End: n - 1 }[e.key];
		if (j == null) return;
		e.preventDefault();
		tab = TABS[j % n][0];
		document.getElementById(`tab-${tab}`)?.focus();
	}

	function setArea(a: Area, name: string) {
		area = a;
		areaName = name;
		fitKey = JSON.stringify(a);
	}

	// The address bar always holds a link to this search (replaced, not added to the history).
	// A polygon with too many points cannot go in a link: the address bar then drops the search, and
	// Copy link is off, so no link opens a different area than the one shown.
	let linkMsg = $state('');
	let canShare = $state(true);
	$effect(() => {
		if (!meta || !start || !end || !month) return;
		const qs = toParams({ area: $state.snapshot(area) as Area, start, end, month, baseline });
		canShare = qs !== null;
		const want = qs === null ? '' : `?${qs}`;
		if (window.location.search !== want) replaceState(want || window.location.pathname, page.state);
		linkMsg = '';
	});
	async function copyLink() {
		if (!canShare) return;
		try {
			await navigator.clipboard.writeText(window.location.href);
			linkMsg = 'Link copied.';
		} catch {
			linkMsg = 'Could not copy; copy the address from the address bar instead.';
		}
	}

	// The whole series for the area: the time bar's histogram. Only the area changes it.
	$effect(() => {
		if (!meta) return;
		const req = { area: $state.snapshot(area) as Area, start: meta.series_start, end: meta.series_end, month: meta.series_end };
		const my = ++seriesSeq;
		cachedQuery(req)
			.then((r) => {
				if (my === seriesSeq) series = r.months;
			})
			.catch(() => {});
	});

	// The selected dates and month: hexagons, answer and charts. Previous results stay on screen while loading.
	$effect(() => {
		if (!meta || !start || !end || !month) return;
		const req = { area: $state.snapshot(area) as Area, start, end, month, baseline };
		const name = areaName;
		const my = ++seq;
		busy = true;
		cachedQuery(req)
			.then((r) => {
				if (my !== seq) return;
				data = r;
				dataAreaName = name;
				dataArea = req.area;
				dataAreaKey = JSON.stringify(req.area);
				notice = '';
			})
			.catch((e) => {
				if (my !== seq) return;
				notice = `The query failed: ${e instanceof Error ? e.message : String(e)}`;
				playing = false;
				rightOpen = true; // the notice lives in the insights panel
			})
			.finally(() => {
				if (my === seq) busy = false;
			});
	});

	function setRange(s: YearMonth, e: YearMonth) {
		start = s;
		end = e;
		if (month < s) month = s;
		if (month > e) month = e;
	}
	function setStart(v: YearMonth) {
		start = v;
		if (end < start) end = start;
		if (month < start) month = start;
	}
	function setEnd(v: YearMonth) {
		const followEnd = month === end;
		end = v;
		if (start > end) start = end;
		if (followEnd || month > end) month = end;
	}

	// Play: step the month through the date range, prefetching the next month.
	const rangeMonths = $derived(start && end ? monthRange(start, end) : []);
	function nextMonth(m: YearMonth): YearMonth {
		const i = rangeMonths.indexOf(m);
		return rangeMonths[(i + 1) % rangeMonths.length];
	}
	$effect(() => {
		clearTimeout(timer);
		if (!playing || !data || busy || !meta) return;
		const nxt = nextMonth(month);
		const req = { area: $state.snapshot(area) as Area, start, end, month: nxt, baseline };
		cachedQuery(req).catch(() => {});
		timer = setTimeout(() => (month = nxt), 700 / speed);
	});
	function togglePlay() {
		if (!playing && month === end) month = start;
		playing = !playing;
		if (playing) measure = 'month';
	}

	// Hexagon colours: quantile classes of the chosen measure over the hexagons on screen.
	const cells = $derived<CellValue[]>((data?.cells ?? []).filter((c) => c[measure] > 0));
	const breaks = $derived(quantileBreaks(cells.map((c) => c[measure])));
	const k = $derived(breaks.length + 1);
	const fill = $derived.by(() => {
		const b = breaks;
		const m = measure;
		const cs = colors;
		return (d: CellValue): RGBA => (cs.length ? [...stepColor(classOf(d[m], b), k, cs), 235] : [128, 128, 128, 200]);
	});
	const fillKey = $derived(`${measure}|${breaks.join(',')}|${colors.flat().join(',')}`);
	const legend = $derived.by(() => {
		if (!colors.length || !cells.length) return [];
		const vals = cells.map((c) => c[measure]);
		const edges = [Math.min(...vals), ...breaks, Math.max(...vals)];
		return Array.from({ length: k }, (_, i) => ({
			color: `rgb(${stepColor(i, k, colors).join(',')})`,
			label: i === k - 1 ? `${fmt(edges[i])}–${fmt(edges[i + 1])}` : `${fmt(edges[i])}–<${fmt(edges[i + 1])}`
		}));
	});

	// 3D height: date-range fire-days, square-root scaled, tallest column sized to the hexagon level.
	const HEIGHT: Record<number, number> = { 4: 140000, 5: 60000, 6: 24000 };
	const rangeMax = $derived(Math.max(1, ...(data?.cells ?? []).map((c) => c.range)));
	const elevation = $derived.by(() => {
		const top = HEIGHT[data?.area.resolution ?? 6] ?? 24000;
		const mx = rangeMax;
		return (d: CellValue) => Math.sqrt(d.range / mx) * top;
	});
	const elevationKey = $derived(`${rangeMax}|${data?.area.resolution}`);

	// The map in words, for anyone who can't see it or hover over it: the busiest hexagons and where they are.
	const where = ([lat, lon]: number[]) =>
		`${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(1)}° ${lon >= 0 ? 'E' : 'W'}`;
	const busiest = $derived(
		[...cells]
			.sort((a, b) => b[measure] - a[measure])
			.slice(0, 5)
			.map((c) => ({ ...c, at: where(cellToLatLng(c.h3)) }))
	);
	const mapWhen = $derived(
		!data ? '' : measure === 'month' ? `in ${monthLabel(data.stats.month)}` : `from ${monthLabel(data.start)} to ${monthLabel(data.end)}`
	);
	const mapSummary = $derived(
		!data
			? ''
			: cells.length === 0
				? `No hexagon in this area had fire ${mapWhen}.`
				: `${fmt(cells.length)} of ${fmt(data.area.hexagons)} hexagons (level ${data.area.resolution}) had fire ${mapWhen}. The busiest had ${fmt(
						busiest[0][measure]
					)} fire-days, centred at ${busiest[0].at}.`
	);

	const tooltip = (d: CellValue) =>
		data
			? `<b>${fmt(d.month)}</b> fire-days in ${monthLabel(data.stats.month)}<br><b>${fmt(d.range)}</b> fire-days, ${monthShortLabel(
					data.start
				)}–${monthShortLabel(data.end)}<br><span style="opacity:.7">H3 ${d.h3} · level ${data.area.resolution}</span>`
			: null;

	const TOOLS: { id: Tool; label: string }[] = [
		{ id: 'move', label: 'Pan' },
		{ id: 'rectangle', label: 'Box' },
		{ id: 'polygon', label: 'Polygon' },
		{ id: 'circle', label: 'Circle' }
	];
	const HINT: Record<Tool, string> = {
		move: '',
		rectangle: 'Drag from one corner to the opposite one. Esc cancels.',
		polygon: 'Click each corner; click the first point or press Enter to finish. Esc cancels.',
		circle: 'Press at the centre and drag to the edge. Esc cancels.'
	};
	function useView() {
		if (!lastView) return;
		area = { bbox: lastView.bbox };
		areaName = lastView.clipped ? 'Map view (to the 180° line)' : 'Map view';
	}

	// Downloads
	const slug = (s: string) =>
		s
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '')
			.slice(0, 40);
	// Printed under the title of a saved chart image.
	const chartContext = $derived(data ? `${dataAreaName}, ${monthLabel(data.start)} to ${monthLabel(data.end)}` : '');
	const fileBase = $derived(data ? `firecal-${slug(dataAreaName)}-${data.start}_${data.end}` : 'firecal');
	let exporting = $state(false);
	let exportMsg = $state('');
	async function downloadHotspots() {
		if (!data) return;
		exporting = true;
		exportMsg = '';
		try {
			const shown = dataArea ?? ($state.snapshot(area) as Area);
			downloadBlob(`${fileBase}-hotspots.csv`, await exportHotspots({ area: shown, start: data.start, end: data.end }));
		} catch (e) {
			exportMsg = e instanceof Error ? e.message : String(e);
		} finally {
			exporting = false;
		}
	}
	const fmtShare = (s: number | null | undefined) =>
		s == null ? 'all' : `${(s * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })} %`;

	const padding = $derived({ top: 64, bottom: 170, left: leftOpen ? 350 : 24, right: rightOpen ? 440 : 24 });
</script>

<svelte:head>
	<title>firecal: burning-activity calendar</title>
	<meta name="description" content="How unusual is this month's burning? MODIS and VIIRS fire counts on one scale, 2000–2025." />
</svelte:head>

<a class="skip" href="#answer">Skip to the answer</a>

<main class="proto">
	{#if fatal}
		<p class="glass msg" role="alert">{fatal}</p>
	{:else if meta}
		<FullMap
			{meta}
			hexes={cells}
			{fill}
			{fillKey}
			{extruded}
			{elevation}
			{elevationKey}
			{opacity}
			{outline}
			ring={data?.area.ring ?? null}
			fitKey={dataAreaKey === fitKey ? fitKey : ''}
			{tooltip}
			bind:tool
			{padding}
			describedby="map-summary"
			onview={(bbox, clipped) => (lastView = { bbox, clipped })}
			onarea={setArea}
		/>

		<p class="sr" id="map-summary">{mapSummary}</p>
		<header class="glass brand">
			<h1>firecal</h1>
			<span class="sub" title="Is this month's burning unusual? Satellite fire counts from 2000 to today, on one scale.">{areaName}</span>
			{#if busy}<progress class="spin" aria-label="Loading"></progress>{/if}
		</header>
		{#if HINT[tool]}<p class="glass hint" aria-live="polite">{HINT[tool]}</p>{/if}

		<!-- Left: area, dates, layer and data -->
		<aside class="glass left" class:closed={!leftOpen} aria-label="Area, dates, layer and data">
			<button class="collapse pbtn" type="button" aria-expanded={leftOpen} onclick={() => (leftOpen = !leftOpen)}>
				{leftOpen ? '‹ Hide' : '☰ Area, dates and layers'}
			</button>
			{#if leftOpen}
				<!-- svelte-ignore a11y_interactive_supports_focus -->
				<div class="tabs seg" role="tablist" aria-label="Panel" onkeydown={tabKey}>
					{#each TABS as [id, label] (id)}
						<button
							type="button"
							role="tab"
							id="tab-{id}"
							aria-selected={tab === id}
							tabindex={tab === id ? 0 : -1}
							onclick={() => (tab = id)}>{label}</button
						>
					{/each}
				</div>
				<div class="pane scroll" role="tabpanel" aria-labelledby="tab-{tab}">
					{#if tab === 'area'}
						<section>
							<h2 class="p-h">Draw on the map</h2>
							<div class="seg" role="group" aria-label="Map tools">
								{#each TOOLS as t (t.id)}
									<button type="button" aria-pressed={tool === t.id} onclick={() => (tool = t.id)}>{t.label}</button>
								{/each}
							</div>
							<p><button class="pbtn" type="button" onclick={useView} disabled={!lastView}>Search the map view</button></p>
							{#if lastView?.clipped}<p class="small">The view crosses the 180° line; the search stops at it.</p>{/if}
						</section>
						<section class="picker">
							<h2 class="p-h">Places and coordinates</h2>
							<AreaPicker {meta} {area} onarea={setArea} />
						</section>
					{:else if tab === 'dates'}
						<section class="dates">
							<h2 class="p-h">Dates</h2>
							<MonthPicker id="start" label="From" value={start} min={meta.series_start} max={meta.series_end} onchange={setStart} />
							<MonthPicker id="end" label="To" value={end} min={meta.series_start} max={meta.series_end} onchange={setEnd} />
							<MonthPicker id="month" label="Describe month" value={month} min={meta.series_start} max={meta.series_end} onchange={(v) => (month = v)} />
							<p class="small">Or drag across the time bar at the bottom, and click a bar to pick the month.</p>
						</section>
						<fieldset class="baseline">
							<legend class="p-h">"Usual" means the</legend>
							<label class="row"><input type="radio" name="baseline" value="median" bind:group={baseline} /> Median (steadier)</label>
							<label class="row"><input type="radio" name="baseline" value="mean" bind:group={baseline} /> Average (mean)</label>
						</fieldset>
					{:else if tab === 'layer'}
						<section>
							<h2 class="p-h">Fire-days per hexagon</h2>
							<div class="seg" role="group" aria-label="Colour hexagons by">
								<button type="button" aria-pressed={measure === 'month'} onclick={() => (measure = 'month')}>Selected month</button>
								<button type="button" aria-pressed={measure === 'range'} onclick={() => (measure = 'range')}>Date range</button>
							</div>
							{#if data}
								<p class="small">
									{measure === 'month' ? monthLabel(data.stats.month) : `${monthShortLabel(data.start)} – ${monthShortLabel(data.end)}`},
									{fmt(cells.length)} hexagons with fire at level {data.area.resolution}. Classes are quantiles of the hexagons shown.
								</p>
							{/if}
							<ul class="legend" aria-label="Colour classes">
								{#each legend as l, i (i)}
									<li><span class="swatch" style="background:{l.color}"></span>{l.label}</li>
								{/each}
							</ul>
						</section>
						<section>
							<h2 class="p-h">Style</h2>
							<label class="row">Opacity <input type="range" min="0.2" max="1" step="0.05" bind:value={opacity} aria-label="Hexagon opacity" /></label>
							<label class="row"><input type="checkbox" bind:checked={outline} disabled={extruded} /> Hexagon outlines</label>
							<label class="row"><input type="checkbox" bind:checked={extruded} /> 3D: height = fire-days over the date range</label>
							{#if extruded}<p class="small">Height grows with the square root of the date-range total. Right-drag or ctrl-drag to tilt and turn.</p>{/if}
						</section>
						<section>
							<h2 class="p-h">Satellite eras (time bar colours)</h2>
							<ul class="legend">
								{#each SOURCES as s (s)}
									<li><span class="swatch" style="background:{ERA_VAR[s]}"></span>{SOURCE_LABEL[s]}</li>
								{/each}
							</ul>
							<p class="small">Faded bars are months with missing satellite days, left out of the "usual".</p>
						</section>
					{:else if data}
						<section class="downloads" aria-labelledby="dl-title">
							<h2 id="dl-title" class="p-h">Downloads</h2>
							<p class="small">
								Monthly series for {dataAreaName}, {monthLabel(data.start)} to {monthLabel(data.end)}, with every field: converted value, 80 % range,
								raw count, hotspots, fire power, days with data and record.
							</p>
							<div class="stack">
								<button class="pbtn primary" type="button" onclick={() => downloadBlob(`${fileBase}-monthly.csv`, new Blob([monthsToCsv(data!.months)], { type: 'text/csv' }))}>
									Download CSV ({data.months.length} months)
								</button>
								{#if meta.export_limit != null}
									<button class="pbtn" type="button" onclick={downloadHotspots} disabled={exporting} aria-describedby="hotspot-note">
										{exporting ? 'Preparing hotspots…' : 'Hotspots CSV'}
									</button>
								{/if}
								<button
									class="pbtn"
									type="button"
									disabled={!data.cells.length}
									onclick={() => downloadBlob(`${fileBase}-hexagons.csv`, new Blob([cellsToCsv(data!)], { type: 'text/csv' }))}
								>
									Hexagon CSV for Kepler.gl ({data.cells.length.toLocaleString('en-US')} hexagons)
								</button>
							</div>
							{#if exportMsg}<p class="small warn" role="alert">{exportMsg}</p>{/if}

							<p class="small">
								The hexagon CSV has one row per hexagon with fire: its H3 index (<code>hex_id</code>), fire-days in {monthLabel(data.stats.month)} and over
								the selected dates. Drop it on <a href="https://kepler.gl/demo" target="_blank" rel="noopener noreferrer">kepler.gl/demo</a>. Each chart
								has its own SVG and PNG buttons.
							</p>
							{#if meta.export_limit == null}
								<p class="small" id="hotspot-note">
									The hotspot CSV is not available for this data yet; download hotspots from
									<a href="https://firms.modaps.eosdis.nasa.gov/download/" target="_blank" rel="noopener noreferrer">NASA FIRMS</a> instead.
								</p>
							{:else}
								<p class="small" id="hotspot-note">
									The hotspots CSV lists every detection that passed the filters in this area, {monthLabel(data.start)} to {monthLabel(data.end)}, from
									every satellite: position, UTC and local solar time, satellite, day or night, confidence and fire power. <code>in_calendar</code> is
									true for the detections from the satellite the calendar counts that day. Up to {meta.export_limit.toLocaleString('en-US')} rows per
									file; narrow the dates for large areas.
								</p>
							{/if}
						</section>
						<section aria-labelledby="share-title">
							<h2 id="share-title" class="p-h">Share</h2>
							<p class="small">The address bar holds a link to this search: area, dates, month and "usual". Anyone opening it sees the same answer.</p>
							<button class="pbtn" type="button" onclick={copyLink} disabled={!canShare} aria-describedby={canShare ? undefined : 'share-off'}>Copy link</button>
							{#if !canShare}
								<p id="share-off" class="small">This polygon has more than {MAX_LINK_POINTS} points, too many for a link. Draw a simpler one, or use a box, to share the search.</p>
							{/if}
							<p class="small" role="status">{linkMsg}</p>
						</section>
					{/if}
				</div>
			{/if}
		</aside>

		<!-- Right: answer, charts and methods -->
		<aside class="right" id="answer" tabindex="-1" class:closed={!rightOpen} aria-label="Answer and charts">
			<button class="collapse pbtn glass" type="button" aria-expanded={rightOpen} onclick={() => (rightOpen = !rightOpen)}>
				{rightOpen ? 'Hide ›' : '‹ Answer and charts'}
			</button>
			{#if rightOpen}
				<div class="insights scroll">
					{#if notice}<p class="card notice" role="alert">{notice}</p>{/if}
					{#if data}
						<AnswerCard {data} areaName={dataAreaName} {busy} live={!playing} />
						<p class="card small area-meta">
							{dataAreaName}: {data.area.hexagons.toLocaleString('en-US')} hexagons at level {data.area.resolution},
							{data.area.active_hexagons.toLocaleString('en-US')} with any fire. Showing {monthLabel(data.start)} to {monthLabel(data.end)}.
							{#if isGlobal(meta) && data.continent}
								{#if data.continent === 'World'}
									No fire here in any year, so no continent's model applies; days with data are counted for the whole globe.
								{:else if meta.continents?.[data.continent]?.fitted === false}
									{continentName(data.continent)} ({fmtShare(data.continent_share)} of this area's fire-days) has no model: too few fires to fit one, so
									months before February 2012 have no data.
								{:else}
									Converted with the {continentName(data.continent)} model, which holds {fmtShare(data.continent_share)} of this area's fire-days.
								{/if}
							{/if}
						</p>
						<section class="card small" aria-labelledby="map-words-title">
							<h2 id="map-words-title" class="p-h">On the map</h2>
							<p>{mapSummary}</p>
							{#if busiest.length > 1}
								<ol class="busiest">
									{#each busiest as b (b.h3)}
										<li>{fmt(b[measure])} fire-days at {b.at}</li>
									{/each}
								</ol>
							{/if}
							<p>Every hexagon's values are in the hexagon CSV (Data tab).</p>
						</section>
						<CalendarHeatmap months={data.months} selected={data.stats.month} onselect={(m) => (month = m)} filename="{fileBase}-calendar" {busy} context={chartContext} />
						<YearlyBars months={data.months} filename="{fileBase}-yearly" {busy} context={chartContext} />
						<SeasonCycle months={data.months} selected={data.stats.month} {baseline} filename="{fileBase}-season" {busy} context={chartContext} />
						<MethodsPanel {meta} {data} />
					{:else if busy}
						<p class="card" role="status">Loading…</p>
					{/if}
				</div>
			{/if}
		</aside>

		<!-- Bottom: time bar -->
		<section class="glass time" aria-label="Time">
			<div class="time-head">
				<button class="pbtn play" type="button" onclick={togglePlay} aria-pressed={playing} disabled={!data}>
					{playing ? '❚❚ Pause' : '▶ Play'}
				</button>
				<div class="seg" role="group" aria-label="Playback speed">
					{#each [1, 2, 4] as s (s)}
						<button type="button" aria-pressed={speed === s} onclick={() => (speed = s as 1 | 2 | 4)}>{s}×</button>
					{/each}
				</div>
				<span class="now"
					><strong>{month ? monthLabel(month) : ''}</strong>{#if meta.in_progress && month === meta.in_progress.month}
						· days 1–{meta.in_progress.days} so far{/if}</span
				>
				<span class="range">Dates {start ? monthShortLabel(start) : ''} – {end ? monthShortLabel(end) : ''}</span>
				<button class="pbtn" type="button" onclick={() => {
						if (!meta) return;
						setRange(meta.series_start, meta.series_end);
						measure = 'range';
					}}>Whole series</button>
			</div>
			{#if series.length}
				<!-- The map follows what the time bar was last used for: a month clicked shows that month, a range dragged shows the range. -->
				<TimeBar
					{series}
					{start}
					{end}
					{month}
					{busy}
					onrange={(a, b) => {
						setRange(a, b);
						measure = 'range';
					}}
					onmonth={(m) => {
						month = m;
						measure = 'month';
					}}
				/>
			{:else}
				<p class="small">Loading the series…</p>
			{/if}
			<p class="small help">
				Drag across the bars to set the dates, or type them in the Dates tab · click a bar to map that month · arrow keys step months. Bar
				height: fire-days (square-root scale).
				Fire data: NASA FIRMS.
			</p>
		</section>
	{:else}
		<p class="glass msg" role="status">Loading…</p>
	{/if}
</main>

<style>
	.skip {
		position: absolute;
		left: -9999px;
	}
	.skip:focus {
		left: 16px;
		top: 8px;
		z-index: 10;
		background: var(--surface);
		padding: 8px 12px;
		border-radius: 8px;
	}
	.msg {
		position: absolute;
		top: 40%;
		left: 50%;
		transform: translateX(-50%);
		padding: 12px 16px;
	}
	.brand {
		position: absolute;
		top: 12px;
		left: 50%;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 6px 12px;
		z-index: 3;
		max-width: calc(100% - 24px);
	}
	h1 {
		font-size: 1rem;
		margin: 0;
	}
	.sub {
		color: var(--text-2);
		font-size: 0.85rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	/* An indeterminate <progress> drawn as a small ring. */
	progress.spin {
		appearance: none;
		width: 14px;
		height: 14px;
		border: 2px solid var(--axis);
		border-top-color: var(--accent);
		border-radius: 50%;
		background: none;
		animation: spin 0.8s linear infinite;
	}
	progress.spin::-webkit-progress-bar {
		display: none;
		background: none;
	}
	progress.spin::-webkit-progress-value {
		display: none;
		background: none;
	}
	progress.spin::-moz-progress-bar {
		display: none;
		background: none;
	}
	@media (prefers-reduced-motion: reduce) {
		/* Slower, not stopped, so it still shows that something is loading. */
		progress.spin {
			animation-duration: 6s;
		}
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.hint {
		position: absolute;
		top: 56px;
		left: 50%;
		transform: translateX(-50%);
		margin: 0;
		padding: 6px 12px;
		font-size: 0.82rem;
		z-index: 3;
	}
	.left {
		position: absolute;
		top: 12px;
		left: 12px;
		/* As tall as its content, up to the space above the time panel (12px + 172px). */
		max-height: calc(100% - 184px);
		width: 320px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 10px;
		z-index: 2;
	}
	.left.closed {
		width: auto;
		padding: 6px;
	}
	.collapse {
		align-self: flex-start;
	}
	.tabs {
		width: 100%;
	}
	.tabs button {
		flex: 1;
	}
	.pane {
		flex: 0 1 auto;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 16px;
		/* Room for focus rings, which a scrolling box would otherwise cut off at its edges. */
		padding: 4px 8px 4px 4px;
		margin: -4px;
	}
	section p {
		margin: 8px 0 0;
	}
	.small {
		font-size: 0.78rem;
		color: var(--text-2);
		line-height: 1.45;
	}
	.warn,
	.notice {
		background: var(--warn-bg);
		border-color: var(--warn-border);
	}
	.notice {
		margin: 0;
	}
	.legend {
		list-style: none;
		margin: 8px 0 0;
		padding: 0;
		display: grid;
		gap: 4px;
		font-size: 0.8rem;
	}
	.legend li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.85rem;
		margin-top: 6px;
	}
	.row input[type='range'] {
		flex: 1;
	}
	.row input {
		accent-color: var(--accent);
	}
	.dates {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.baseline {
		border: 0;
		margin: 0;
		padding: 0;
	}
	.stack {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 6px;
		margin-top: 8px;
	}
	.picker :global(.card) {
		padding: 0;
		border: 0;
		background: none;
	}
	.right {
		position: absolute;
		top: 12px;
		right: 12px;
		bottom: 172px;
		width: 420px;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 8px;
		z-index: 2;
		pointer-events: none;
	}
	.right > * {
		pointer-events: auto;
	}
	.right.closed {
		bottom: auto;
	}
	.insights {
		width: 100%;
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
		border-radius: 12px;
	}
	.insights :global(.card) {
		background: var(--surface);
		flex-shrink: 0;
	}
	.area-meta {
		margin: 0;
	}
	.busiest {
		margin: 6px 0 0;
		padding-left: 20px;
	}
	.proto {
		/* Keep the map's zoom buttons above the time panel. */
		--map-ctrl-bottom: 172px;
	}
	.proto:has(.right:not(.closed)) {
		/* ...and beside the open insights panel. */
		--map-ctrl-right: 432px;
	}
	.time {
		position: absolute;
		left: 12px;
		right: 12px;
		bottom: 12px;
		padding: 8px 12px 6px;
		z-index: 3;
	}
	.time-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 12px;
		margin-bottom: 4px;
		font-size: 0.85rem;
	}
	.play {
		min-width: 84px;
	}
	.range {
		color: var(--text-2);
	}
	.time-head .pbtn:last-child {
		margin-left: auto;
	}
	.help {
		margin: 2px 0 0;
	}
	@media (max-width: 1100px) {
		.right {
			width: 360px;
		}
		.proto:has(.right:not(.closed)) {
			--map-ctrl-right: 372px;
		}
	}
	@media (max-width: 760px) {
		.proto {
			--map-ctrl-bottom: 196px;
		}
		.left,
		.right {
			bottom: 196px;
		}
		.left:not(.closed),
		.right:not(.closed) {
			left: 8px;
			right: 8px;
			width: auto;
			top: 56px;
			z-index: 4;
			background: var(--surface);
		}
		.right:not(.closed) {
			align-items: stretch;
		}
		.right.closed,
		.left.closed {
			top: 56px;
		}
		.brand {
			left: 8px;
			right: 8px;
			transform: none;
		}
		.time {
			left: 8px;
			right: 8px;
			bottom: 8px;
		}
		.range,
		.help {
			display: none;
		}
	}
</style>
