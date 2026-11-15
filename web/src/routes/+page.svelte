<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { exportHotspots, fetchMeta, query } from '#lib/api.ts';
	import { cellsToCsv, downloadBlob, monthsToCsv } from '#lib/download.ts';
	import { monthLabel } from '#lib/format.ts';
	import type { Area, Baseline, Meta, QueryResponse, YearMonth } from '#lib/types.ts';
	import AreaPicker from '#lib/components/AreaPicker.svelte';
	import MonthPicker from '#lib/components/MonthPicker.svelte';
	import AnswerCard from '#lib/components/AnswerCard.svelte';
	import CalendarHeatmap from '#lib/components/CalendarHeatmap.svelte';
	import YearlyBars from '#lib/components/YearlyBars.svelte';
	import MonthlyLine from '#lib/components/MonthlyLine.svelte';
	import Methods from '#lib/components/Methods.svelte';
	import MapView from '#lib/components/MapView.svelte';

	let meta = $state<Meta | null>(null);
	let fatal = $state('');

	let area = $state<Area>({ preset: 'argentina-box' });
	let areaName = $state('Study region');
	let start = $state<YearMonth>('');
	let end = $state<YearMonth>('');
	let month = $state<YearMonth>('');
	let baseline = $state<Baseline>('median');

	let data = $state<QueryResponse | null>(null);
	let dataAreaName = $state('');
	let busy = $state(false);
	let notice = $state('');
	let seq = 0;
	// The area behind the numbers on screen, which may differ from `area` while a new one loads.
	let dataArea: Area | null = null;

	onMount(async () => {
		try {
			const m = await fetchMeta();
			meta = m;
			start = m.series_start;
			end = m.series_end;
			month = m.series_end;
			const first = m.presets.find((p) => p.id === 'argentina-box') ?? m.presets[0];
			if (first) {
				area = { preset: first.id };
				areaName = first.name;
			}
		} catch (e) {
			fatal = `Could not load firecal data: ${e instanceof Error ? e.message : String(e)}`;
		}
	});

	// Re-query whenever the request changes. Previous charts stay on screen (dimmed) while loading.
	$effect(() => {
		if (!meta || !start || !end || !month) return;
		const req = { area: $state.snapshot(area) as Area, start, end, month, baseline };
		const name = areaName;
		const my = ++seq;
		busy = true;
		query(req)
			.then((res) => {
				if (my !== seq) return;
				data = res;
				dataAreaName = name;
				dataArea = req.area;
				notice = '';
			})
			.catch((e) => {
				if (my !== seq) return;
				notice = `The query failed: ${e instanceof Error ? e.message : String(e)}`;
			})
			.finally(() => {
				if (my === seq) busy = false;
			});
	});

	function setArea(a: Area, name: string) {
		area = a;
		areaName = name;
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

	const slug = (s: string) =>
		s
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '')
			.slice(0, 40);
	const fileBase = $derived(data ? `firecal-${slug(dataAreaName)}-${data.start}_${data.end}` : 'firecal');

	function downloadCsv() {
		if (!data) return;
		downloadBlob(`${fileBase}-monthly.csv`, new Blob([monthsToCsv(data.months)], { type: 'text/csv' }));
	}
	let exporting = $state(false);
	let exportMsg = $state('');
	async function downloadHotspots() {
		if (!data) return;
		exporting = true;
		exportMsg = '';
		try {
			// The area that produced the numbers on screen, even if a new one is still loading.
			const shownArea = dataArea ?? ($state.snapshot(area) as Area);
			const blob = await exportHotspots({ area: shownArea, start: data.start, end: data.end });
			downloadBlob(`${fileBase}-hotspots.csv`, blob);
		} catch (e) {
			exportMsg = e instanceof Error ? e.message : String(e);
		} finally {
			exporting = false;
		}
	}

	function downloadHexCsv() {
		if (!data) return;
		downloadBlob(`${fileBase}-hexagons.csv`, new Blob([cellsToCsv(data)], { type: 'text/csv' }));
	}
</script>

<svelte:head>
	<title>firecal: burning-activity calendar</title>
	<meta name="description" content="How unusual is this month's burning? MODIS and VIIRS fire counts on one scale, 2000–2025." />
</svelte:head>

<a class="skip" href="#answer">Skip to the answer</a>

<header class="top">
	<div class="inner">
		<div class="brand">
			<h1>firecal</h1>
			<p>Is this month's burning unusual? Satellite fire counts from 2000 to today, on one scale.</p>
		</div>
	</div>
</header>

<main class="inner">
	{#if fatal}
		<p class="card notice" role="alert">{fatal}</p>
	{:else if !meta}
		<p class="card" role="status">Loading…</p>
	{:else}
		<section class="choose" aria-labelledby="choose-title">
			<div class="card">
				<h2 id="choose-title" class="h">Choose an area</h2>
				<AreaPicker {meta} {area} onarea={setArea} />
			</div>
			<MapView {meta} {data} {busy} onarea={setArea} />
		</section>

		<section class="card filters" aria-label="Dates and comparison">
			<MonthPicker id="start" label="From" value={start} min={meta.series_start} max={meta.series_end} onchange={setStart} />
			<MonthPicker id="end" label="To" value={end} min={meta.series_start} max={meta.series_end} onchange={setEnd} />
			<MonthPicker id="month" label="Describe month" value={month} min={meta.series_start} max={meta.series_end} onchange={(v) => (month = v)} />
			<fieldset class="baseline">
				<legend>"Usual" means the</legend>
				<div class="seg">
					<label class="radio"><input type="radio" name="baseline" value="median" bind:group={baseline} /> Median (steadier)</label>
					<label class="radio"><input type="radio" name="baseline" value="mean" bind:group={baseline} /> Average (mean)</label>
				</div>
			</fieldset>
		</section>

		{#if notice}
			<p class="card notice" role="alert">{notice}</p>
		{/if}

		<div id="answer">
			{#if data}
				<AnswerCard {data} areaName={dataAreaName} {busy} />
			{:else if busy}
				<p class="card" role="status">Loading…</p>
			{/if}
		</div>

		{#if data}
			<p class="area-meta">
				{dataAreaName}: {data.area.hexagons.toLocaleString('en-US')} hexagons at level {data.area.resolution},
				{data.area.active_hexagons.toLocaleString('en-US')} with any fire. Showing {monthLabel(data.start)} to {monthLabel(data.end)}.
			</p>
			<div class="charts">
				<CalendarHeatmap months={data.months} selected={data.stats.month} onselect={(m) => (month = m)} filename="{fileBase}-calendar" {busy} />
				<YearlyBars months={data.months} filename="{fileBase}-yearly" {busy} />
				<div class="wide">
					<MonthlyLine months={data.months} selected={data.stats.month} filename="{fileBase}-monthly" {busy} />
				</div>
			</div>

			<section class="card downloads" aria-labelledby="dl-title">
				<h2 id="dl-title" class="h">Downloads</h2>
				<p>
					Monthly series for {dataAreaName}, {monthLabel(data.start)} to {monthLabel(data.end)}, with every field: converted value,
					80 % range, raw count, hotspots, fire power, days with data and record.
				</p>
				<div class="dl-row">
					<button class="btn primary" type="button" onclick={downloadCsv}>Download CSV ({data.months.length} months)</button>
					<button class="btn" type="button" onclick={downloadHotspots} disabled={exporting} aria-describedby="hotspot-note">
						{exporting ? 'Preparing hotspots…' : 'Hotspots CSV'}
					</button>
					<button class="btn" type="button" onclick={downloadHexCsv} disabled={data.cells.length === 0}>
						Hexagon CSV for Kepler.gl ({data.cells.length.toLocaleString('en-US')} hexagons)
					</button>
				</div>
				<p class="small">
					The hexagon CSV has one row per hexagon with fire: its H3 index (<code>hex_id</code>), fire-days in {monthLabel(data.stats.month)}
					and over the selected dates. Drop it on <a href="https://kepler.gl/demo" target="_blank" rel="noopener noreferrer">kepler.gl/demo</a>, which
					draws the H3 column as hexagons. Each chart has its own SVG and PNG buttons.
				</p>
				<p class="small" id="hotspot-note">
					The hotspots CSV lists every detection that passed the filters in this area, {monthLabel(data.start)} to {monthLabel(data.end)},
					from every satellite: position, UTC and local solar time, satellite, day or night, confidence and fire power.
					<code>in_calendar</code> is true for the detections from the satellite the calendar counts that day. Up to
					{(meta.export_limit ?? 250000).toLocaleString('en-US')} rows per file; narrow the dates for large areas.
				</p>
				{#if exportMsg}<p class="notice small" role="alert">{exportMsg}</p>{/if}
			</section>
		{/if}

		<Methods {meta} />
	{/if}
</main>

<footer class="inner foot">
	<p>firecal · NASA Space Apps 2026 · Fire data: NASA FIRMS.</p>
</footer>

<style>
	.inner {
		max-width: 1160px;
		margin: 0 auto;
		padding: 0 16px;
	}
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
	.top {
		border-bottom: 1px solid var(--border);
		background: var(--surface);
		margin-bottom: 16px;
	}
	.top .inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding-top: 14px;
		padding-bottom: 14px;
		flex-wrap: wrap;
	}
	h1 {
		font-size: 1.4rem;
		letter-spacing: -0.01em;
	}
	.brand p {
		margin: 2px 0 0;
		color: var(--text-2);
		font-size: 0.9rem;
	}
	main {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.h {
		font-size: 1.1rem;
		margin-bottom: 12px;
	}
	.choose {
		display: grid;
		grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
		gap: 16px;
		align-items: start;
	}
	.dl-row {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 12px 24px;
		align-items: flex-end;
	}
	.baseline {
		border: 0;
		padding: 0;
		margin: 0;
	}
	.baseline legend {
		font-size: 0.8rem;
		color: var(--text-2);
		padding: 0;
		margin-bottom: 4px;
	}
	.radio {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
		padding: 0 10px 0 6px;
		border: 1px solid var(--border);
		border-radius: 8px;
		font-size: 0.9rem;
		cursor: pointer;
	}
	.radio input {
		accent-color: var(--accent);
		margin: 0;
	}
	.notice {
		margin: 0;
		background: var(--warn-bg);
		border-color: var(--warn-border);
	}
	.area-meta {
		margin: 0;
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.charts {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 16px;
		align-items: start;
	}
	.wide {
		grid-column: 1 / -1;
		min-width: 0;
	}
	.downloads p {
		margin: 0 0 12px;
		font-size: 0.9rem;
		max-width: 70ch;
	}
	.downloads .small {
		margin: 12px 0 0;
		color: var(--text-2);
		font-size: 0.85rem;
	}
	.foot {
		color: var(--text-2);
		font-size: 0.8rem;
		padding-top: 24px;
		padding-bottom: 24px;
	}
	@media (max-width: 900px) {
		.choose,
		.charts {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	@media (max-width: 480px) {
		:global(.card) {
			padding: 12px;
		}
	}
</style>
