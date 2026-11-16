<script lang="ts">
	// Prototype C · Seasons: for land managers and planners. The burning calendar, docked under the
	// map, is the time control: a month or a year goes on the map, or the change between two years.
	import '../../../app.css';
	import '#lib/panels.css';
	import { onMount } from 'svelte';
	import { exportHotspots, fetchMeta } from '#lib/api.ts';
	import { cellsToCsv, downloadBlob, monthsToCsv } from '#lib/download.ts';
	import { continentName, fmt1, isGlobal, monthLabel } from '#lib/format.ts';
	import { CATEGORY_GLYPH, CATEGORY_ORDER, categoryOf } from '#lib/scales.ts';
	import type { Area, BBox, Baseline, Category, Meta, QueryResponse, YearMonth } from '#lib/types.ts';
	import AreaPicker from '#lib/components/AreaPicker.svelte';
	import AnswerCard from '#lib/components/AnswerCard.svelte';
	import YearlyBars from '#lib/components/YearlyBars.svelte';
	import FullMap from '#lib/map/FullMap.svelte';
	import SeasonCalendar from '#lib/proto/seasons/SeasonCalendar.svelte';
	import SeasonProfile from '#lib/proto/seasons/SeasonProfile.svelte';
	import { cachedQuery, classOf, divColors, quantileBreaks, seqColors, stepColor, type RGBA, type Tool } from '#lib/map/helpers.ts';

	type Mode = 'month' | 'year' | 'change';
	interface Hex {
		h3: string;
		v: number;
		a?: number;
		ratio?: number | null;
		cat?: Category;
	}

	let meta = $state<Meta | null>(null);
	let fatal = $state('');
	let area = $state<Area>({ preset: 'argentina-box' });
	let areaName = $state('Study region');
	let baseline = $state<Baseline>('median');
	let mode = $state<Mode>('month');
	let month = $state<YearMonth>('');
	let year = $state(0);
	let yearA = $state(0);
	let yearB = $state(0);

	let main = $state<QueryResponse | null>(null);
	let mainName = $state('');
	let mainArea: Area | null = null;
	let yearData = $state<QueryResponse | null>(null);
	let pair = $state<[QueryResponse, QueryResponse] | null>(null);
	let busyMain = $state(false);
	let busyMap = $state(false);
	let notice = $state('');

	let tool = $state<Tool>('move');
	let mapReady = $state(false);
	let mapRef = $state<{ viewNow: () => { bbox: BBox; clipped: boolean } | null } | undefined>();
	let areaOpen = $state(false);
	let sideOpen = $state(true);
	let dark = $state(false);

	onMount(() => {
		sideOpen = window.innerWidth > 760;
		const mq = window.matchMedia('(prefers-color-scheme: dark)');
		const sync = () => (dark = document.documentElement.dataset.theme === 'dark' || (mq.matches && document.documentElement.dataset.theme !== 'light'));
		sync();
		mq.addEventListener('change', sync);
		fetchMeta()
			.then((m) => {
				meta = m;
				month = m.series_end;
				const last = Number(m.series_end.slice(0, 4));
				const lastFull = m.series_end.endsWith('-12') && !m.in_progress ? last : last - 1;
				year = lastFull;
				yearB = lastFull;
				yearA = Math.max(Number(m.series_start.slice(0, 4)), lastFull - 1);
				const first = m.presets.find((p) => p.id === 'argentina-box') ?? m.presets[0];
				if (first) {
					area = { preset: first.id };
					areaName = first.name;
				}
			})
			.catch((e) => (fatal = `Could not load firecal data: ${e instanceof Error ? e.message : String(e)}`));
		return () => mq.removeEventListener('change', sync);
	});

	/** The months of year y that the series has. */
	function yearSpan(y: number): { start: YearMonth; end: YearMonth } {
		const s = `${y}-01`;
		const e = `${y}-12`;
		return { start: meta && s < meta.series_start ? meta.series_start : s, end: meta && e > meta.series_end ? meta.series_end : e };
	}
	const partial = (y: number) => {
		const s = yearSpan(y);
		return !s.start.endsWith('-01') || !s.end.endsWith('-12') || (meta?.in_progress?.month ?? '') === s.end;
	};
	const err = (e: unknown) => `The search failed: ${e instanceof Error ? e.message : String(e)}`;

	// The whole series (calendar, season profile, yearly bars) and the selected month's stats and hexagons.
	let seqMain = 0;
	$effect(() => {
		if (!meta || !month) return;
		const a = $state.snapshot(area) as Area;
		const name = areaName;
		const my = ++seqMain;
		busyMain = true;
		cachedQuery({ area: a, start: meta.series_start, end: meta.series_end, month, baseline })
			.then((r) => {
				if (my !== seqMain) return;
				main = r;
				mainName = name;
				mainArea = a;
				notice = '';
			})
			.catch((e) => my === seqMain && (notice = err(e)))
			.finally(() => my === seqMain && (busyMain = false));
	});

	// Year total, or the two years to compare.
	let seqMap = 0;
	$effect(() => {
		if (!meta || mode === 'month') return;
		const a = $state.snapshot(area) as Area;
		const my = ++seqMap;
		const q = (y: number) => {
			const s = yearSpan(y);
			return cachedQuery({ area: a, start: s.start, end: s.end, month: s.end, baseline: 'median' });
		};
		busyMap = true;
		const job =
			mode === 'year'
				? q(year).then((r) => my === seqMap && (yearData = r))
				: Promise.all([q(yearA), q(yearB)]).then((rs) => my === seqMap && (pair = rs));
		job.catch((e) => my === seqMap && (notice = err(e))).finally(() => my === seqMap && (busyMap = false));
	});

	const hexes = $derived.by<Hex[]>(() => {
		if (mode === 'month') return (main?.cells ?? []).filter((c) => c.month > 0).map((c) => ({ h3: c.h3, v: c.month }));
		if (mode === 'year') return (yearData?.cells ?? []).filter((c) => c.range > 0).map((c) => ({ h3: c.h3, v: c.range }));
		if (!pair) return [];
		const A = new Map(pair[0].cells.filter((c) => c.range > 0).map((c) => [c.h3, c.range]));
		const B = new Map(pair[1].cells.filter((c) => c.range > 0).map((c) => [c.h3, c.range]));
		const out: Hex[] = [];
		for (const h3 of new Set([...A.keys(), ...B.keys()])) {
			const a = A.get(h3) ?? 0;
			const v = B.get(h3) ?? 0;
			const ratio = a > 0 ? v / a : null;
			out.push({ h3, v, a, ratio, cat: ratio == null ? 'much higher than usual' : categoryOf(ratio) });
		}
		return out;
	});

	const breaks = $derived(mode === 'change' ? [] : quantileBreaks(hexes.map((h) => h.v)));
	const seq = $derived.by(() => (void dark, mapReady ? seqColors() : []));
	const div = $derived.by(() => (void dark, mapReady ? divColors() : null));
	const fill = (h: Hex): RGBA => {
		if (mode === 'change') return [...(div?.[h.cat!] ?? [128, 128, 128]), 235];
		return [...(seq.length ? stepColor(classOf(h.v, breaks), breaks.length + 1, seq) : [128, 128, 128]), 230] as RGBA;
	};
	const fillKey = $derived(`${mode}|${breaks.join(',')}|${dark}|${mapReady}|${hexes.length}|${month}|${year}|${yearA}|${yearB}`);

	const CHANGE_LABEL: Record<Category, string> = {
		'much lower than usual': 'under 0.5× (much less)',
		'lower than usual': '0.5–0.8× (less)',
		'about usual': '0.8–1.25× (about the same)',
		'higher than usual': '1.25–2× (more)',
		'much higher than usual': '2× or more, or new fire'
	};
	const seqVarOf = (i: number, k: number) => `var(--seq-${(k <= 1 ? 6 : Math.round((i * 6) / (k - 1))) + 1})`;
	const legend = $derived.by(() => {
		if (mode === 'change') return CATEGORY_ORDER.map((c, i) => ({ label: `${CATEGORY_GLYPH[c]} ${CHANGE_LABEL[c]}`, color: ['--div-mlo', '--div-lo', '--div-mid', '--div-hi', '--div-mhi'].map((v) => `var(${v})`)[i] }));
		const k = breaks.length + 1;
		return Array.from({ length: k }, (_, i) => ({
			label: breaks.length === 0 ? 'any' : i === 0 ? `under ${fmt1(breaks[0])}` : i === breaks.length ? `${fmt1(breaks[i - 1])}+` : `${fmt1(breaks[i - 1])}–${fmt1(breaks[i])}`,
			color: seqVarOf(i, k)
		}));
	});
	const inProg = $derived(meta?.in_progress?.month === month);
	const mapTitle = $derived(
		mode === 'month'
			? `Fire-days in ${monthLabel(month)}${inProg ? ' so far' : ''}`
			: mode === 'year'
				? `Fire-days in ${year}${partial(year) ? ` (${monthLabel(yearSpan(year).start)} to ${monthLabel(yearSpan(year).end)} only)` : ''}`
				: `Change in fire-days, ${yearB} against ${yearA}`
	);

	const tooltip = (h: Hex): string => {
		if (mode === 'month') return `<b>${fmt1(h.v)}</b> fire-days in ${monthLabel(month)}${inProg ? ' so far' : ''}`;
		if (mode === 'year') return `<b>${fmt1(h.v)}</b> fire-days in ${year}`;
		const r = h.ratio == null ? 'new fire (none in ' + yearA + ')' : `${fmt1(h.ratio)}× ${yearA}`;
		return `${yearA}: <b>${fmt1(h.a)}</b> fire-days<br>${yearB}: <b>${fmt1(h.v)}</b> fire-days<br>${CATEGORY_GLYPH[h.cat!]} ${r}`;
	};

	const years = $derived.by(() => {
		if (!meta) return [] as number[];
		const a = Number(meta.series_start.slice(0, 4));
		const b = Number(meta.series_end.slice(0, 4));
		return Array.from({ length: b - a + 1 }, (_, i) => b - i);
	});

	function setArea(a: Area, name: string) {
		area = a;
		areaName = name;
		areaOpen = false;
	}
	function useView() {
		const v = mapRef?.viewNow();
		if (v) setArea({ bbox: v.bbox }, v.clipped ? 'Map view (middle 180°)' : 'Map view');
	}
	function drawWith(t: Tool) {
		tool = t;
		areaOpen = false;
	}
	function pickMonth(m: YearMonth) {
		month = m;
		mode = 'month';
	}
	function pickYear(y: number) {
		year = y;
		if (mode === 'change') yearB = y;
		else mode = 'year';
	}

	const fmtShare = (s: number | null | undefined) => (s == null ? 'all' : `${(s * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })} %`);
	const slug = (s: string) =>
		s
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '')
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-|-$/g, '')
			.slice(0, 40);
	const fileBase = $derived(`firecal-${slug(mainName || 'area')}`);

	function dlMonthly() {
		if (main) downloadBlob(`${fileBase}-monthly.csv`, new Blob([monthsToCsv(main.months)], { type: 'text/csv' }));
	}
	function dlHexes() {
		let csv: string;
		let name: string;
		if (mode === 'change' && pair) {
			const lines = [`hex_id,resolution,fire_days_${yearA},fire_days_${yearB},ratio,change`];
			for (const h of hexes) lines.push([h.h3, pair[1].area.resolution, h.a, h.v, h.ratio ?? '', h.cat].join(','));
			csv = lines.join('\n') + '\n';
			name = `${fileBase}-change-${yearA}-${yearB}-hexagons.csv`;
		} else if (mode === 'year' && yearData) {
			csv = cellsToCsv(yearData);
			name = `${fileBase}-${year}-hexagons.csv`;
		} else if (main) {
			csv = cellsToCsv(main);
			name = `${fileBase}-${month}-hexagons.csv`;
		} else return;
		downloadBlob(name, new Blob([csv], { type: 'text/csv' }));
	}
	const hotspotSpan = $derived(mode === 'month' ? { start: month, end: month } : yearSpan(mode === 'year' ? year : yearB));
	let exporting = $state(false);
	let exportMsg = $state('');
	async function dlHotspots() {
		exporting = true;
		exportMsg = '';
		try {
			const blob = await exportHotspots({ area: mainArea ?? ($state.snapshot(area) as Area), ...hotspotSpan });
			downloadBlob(`${fileBase}-hotspots-${hotspotSpan.start}_${hotspotSpan.end}.csv`, blob);
		} catch (e) {
			exportMsg = e instanceof Error ? e.message : String(e);
		} finally {
			exporting = false;
		}
	}
</script>

<svelte:head><title>firecal · Seasons (prototype C)</title></svelte:head>

<div class="proto" class:side={sideOpen}>
	{#if fatal}
		<p class="glass fatal" role="alert">{fatal}</p>
	{:else if meta}
		<div class="mapwrap">
			<FullMap
				bind:this={mapRef}
				bind:tool
				bind:ready={mapReady}
				{meta}
				{hexes}
				{fill}
				{fillKey}
				ring={main?.area.ring ?? null}
				fitKey={main ? JSON.stringify(main.area.ring) : ''}
				{tooltip}
				onarea={setArea}
				padding={{ top: 84, right: 24, bottom: 24, left: 24 }}
			/>

			<header class="bar glass">
				<a class="brand" href="/proto" title="All prototypes">firecal <span>Seasons</span></a>
				<div class="areabox">
					<button type="button" class="pbtn" aria-expanded={areaOpen} onclick={() => (areaOpen = !areaOpen)}>
						<span class="aname">{areaName}</span> ▾
					</button>
					{#if areaOpen}
						<div class="pop glass scroll" role="dialog" aria-label="Choose an area">
							<p class="p-h">Draw on the map</p>
							<div class="row">
								<button type="button" class="pbtn" onclick={() => drawWith('rectangle')}>Box</button>
								<button type="button" class="pbtn" onclick={() => drawWith('polygon')}>Polygon</button>
								<button type="button" class="pbtn" onclick={() => drawWith('circle')}>Circle</button>
								<button type="button" class="pbtn" onclick={useView}>Use map view</button>
							</div>
							<p class="p-h">Or pick / type one</p>
							<AreaPicker {meta} {area} onarea={setArea} />
						</div>
					{/if}
				</div>
				<div class="seg" role="group" aria-label="What the map shows">
					<button type="button" aria-pressed={mode === 'month'} onclick={() => (mode = 'month')}>Month</button>
					<button type="button" aria-pressed={mode === 'year'} onclick={() => (mode = 'year')}>Year total</button>
					<button type="button" aria-pressed={mode === 'change'} onclick={() => (mode = 'change')}>Change between years</button>
				</div>
				{#if mode === 'change'}
					<label class="sel">A <select bind:value={yearA}>{#each years as y (y)}<option value={y}>{y}{partial(y) ? '*' : ''}</option>{/each}</select></label>
					<span aria-hidden="true">→</span>
					<label class="sel">B <select bind:value={yearB}>{#each years as y (y)}<option value={y}>{y}{partial(y) ? '*' : ''}</option>{/each}</select></label>
				{/if}
				<button type="button" class="pbtn sidebtn" aria-expanded={sideOpen} onclick={() => (sideOpen = !sideOpen)}>{sideOpen ? 'Hide' : 'Show'} insights</button>
			</header>

			{#if tool !== 'move'}
				<p class="hint glass" role="status">
					{tool === 'rectangle' ? 'Drag a box' : tool === 'polygon' ? 'Click each corner; click the first point or press Enter to finish' : 'Drag out a circle'}. Esc cancels.
				</p>
			{/if}

			<div class="legend glass" aria-label="Map legend">
				<p class="lt">{mapTitle}{(busyMain && mode === 'month') || busyMap ? ' · loading…' : ''}</p>
				{#each legend as l, i (i)}
					<span class="li"><i class="swatch" style="background:{l.color}"></i>{l.label}</span>
				{/each}
				{#if mode === 'change' && (partial(yearA) || partial(yearB))}
					<p class="note">* A partial year: compare with care.</p>
				{/if}
				{#if hexes.length === 0 && !busyMain && !busyMap}<p class="note">No fire here for this choice.</p>{/if}
			</div>
		</div>

		<section class="dock glass" aria-label="Burning calendar">
			<div class="dock-h">
				<p class="p-h">Burning calendar · click a month or a year to map it</p>
				{#if notice}<p class="notice" role="alert">{notice}</p>{/if}
			</div>
			{#if main}
				<SeasonCalendar
					months={main.months}
					month={mode === 'month' ? month : ''}
					year={mode === 'year' ? year : 0}
					yearA={mode === 'change' ? yearA : 0}
					yearB={mode === 'change' ? yearB : 0}
					onmonth={pickMonth}
					onyear={pickYear}
					busy={busyMain}
				/>
			{:else}
				<p role="status">Loading the calendar…</p>
			{/if}
		</section>

		{#if sideOpen}
			<aside class="sidepanel glass scroll" aria-label="Insights">
				<button type="button" class="pbtn close" onclick={() => (sideOpen = false)} aria-label="Close insights">✕</button>
				<div class="base">
					<span class="p-h">"Usual" means the</span>
					<div class="seg" role="group" aria-label="Usual means">
						<button type="button" aria-pressed={baseline === 'median'} onclick={() => (baseline = 'median')}>Median</button>
						<button type="button" aria-pressed={baseline === 'mean'} onclick={() => (baseline = 'mean')}>Mean</button>
					</div>
				</div>
				{#if main}
					<AnswerCard data={main} areaName={mainName} busy={busyMain} />
					{#if isGlobal(meta) && main.continent}
						<p class="cont">
							{#if main.continent === 'World'}
								No fire here in any year, so no continent's model applies; days with data are counted for the whole globe.
							{:else if meta.continents?.[main.continent]?.fitted === false}
								{continentName(main.continent)} ({fmtShare(main.continent_share)} of this area's fire-days) has no model: too few fires to fit one, so months before February 2012 have no data.
							{:else}
								Converted with the {continentName(main.continent)} model, which holds {fmtShare(main.continent_share)} of this area's fire-days.
							{/if}
						</p>
					{/if}
					<div class="block">
						<SeasonProfile months={main.months} {baseline} year={mode === 'change' ? yearB : mode === 'year' ? year : Number(month.slice(0, 4))} filename="{fileBase}-season" />
					</div>
					<YearlyBars months={main.months} filename="{fileBase}-yearly" busy={busyMain} />
					<div class="block">
						<p class="p-h">Downloads</p>
						<div class="row">
							<button type="button" class="pbtn primary" onclick={dlMonthly}>Monthly CSV ({main.months.length} months)</button>
							<button type="button" class="pbtn" onclick={dlHexes} disabled={hexes.length === 0}>Hexagons on the map (CSV)</button>
							{#if meta.export_limit != null}
								<button type="button" class="pbtn" onclick={dlHotspots} disabled={exporting}>
									{exporting ? 'Preparing…' : `Hotspots ${monthLabel(hotspotSpan.start)}${hotspotSpan.end !== hotspotSpan.start ? ` to ${monthLabel(hotspotSpan.end)}` : ''}`}
								</button>
							{/if}
						</div>
						{#if exportMsg}<p class="notice" role="alert">{exportMsg}</p>{/if}
						<p class="small">
							The hexagon CSV opens in kepler.gl (H3 column <code>hex_id</code>). Charts have their own SVG and PNG buttons.
							{#if meta.export_limit == null}Hotspot rows for the global data come from <a href="https://firms.modaps.eosdis.nasa.gov/download/" target="_blank" rel="noopener noreferrer">NASA FIRMS</a>.{/if}
						</p>
					</div>
				{/if}
			</aside>
		{/if}
	{:else}
		<p class="glass fatal" role="status">Loading…</p>
	{/if}
</div>

<style>
	.proto {
		--side: 380px;
		--dock: 38vh;
	}
	.mapwrap {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: var(--dock);
	}
	.side .mapwrap,
	.side .dock {
		right: var(--side);
	}
	.bar {
		position: absolute;
		top: 10px;
		left: 10px;
		right: 10px;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		padding: 8px 10px;
		z-index: 3;
	}
	.brand {
		font-weight: 700;
		color: var(--text);
		text-decoration: none;
		margin-right: 4px;
	}
	.brand span {
		font-weight: 500;
		color: var(--accent);
	}
	.areabox {
		position: relative;
	}
	.aname {
		max-width: 22ch;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.pop {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		width: min(420px, calc(100vw - 40px));
		max-height: 60vh;
		padding: 12px;
		z-index: 5;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 10px;
	}
	.sel {
		font-size: 0.82rem;
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.sel select {
		font: inherit;
		min-height: 32px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
	}
	.sidebtn {
		margin-left: auto;
	}
	.hint {
		position: absolute;
		top: 72px;
		left: 50%;
		transform: translateX(-50%);
		margin: 0;
		padding: 6px 12px;
		font-size: 0.82rem;
		z-index: 3;
	}
	.legend {
		position: absolute;
		left: 10px;
		bottom: 10px;
		max-width: min(320px, calc(100% - 70px));
		padding: 8px 10px;
		font-size: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 3px;
		z-index: 2;
	}
	.legend .lt {
		margin: 0 0 2px;
		font-weight: 600;
		color: var(--text);
	}
	.legend .note {
		margin: 2px 0 0;
		color: var(--text-2);
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: var(--text-2);
	}
	.dock {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: var(--dock);
		border-radius: 0;
		border-width: 1px 0 0;
		padding: 8px 12px 10px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		box-sizing: border-box;
	}
	.dock-h {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.dock-h .p-h {
		margin: 0;
	}
	.notice {
		margin: 0;
		font-size: 0.8rem;
		background: var(--warn-bg);
		border: 1px solid var(--warn-border);
		border-radius: 6px;
		padding: 2px 8px;
	}
	.sidepanel {
		position: absolute;
		top: 0;
		right: 0;
		bottom: 0;
		width: var(--side);
		box-sizing: border-box;
		border-radius: 0;
		border-width: 0 0 0 1px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		z-index: 4;
	}
	.close {
		display: none;
		align-self: flex-end;
	}
	.base {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.base .p-h {
		margin: 0;
	}
	.cont {
		margin: 0;
		font-size: 0.8rem;
		color: var(--text-2);
	}
	.block {
		border-top: 1px solid var(--border);
		padding-top: 10px;
	}
	.small {
		font-size: 0.75rem;
		color: var(--text-2);
		margin: 0;
	}
	.sidepanel :global(.card) {
		padding: 12px;
		box-shadow: none;
	}
	.fatal {
		position: absolute;
		top: 40%;
		left: 50%;
		transform: translateX(-50%);
		padding: 12px 16px;
	}
	@media (max-width: 760px) {
		.proto {
			--dock: 42vh;
		}
		.side .mapwrap,
		.side .dock {
			right: 0;
		}
		.sidepanel {
			top: auto;
			left: 0;
			width: auto;
			max-height: 82vh;
			border-width: 1px 0 0;
			border-radius: 14px 14px 0 0;
			box-shadow: 0 -8px 30px rgba(0, 0, 0, 0.3);
		}
		.close {
			display: inline-flex;
		}
		.bar {
			gap: 6px;
			padding: 6px 8px;
		}
		.bar .seg button {
			padding: 4px 7px;
			font-size: 0.76rem;
		}
		.brand span {
			display: none;
		}
		.legend {
			max-width: calc(100% - 60px);
		}
	}
</style>
