<script lang="ts">
	// Prototype A, "Now": for fire responders, firefighters and duty officers.
	// The map is the search: pan or zoom and the area follows the view. Each hexagon is coloured by
	// how the chosen month compares with its own usual month. One answer, a strip of recent months.
	import '../../../app.css';
	import '#lib/panels.css';
	import { onMount } from 'svelte';
	import { exportHotspots, fetchMeta } from '#lib/api.ts';
	import { cellsToCsv, downloadBlob, monthsToCsv } from '#lib/download.ts';
	import { continentName, fmt, fmt1, isGlobal, monthLabel, monthRange, monthShortLabel, SOURCE_LABEL } from '#lib/format.ts';
	import { anomalies, type Anomaly, CATEGORY_GLYPH, CATEGORY_ORDER, CATEGORY_VAR, CATEGORY_INK } from '#lib/scales.ts';
	import type { Area, Baseline, BBox, Meta, QueryResponse, YearMonth } from '#lib/types.ts';
	import FullMap from '#lib/map/FullMap.svelte';
	import AreaPicker from '#lib/components/AreaPicker.svelte';
	import CalendarHeatmap from '#lib/components/CalendarHeatmap.svelte';
	import {
		cachedQuery,
		classOf,
		divColors,
		hexAnomalies,
		quantileBreaks,
		seqColors,
		stepColor,
		type HexAnomaly,
		type RGBA,
		type Tool
	} from '#lib/map/helpers.ts';

	let meta = $state<Meta | null>(null);
	let fatal = $state('');

	// Area: follows the map view until the user draws or picks one.
	let follow = $state(true);
	let area = $state<Area | null>(null);
	let areaName = $state('Map view');
	let clipped = $state(false);
	let month = $state<YearMonth>('');
	let baseline = $state<Baseline>('median');
	let mode = $state<'anomaly' | 'firedays'>('anomaly');
	let tool = $state<Tool>('move');
	let mapReady = $state(false);

	let data = $state<QueryResponse | null>(null);
	let busy = $state(false);
	let notice = $state('');
	let hexes = $state<HexAnomaly[]>([]);
	let hexState = $state<'idle' | 'loading' | 'done' | 'skipped'>('idle');
	let hexWhy = $state('');
	let hexProgress = $state(0);
	let picked = $state<HexAnomaly | null>(null);
	let sheet = $state<'' | 'area' | 'calendar' | 'download'>('');
	let fitKey = $state('');

	let seq = 0;
	let hexSeq = 0;
	const MAX_HEX_COMPARE = 6000;

	onMount(async () => {
		try {
			const m = await fetchMeta();
			meta = m;
			month = m.in_progress ? prevMonth(m.series_end) : m.series_end;
			// Search the opening view straight away; the map's first "moved" event refines it once tiles load.
			area = { bbox: startBox(m) };
		} catch (e) {
			fatal = `Could not load firecal data: ${e instanceof Error ? e.message : String(e)}`;
		}
	});

	const startBox = (m: Meta): BBox => (isGlobal(m) ? (m.presets[0]?.bbox ?? m.region.bbox) : m.region.bbox);

	function prevMonth(m: YearMonth): YearMonth {
		let [y, mm] = m.split('-').map(Number);
		mm--;
		if (mm < 1) {
			mm = 12;
			y--;
		}
		return `${y}-${String(mm).padStart(2, '0')}`;
	}
	function nextMonth(m: YearMonth): YearMonth {
		let [y, mm] = m.split('-').map(Number);
		mm++;
		if (mm > 12) {
			mm = 1;
			y++;
		}
		return `${y}-${String(mm).padStart(2, '0')}`;
	}

	function onview(bbox: BBox, wasClipped: boolean) {
		if (!follow) return;
		area = { bbox };
		areaName = 'Map view';
		clipped = wasClipped;
	}
	function setArea(a: Area, name: string) {
		follow = false;
		area = a;
		areaName = name;
		clipped = false;
		sheet = '';
		fitKey = JSON.stringify(a);
	}
	function followMap() {
		follow = true;
		fitKey = '';
		// The next moveend sets the area; nudge one now so the view is searched straight away.
		mapApi?.viewNow() && onview(mapApi.viewNow()!.bbox, mapApi.viewNow()!.clipped);
	}
	let mapApi = $state<{ viewNow(): { bbox: BBox; clipped: boolean } | null } | null>(null);

	// The area's whole series (for the strip, the calendar and the answer), plus this month's hexagons.
	$effect(() => {
		if (!meta || !area || !month) return;
		const req = { area: $state.snapshot(area) as Area, start: meta.series_start, end: meta.series_end, month, baseline };
		const my = ++seq;
		busy = true;
		cachedQuery(req)
			.then((res) => {
				if (my !== seq) return;
				data = res;
				notice = '';
				picked = null;
			})
			.catch((e) => {
				if (my === seq) notice = `The search failed: ${e instanceof Error ? e.message : String(e)}`;
			})
			.finally(() => {
				if (my === seq) busy = false;
			});
	});

	// Per-hexagon comparison: one search per comparison year (the API has no per-hexagon baseline yet).
	$effect(() => {
		const d = data;
		const a = area;
		if (!d || !a || mode !== 'anomaly') return;
		const my = ++hexSeq;
		const row = d.months.find((m) => m.month === d.stats.month);
		if (row?.in_progress) {
			hexState = 'skipped';
			hexWhy = `${monthLabel(d.stats.month)} is still in progress, and hexagons can only be compared on whole months. The area total above compares the same days.`;
			return;
		}
		if (d.cells.length > MAX_HEX_COMPARE) {
			hexState = 'skipped';
			hexWhy = `Too many hexagons to compare one by one (${fmt(d.cells.length)}). Zoom in, or switch to fire-days.`;
			return;
		}
		hexState = 'loading';
		hexProgress = 0;
		const current = d.cells.map((c) => ({ h3: c.h3, month: c.month }));
		hexAnomalies($state.snapshot(a) as Area, d.stats.month, current, d.stats.baseline_years, d.stats.baseline, (n, t) => {
			if (my === hexSeq) hexProgress = n / t;
		})
			.then((h) => {
				if (my !== hexSeq) return;
				hexes = h;
				hexState = 'done';
			})
			.catch((e) => {
				if (my !== hexSeq) return;
				hexState = 'skipped';
				hexWhy = `Hexagon comparison failed: ${e instanceof Error ? e.message : String(e)}`;
			});
	});

	// What the map draws.
	const showAnomaly = $derived(mode === 'anomaly' && hexState === 'done');
	type Hex = HexAnomaly;
	const fireHexes = $derived<Hex[]>(
		(data?.cells ?? [])
			.filter((c) => c.month > 0)
			.map((c) => ({ h3: c.h3, value: c.month, usual: NaN, ratio: null, category: 'about usual', isNew: false }))
	);
	const mapHexes = $derived<Hex[]>(showAnomaly ? hexes : fireHexes);
	const breaks = $derived(quantileBreaks(fireHexes.map((h) => h.value)));
	let palette = $state<{ seq: ReturnType<typeof seqColors>; div: ReturnType<typeof divColors> } | null>(null);
	$effect(() => {
		if (mapReady) palette = { seq: seqColors(), div: divColors() };
	});
	const fill = $derived.by(() => {
		const p = palette;
		const b = breaks;
		if (!p) return (): RGBA => [0, 0, 0, 0];
		if (showAnomaly) return (d: Hex): RGBA => [...p.div[d.category], d.value === 0 ? 140 : 200];
		return (d: Hex): RGBA => [...stepColor(classOf(d.value, b), b.length + 1, p.seq), 200];
	});
	const fillKey = $derived(`${showAnomaly}|${breaks.join(',')}|${!!palette}|${hexes.length}`);

	function tooltip(d: Hex): string {
		const m = data ? monthLabel(data.stats.month) : '';
		if (!showAnomaly) return `<b>${fmt1(d.value)}</b> fire-days in ${m}`;
		const usual = `${data?.stats.baseline === 'mean' ? 'average' : 'median'} ${fmt1(d.usual)}`;
		const line =
			d.isNew ? 'Fire here, where this month usually has none' : d.value === 0 ? 'No fire here this month' : `${fmt1(d.ratio!)}× the usual`;
		return `<b>${CATEGORY_GLYPH[d.category]} ${line}</b><br>${fmt1(d.value)} fire-days in ${m}<br>Usual: ${usual} fire-days`;
	}

	// Answer.
	const s = $derived(data?.stats);
	const row = $derived(data?.months.find((m) => m.month === s?.month));
	const anoms = $derived(data ? anomalies(data.months) : new Map<string, Anomaly>());
	const strip = $derived(meta && data ? data.months.slice(-24) : []);
	const stripMax = $derived(Math.max(1, ...strip.map((m) => m.value)));

	const hexCounts = $derived.by(() => {
		const out: Record<string, number> = {};
		for (const h of hexes) out[h.category] = (out[h.category] ?? 0) + 1;
		return out;
	});
	const hotter = $derived(
		hexes.filter((h) => h.category === 'higher than usual' || h.category === 'much higher than usual').length
	);

	// Downloads.
	const fileBase = $derived(data ? `firecal-${areaName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${data.stats.month}` : 'firecal');
	let exporting = $state(false);
	let exportMsg = $state('');
	function hexAnomalyCsv(): string {
		const lines = ['hex_id,month,fire_days,usual,ratio,category'];
		for (const h of hexes) lines.push([h.h3, data!.stats.month, h.value, h.usual, h.ratio ?? '', `"${h.category}"`].join(','));
		return lines.join('\n') + '\n';
	}
	async function hotspots() {
		if (!data || !area) return;
		exporting = true;
		exportMsg = '';
		try {
			const blob = await exportHotspots({ area: $state.snapshot(area) as Area, start: data.stats.month, end: data.stats.month });
			downloadBlob(`${fileBase}-hotspots.csv`, blob);
		} catch (e) {
			exportMsg = e instanceof Error ? e.message : String(e);
		} finally {
			exporting = false;
		}
	}

	const months = $derived(meta ? monthRange(meta.series_start, meta.series_end) : []);
	const fmtShare = (v: number | null | undefined) => (v == null ? 'all' : `${Math.round(v * 100)} %`);
</script>

<svelte:head><title>firecal · Now (prototype A)</title></svelte:head>

<div class="proto">
	{#if fatal}
		<p class="glass fatal" role="alert">{fatal}</p>
	{:else if meta}
		<FullMap
			bind:this={mapApi}
			{meta}
			hexes={mapHexes}
			{fill}
			{fillKey}
			ring={follow ? null : (data?.area.ring ?? null)}
			fitKey={follow ? '' : fitKey && data ? fitKey + JSON.stringify(data.area.ring[0]) : ''}
			{tooltip}
			onhex={(d) => (picked = d)}
			onarea={setArea}
			{onview}
			bind:tool
			bind:ready={mapReady}
			padding={{ top: 220, right: 40, bottom: 150, left: 40 }}
			initialBbox={startBox(meta)}
		/>

		{#if busy || hexState === 'loading'}
			<div class="progress" role="progressbar" aria-label="Loading" aria-valuemin={0} aria-valuemax={100} aria-valuenow={hexState === 'loading' ? Math.round(hexProgress * 100) : undefined}>
				<i style="width:{hexState === 'loading' ? 15 + hexProgress * 85 : 40}%"></i>
			</div>
		{/if}

		<!-- Answer card -->
		<section class="glass answer" aria-live="polite" aria-labelledby="answer-h">
			<div class="row top">
				<span class="brand">firecal <b>Now</b></span>
				<span class="area-chip" title={areaName}>
					{#if follow}<span class="dot"></span> Searching the map view{:else}{areaName}{/if}
				</span>
			</div>
			<div class="row month">
				<button class="pbtn icon" type="button" aria-label="Previous month" disabled={month <= meta.series_start} onclick={() => (month = prevMonth(month))}>‹</button>
				<label class="sr" for="mon">Month</label>
				<select id="mon" bind:value={month}>
					{#each [...months].reverse() as m (m)}<option value={m}>{monthLabel(m)}{m === meta.in_progress?.month ? ' (so far)' : ''}</option>{/each}
				</select>
				<button class="pbtn icon" type="button" aria-label="Next month" disabled={month >= meta.series_end} onclick={() => (month = nextMonth(month))}>›</button>
			</div>
			{#if s}
				<h1 id="answer-h" class="sr">How unusual is {monthLabel(s.month)}?</h1>
				{#if s.category}
					<p class="verdict" style="background:{CATEGORY_VAR[s.category]};color:{CATEGORY_INK[s.category]}">
						<span aria-hidden="true">{CATEGORY_GLYPH[s.category]}</span>
						{s.category[0].toUpperCase() + s.category.slice(1)}
						{#if s.ratio != null}<span class="ratio">{fmt1(s.ratio)}×</span>{/if}
					</p>
				{/if}
				<p class="sentence">{s.sentence}</p>
				<p class="fine">
					{#if s.lower != null}80 % range {fmt(s.lower)}–{fmt(s.upper)} · {/if}{SOURCE_LABEL[s.source]}{#if row && !row.complete && !row.in_progress} · {row.days_with_data} of {row.days} days with data{/if}
					{#if meta && isGlobal(meta) && data?.continent && data.continent !== 'World'}
						· {continentName(data.continent)} model ({fmtShare(data.continent_share)})
					{/if}
				</p>
				{#if mode === 'anomaly' && hexState === 'done' && hexes.length}
					<p class="fine hexline">
						<b>{fmt(hotter)}</b> of {fmt(hexes.length)} hexagons with fire now or usually are above their usual {monthLabel(s.month).split(' ')[0]}.
					</p>
				{/if}
			{:else}
				<p class="sentence muted">Loading…</p>
			{/if}
			<div class="row actions">
				<button class="pbtn" type="button" aria-expanded={sheet === 'calendar'} onclick={() => (sheet = sheet === 'calendar' ? '' : 'calendar')} disabled={!data}>Burning calendar</button>
				<button class="pbtn" type="button" aria-expanded={sheet === 'download'} onclick={() => (sheet = sheet === 'download' ? '' : 'download')} disabled={!data}>Download</button>
			</div>
			{#if notice}<p class="warn" role="alert">{notice}</p>{/if}
			{#if clipped && follow}<p class="fine">The view is wider than 180°, so the middle 180° is searched.</p>{/if}
		</section>

		<!-- Tools -->
		<nav class="glass tools" aria-label="Area and tools">
			<div class="seg" role="group" aria-label="Colour hexagons by">
				<button type="button" aria-pressed={mode === 'anomaly'} onclick={() => (mode = 'anomaly')}>vs usual</button>
				<button type="button" aria-pressed={mode === 'firedays'} onclick={() => (mode = 'firedays')}>Fire-days</button>
			</div>
			<div class="seg" role="group" aria-label="Usual means the">
				<button type="button" aria-pressed={baseline === 'median'} onclick={() => (baseline = 'median')} title="Usual = median of other years (steadier)">Median</button>
				<button type="button" aria-pressed={baseline === 'mean'} onclick={() => (baseline = 'mean')} title="Usual = average of other years">Mean</button>
			</div>
			<span class="sep" aria-hidden="true"></span>
			<button class="pbtn" type="button" aria-pressed={follow} onclick={followMap} title="Search whatever the map shows">Map view</button>
			<button class="pbtn" type="button" aria-pressed={tool === 'rectangle'} onclick={() => (tool = tool === 'rectangle' ? 'move' : 'rectangle')}>▭ Box</button>
			<button class="pbtn" type="button" aria-pressed={tool === 'polygon'} onclick={() => (tool = tool === 'polygon' ? 'move' : 'polygon')}>⬠ Polygon</button>
			<button class="pbtn" type="button" aria-pressed={tool === 'circle'} onclick={() => (tool = tool === 'circle' ? 'move' : 'circle')}>◯ Circle</button>
			<button class="pbtn" type="button" aria-expanded={sheet === 'area'} onclick={() => (sheet = sheet === 'area' ? '' : 'area')}>Places & coordinates</button>
		</nav>
		{#if tool !== 'move'}
			<p class="glass drawhint" role="status">
				{tool === 'polygon' ? 'Click each corner; click the first point or press Enter to finish.' : 'Press and drag on the map.'} Esc cancels.
			</p>
		{/if}

		<!-- Picked hexagon -->
		{#if picked && data}
			<aside class="glass picked" aria-label="Selected hexagon">
				<button class="close" type="button" aria-label="Close" onclick={() => (picked = null)}>×</button>
				<p class="p-h">Hexagon {picked.h3}</p>
				<p><b>{fmt1(picked.value)}</b> fire-days in {monthLabel(data.stats.month)}</p>
				{#if !Number.isNaN(picked.usual)}
					<p>Usual {monthLabel(data.stats.month).split(' ')[0]}: {fmt1(picked.usual)} ({data.stats.baseline} of {data.stats.baseline_years.length} years)</p>
					<p>
						<span class="swatch" style="background:{CATEGORY_VAR[picked.category]}"></span>
						{CATEGORY_GLYPH[picked.category]} {picked.isNew ? 'new fire: usually none here' : picked.category}
					</p>
				{/if}
			</aside>
		{/if}

		<!-- Legend + strip -->
		<footer class="glass bottom">
			<div class="legend" aria-label="Map legend">
				{#if showAnomaly}
					<span class="lt">Each hexagon vs its usual {s ? monthLabel(s.month).split(' ')[0] : ''}:</span>
					{#each CATEGORY_ORDER as c (c)}
						<span class="li"><i class="swatch" style="background:{CATEGORY_VAR[c]}"></i>{CATEGORY_GLYPH[c]} {c.replace(' than usual', '')} <small>{fmt(hexCounts[c] ?? 0)}</small></span>
					{/each}
				{:else}
					<span class="lt">Fire-days per hexagon{s ? `, ${monthLabel(s.month)}` : ''}:</span>
					{#each Array.from({ length: breaks.length + 1 }, (_, i) => i) as i (i)}
						<span class="li"
							><i class="swatch" style="background:var(--seq-{Math.round((i * 6) / Math.max(1, breaks.length)) + 1})"></i>{i === 0
								? `under ${fmt1(breaks[0] ?? 0)}`
								: i === breaks.length
									? `${fmt1(breaks[i - 1])}+`
									: `${fmt1(breaks[i - 1])}–${fmt1(breaks[i])}`}</span
						>
					{/each}
				{/if}
				{#if mode === 'anomaly' && hexState === 'loading'}<span class="li muted">Comparing each hexagon with {s?.baseline_years.length} years… {Math.round(hexProgress * 100)} %</span>{/if}
				{#if mode === 'anomaly' && hexState === 'skipped'}<span class="li muted">{hexWhy}</span>{/if}
			</div>
			{#if strip.length}
				<div class="strip" role="group" aria-label="Last 24 months, coloured by how each compares with its usual month">
					{#each strip as m (m.month)}
						{@const a = anoms.get(m.month)}
						<button
							type="button"
							class="bar"
							class:sel={m.month === s?.month}
							aria-pressed={m.month === s?.month}
							aria-label="{monthLabel(m.month)}: {fmt(m.value)} fire-days{a ? `, ${a.category}` : m.in_progress ? ', in progress' : ''}"
							title="{monthLabel(m.month)}: {fmt(m.value)} fire-days{a ? ` · ${a.category}` : ''}"
							onclick={() => (month = m.month)}
						>
							<i style="height:{Math.max(3, (m.value / stripMax) * 100)}%;background:{a ? CATEGORY_VAR[a.category] : 'var(--seq-0)'}" class:prog={m.in_progress}></i>
							<span>{m.month.endsWith('-01') ? m.month.slice(0, 4) : monthShortLabel(m.month).slice(0, 1)}</span>
						</button>
					{/each}
				</div>
			{/if}
		</footer>

		<!-- Sheets -->
		{#if sheet}
			<div class="glass sheet scroll" role="dialog" aria-label={sheet === 'area' ? 'Choose an area' : sheet === 'calendar' ? 'Burning calendar' : 'Downloads'}>
				<button class="close" type="button" aria-label="Close" onclick={() => (sheet = '')}>×</button>
				{#if sheet === 'area'}
					<p class="p-h">Choose an area</p>
					<AreaPicker {meta} area={area ?? { bbox: meta.region.bbox }} onarea={setArea} />
				{:else if sheet === 'calendar' && data}
					<CalendarHeatmap months={data.months} selected={data.stats.month} onselect={(m) => (month = m)} filename="{fileBase}-calendar" {busy} />
				{:else if sheet === 'download' && data}
					<p class="p-h">Downloads</p>
					<div class="dl">
						<button class="pbtn primary" type="button" onclick={() => downloadBlob(`${fileBase}-monthly.csv`, new Blob([monthsToCsv(data!.months)], { type: 'text/csv' }))}
							>Monthly series CSV ({data.months.length} months)</button
						>
						<button class="pbtn" type="button" disabled={hexState !== 'done'} onclick={() => downloadBlob(`${fileBase}-hexagons-vs-usual.csv`, new Blob([hexAnomalyCsv()], { type: 'text/csv' }))}
							>Hexagons vs usual CSV</button
						>
						<button class="pbtn" type="button" onclick={() => downloadBlob(`${fileBase}-hexagons.csv`, new Blob([cellsToCsv(data!)], { type: 'text/csv' }))}
							>Hexagon CSV for Kepler.gl</button
						>
						{#if meta.export_limit != null}
							<button class="pbtn" type="button" disabled={exporting} onclick={hotspots}>{exporting ? 'Preparing…' : `Hotspots CSV, ${monthLabel(data.stats.month)}`}</button>
						{/if}
					</div>
					{#if exportMsg}<p class="warn">{exportMsg}</p>{/if}
					<p class="fine">Charts in the calendar have their own SVG and PNG buttons. <a href="/">Methods and full charts</a></p>
				{/if}
			</div>
		{/if}
	{:else}
		<p class="glass fatal" role="status">Loading…</p>
	{/if}
</div>

<style>
	.fatal {
		position: absolute;
		top: 40%;
		left: 50%;
		transform: translateX(-50%);
		padding: 12px 16px;
	}
	.progress {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 3px;
		z-index: 5;
	}
	.progress i {
		display: block;
		height: 100%;
		background: var(--accent);
		transition: width 0.3s;
	}
	.answer {
		position: absolute;
		top: 12px;
		left: 12px;
		width: min(400px, calc(100vw - 24px));
		padding: 12px 14px;
		z-index: 2;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.top {
		justify-content: space-between;
		margin-bottom: 8px;
	}
	.brand {
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.brand b {
		color: var(--text);
	}
	.area-chip {
		font-size: 0.78rem;
		color: var(--text-2);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 60%;
	}
	.dot {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--era-viirs);
		margin-right: 2px;
	}
	.month select {
		flex: 1;
		min-height: 34px;
		font: inherit;
		font-weight: 600;
		font-size: 1rem;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
		padding: 0 8px;
	}
	.icon {
		width: 34px;
		justify-content: center;
		font-size: 1.1rem;
		padding: 0;
	}
	.verdict {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		margin: 10px 0 6px;
		padding: 6px 12px;
		border-radius: 8px;
		font-weight: 700;
		font-size: 1.05rem;
		outline: 1px solid var(--border);
	}
	.ratio {
		font-variant-numeric: tabular-nums;
		opacity: 0.9;
	}
	.sentence {
		margin: 4px 0;
		font-size: 0.95rem;
		line-height: 1.4;
	}
	.fine {
		margin: 4px 0 0;
		font-size: 0.78rem;
		color: var(--text-2);
	}
	.actions {
		margin-top: 10px;
	}
	.hexline {
		color: var(--text);
	}
	.muted {
		color: var(--text-2);
	}
	.warn {
		margin: 6px 0 0;
		padding: 6px 8px;
		border-radius: 6px;
		background: var(--warn-bg);
		border: 1px solid var(--warn-border);
		font-size: 0.82rem;
	}
	.tools {
		position: absolute;
		top: 12px;
		right: 12px;
		max-width: calc(100vw - min(400px, 100vw - 24px) - 36px);
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		align-items: center;
		gap: 6px;
		padding: 8px;
		z-index: 2;
	}
	.sep {
		width: 1px;
		height: 22px;
		background: var(--border);
	}
	.drawhint {
		position: absolute;
		top: 72px;
		right: 12px;
		margin: 0;
		padding: 6px 10px;
		font-size: 0.82rem;
		z-index: 2;
	}
	.picked {
		position: absolute;
		right: 60px;
		bottom: 170px;
		width: 260px;
		padding: 10px 12px;
		z-index: 3;
		font-size: 0.85rem;
	}
	.picked p {
		margin: 2px 0;
	}
	.close {
		position: absolute;
		top: 6px;
		right: 8px;
		border: 0;
		background: transparent;
		color: var(--text-2);
		font-size: 1.2rem;
		cursor: pointer;
	}
	.bottom {
		position: absolute;
		left: 12px;
		right: 60px;
		bottom: 12px;
		padding: 8px 12px 6px;
		z-index: 2;
		max-width: 980px;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 12px;
		font-size: 0.76rem;
		color: var(--text-2);
		margin-bottom: 6px;
	}
	.lt {
		color: var(--text);
		font-weight: 600;
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.li small {
		color: var(--muted);
	}
	.strip {
		display: grid;
		grid-template-columns: repeat(24, minmax(14px, 1fr));
		gap: 2px;
		height: 64px;
	}
	.bar {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		align-items: stretch;
		border: 0;
		padding: 0 0 14px;
		background: transparent;
		cursor: pointer;
		border-radius: 4px;
	}
	.bar:hover {
		background: var(--wash);
	}
	.bar i {
		display: block;
		border-radius: 3px 3px 0 0;
	}
	.bar i.prog {
		background-image: repeating-linear-gradient(45deg, transparent 0 3px, var(--hatch) 3px 4px) !important;
	}
	.bar.sel {
		outline: 2px solid var(--text);
		outline-offset: 1px;
	}
	.bar span {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		font-size: 0.62rem;
		color: var(--text-2);
		text-align: center;
	}
	.sheet {
		position: absolute;
		top: 72px;
		right: 12px;
		width: min(560px, calc(100vw - 24px));
		max-height: calc(100vh - 260px);
		padding: 12px 14px;
		z-index: 4;
	}
	.dl {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 8px;
	}
	@media (max-width: 760px) {
		.tools {
			top: auto;
			bottom: 120px;
			left: 12px;
			right: 12px;
			justify-content: flex-start;
			overflow-x: auto;
			flex-wrap: nowrap;
			max-width: none;
		}
		.tools > :global(*) {
			flex-shrink: 0;
			white-space: nowrap;
		}
		.answer {
			max-height: 44vh;
			overflow: auto;
		}
		.bottom {
			right: 12px;
		}
		.legend {
			display: none;
		}
		.sheet {
			top: auto;
			bottom: 172px;
			max-height: 55vh;
		}
		.picked {
			right: 12px;
			bottom: 180px;
		}
	}
</style>
