<script lang="ts">
	// The fire season year by year: months along the bottom, one faint line per year, the usual year
	// (median or mean of complete years) in bold and the selected month's year highlighted. Unlike one
	// long monthly line, this reads the same for strongly seasonal areas and quiet ones.
	// "So far this season" shows each season's running total instead, so a season running ahead
	// or behind shows as a line above or below the others.
	import ChartFrame from './ChartFrame.svelte';
	import Tooltip, { type TipRow } from './Tooltip.svelte';
	import { MONTH_NAMES, MONTH_SHORT, fmt, fmtTick, median, monthLabel, monthNote } from '#lib/format.ts';
	import { linear, niceTicks } from '#lib/scales.ts';
	import type { Baseline, MonthRow, YearMonth } from '#lib/types.ts';

	interface Props {
		months: MonthRow[];
		selected: YearMonth;
		baseline: Baseline;
		filename: string;
		busy?: boolean;
		/** Area and dates, for saved images. */
		context?: string;
	}
	let { months, selected, baseline, filename, busy = false, context }: Props = $props();

	const calMonth = (m: MonthRow) => Number(m.month.slice(5)) - 1;
	const calYear = (m: MonthRow) => Number(m.month.slice(0, 4));

	/** Usual value of each calendar month, over complete months. */
	const typical = $derived(
		Array.from({ length: 12 }, (_, c) => {
			const xs = months.filter((m) => m.complete && calMonth(m) === c).map((m) => m.value);
			if (!xs.length) return null;
			return baseline === 'mean' ? xs.reduce((s, v) => s + v, 0) / xs.length : median(xs);
		})
	);

	/** First month of the season year: the month after the usual quietest, so a season that runs
	 *  through December is not split in two. January when nothing burns. */
	const start = $derived.by(() => {
		const v = typical.map((t) => t ?? 0);
		if (!(Math.max(...v) > 0)) return 0;
		return (v.indexOf(Math.min(...v)) + 1) % 12;
	});
	const order = $derived(Array.from({ length: 12 }, (_, i) => (start + i) % 12));
	const seasonOf = (m: MonthRow) => calYear(m) - (calMonth(m) < start ? 1 : 0);
	const label = (y: number) => (start === 0 ? String(y) : `${y}–${String(y + 1).slice(2)}`);

	type Season = { year: number; cells: (MonthRow | null)[] };
	const seasons = $derived.by(() => {
		const by = new Map<number, Season>();
		for (const m of months) {
			const y = seasonOf(m);
			if (!by.has(y)) by.set(y, { year: y, cells: Array(12).fill(null) });
			by.get(y)!.cells[(calMonth(m) - start + 12) % 12] = m;
		}
		return [...by.values()].sort((a, b) => a.year - b.year);
	});
	type Mode = 'month' | 'cum';
	let mode = $state<Mode>('month');

	/** Each season's running total from its first month; null from a missing month on, and for a
	 *  season that starts before the dates shown (its total so far is unknown). */
	function running(cells: (MonthRow | null)[]): (number | null)[] {
		let t = 0;
		let ok = true;
		return cells.map((m) => {
			if (!ok || !m) {
				ok = false;
				return null;
			}
			t += m.value;
			return t;
		});
	}
	/** Each season's values in the chosen mode. */
	const vals = $derived(new Map(seasons.map((s) => [s.year, mode === 'month' ? s.cells.map((m) => m?.value ?? null) : running(s.cells)])));
	const valsOf = (s: Season) => vals.get(s.year) ?? [];
	/** Whether a season's value at column i counts towards the usual and the highest/lowest:
	 *  that month is complete, and for a running total every month before it too. */
	const counts = (s: Season, i: number) =>
		valsOf(s)[i] !== null && (mode === 'month' ? !!s.cells[i]?.complete : s.cells.slice(0, i + 1).every((m) => m?.complete));
	const agg = (xs: number[]) => (!xs.length ? null : baseline === 'mean' ? xs.reduce((a, v) => a + v, 0) / xs.length : median(xs));
	/** The usual value at each column: per month as before; so far, the median (or mean) of the
	 *  complete seasons' running totals, which is not the running total of the monthly medians. */
	const usual = $derived(
		order.map((c, i) => (mode === 'month' ? typical[c] : agg(seasons.filter((s) => counts(s, i)).map((s) => valsOf(s)[i]!))))
	);

	const selRow = $derived(months.find((m) => m.month === selected) ?? null);
	const selSeason = $derived(selRow ? seasonOf(selRow) : null);
	const selCol = $derived(selRow ? (calMonth(selRow) - start + 12) % 12 : -1);

	let w = $state(600);
	const H = 260;
	const M = { top: 14, right: 12, bottom: 30, left: 44 };
	const innerW = $derived(Math.max(10, w - M.left - M.right));
	const innerH = H - M.top - M.bottom;
	const x = $derived(linear(0, 11, M.left, M.left + innerW));
	const yMax = $derived(Math.max(1, ...[...vals.values()].flat().map((v) => v ?? 0), ...usual.map((v) => v ?? 0)));
	const ticks = $derived(niceTicks(yMax, 4));
	const y = $derived(linear(0, ticks[ticks.length - 1], M.top + innerH, M.top));

	/** A path through the present values, broken where a month is missing. */
	function path(vals: (number | null)[]): string {
		let d = '';
		let pen = false;
		vals.forEach((v, i) => {
			if (v === null) {
				pen = false;
				return;
			}
			d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
			pen = true;
		});
		return d;
	}
	const usualPath = $derived(path(usual));
	const sel = $derived(seasons.find((s) => s.year === selSeason) ?? null);

	let active = $state<number | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let live = $state('');

	type Point = { s: Season; m: MonthRow; v: number };
	/** Which year or season a highest/lowest value belongs to. */
	const whose = (p: Point) => (mode === 'month' ? p.m.month.slice(0, 4) : label(p.s.year));
	function column(i: number) {
		const c = order[i];
		const pts: Point[] = seasons.filter((s) => counts(s, i)).map((s) => ({ s, m: s.cells[i]!, v: valsOf(s)[i]! }));
		const hi = pts.reduce<Point | null>((a, r) => (!a || r.v > a.v ? r : a), null);
		const lo = pts.reduce<Point | null>((a, r) => (!a || r.v < a.v ? r : a), null);
		const m = sel?.cells[i] ?? null;
		const v = sel ? valsOf(sel)[i] : null;
		return { c, usual: usual[i], cur: m && v !== null ? { m, v } : null, hi, lo };
	}
	const unit = $derived(mode === 'month' ? 'fire-days' : 'fire-days so far this season');
	function describe(i: number) {
		const k = column(i);
		let s = `${MONTH_NAMES[k.c]}: usual ${k.usual === null ? 'unknown' : fmt(k.usual)} ${unit}`;
		if (k.cur) s += `; ${monthLabel(k.cur.m.month)} ${fmt(k.cur.v)}`;
		if (k.hi) s += `; highest ${fmt(k.hi.v)} in ${whose(k.hi)}`;
		if (k.lo) s += `; lowest ${fmt(k.lo.v)} in ${whose(k.lo)}`;
		return s;
	}
	function onmove(e: PointerEvent) {
		const r = svgEl!.getBoundingClientRect();
		active = Math.max(0, Math.min(11, Math.round(((e.clientX - r.left - M.left) / innerW) * 11)));
	}
	function onkey(e: KeyboardEvent) {
		const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, Home: -12, End: 12 };
		if (e.key === 'Escape') {
			active = null;
			return;
		}
		if (!(e.key in step)) return;
		e.preventDefault();
		active = Math.max(0, Math.min(11, (active ?? (selCol >= 0 ? selCol : 0)) + step[e.key]));
		live = describe(active);
	}

	const tip = $derived.by(() => {
		if (active === null) return null;
		const k = column(active);
		const rows: TipRow[] = [];
		if (k.cur) rows.push({ value: fmt(k.cur.v), label: monthLabel(k.cur.m.month) + (k.cur.m.complete ? '' : ` (${monthNote(k.cur.m)})`), key: 'var(--line)' });
		if (k.usual !== null) rows.push({ value: fmt(k.usual), label: `usual (${baseline === 'mean' ? 'average' : 'median'})`, key: 'var(--text)' });
		if (k.hi) rows.push({ value: fmt(k.hi.v), label: `highest, ${whose(k.hi)}` });
		if (k.lo) rows.push({ value: fmt(k.lo.v), label: `lowest, ${whose(k.lo)}` });
		const top = Math.max(k.cur?.v ?? 0, k.usual ?? 0, k.hi?.v ?? 0);
		return { x: x(active), y: Math.min(y(top), H - 120), heading: mode === 'month' ? MONTH_NAMES[k.c] : `By the end of ${MONTH_NAMES[k.c]}`, rows };
	});

	const title = 'Fire season, year by year';
	const subtitle = $derived(
		(mode === 'month'
			? `Fire-days each month, one faint line per ${start === 0 ? 'year' : 'season'}. `
			: `Fire-days so far each ${start === 0 ? 'year' : 'season'}, added up month by month: a line above the dashed one is running ahead of usual. `) +
			(start === 0 ? '' : `Seasons run ${MONTH_NAMES[start]} to ${MONTH_NAMES[(start + 11) % 12]}, starting after the usually quietest month, so a season is not split at New Year. `) +
			'The dashed line is the usual year over these dates; the blue line is the year of the month in the answer card.'
	);
</script>

<ChartFrame id="season-cycle" {title} {subtitle} {filename} svg={svgEl} {busy} {context}>
	{#snippet controls()}
		<div class="seg" role="group" aria-label="Fire season: which numbers">
			<button type="button" class="btn" aria-pressed={mode === 'month'} onclick={() => (mode = 'month')}>Per month</button>
			<button type="button" class="btn" aria-pressed={mode === 'cum'} onclick={() => (mode = 'cum')}>So far this season</button>
		</div>
	{/snippet}
	{#snippet legend()}
		<span class="li"><svg width="18" height="10" aria-hidden="true"><line x1="0" x2="18" y1="5" y2="5" class="k-sel" /></svg>{sel ? label(sel.year) : 'Selected year'}</span>
		<span class="li"><svg width="18" height="10" aria-hidden="true"><line x1="0" x2="18" y1="5" y2="5" class="k-usual" /></svg>Usual ({baseline === 'mean' ? 'average' : 'median'})</span>
		<span class="li"><svg width="18" height="10" aria-hidden="true"><line x1="0" x2="18" y1="5" y2="5" class="k-other" /></svg>Other years</span>
	{/snippet}

	<div class="wrap" bind:clientWidth={w}>
		<!-- One tab stop; arrow keys move the readout month by month (announced via aria-live). -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
		<svg
			bind:this={svgEl}
			viewBox="0 0 {w} {H}"
			width={w}
			height={H}
			role="application"
			tabindex="0"
			aria-roledescription="line chart"
			aria-label="{title}, {mode === 'month' ? 'per month' : 'running total so far each season'}, {seasons.length} {start === 0 ? 'years' : 'seasons'}. Use the left and right arrow keys to read each month."
			onkeydown={onkey}
			onpointermove={onmove}
			onpointerleave={() => (active = null)}
			onblur={() => (active = null)}
		>
			{#each ticks as tk (tk)}
				<line class="grid" x1={M.left} x2={M.left + innerW} y1={y(tk)} y2={y(tk)} />
				<text class="axis" x={M.left - 6} y={y(tk)} text-anchor="end" dominant-baseline="central">{fmtTick(tk)}</text>
			{/each}
			{#each seasons as s (s.year)}
				{#if s.year !== selSeason}
					<path d={path(valsOf(s))} class="other" />
				{/if}
			{/each}
			<path d={usualPath} class="usual" />
			{#if sel}
				{@const sv = valsOf(sel)}
				<path d={path(sv)} class="sel-line" />
				{#each sel.cells as m, i (i)}
					{#if m && !m.complete && sv[i] !== null}<circle cx={x(i)} cy={y(sv[i]!)} r="3.5" class="inc" />{/if}
				{/each}
				{#if selCol >= 0 && sv[selCol] != null}<circle cx={x(selCol)} cy={y(sv[selCol]!)} r="5" class="ring" />{/if}
			{/if}
			{#each order as c, i (i)}
				<text class="axis" x={x(i)} y={H - M.bottom + 16} text-anchor="middle">{MONTH_SHORT[c]}</text>
			{/each}
			<line class="base" x1={M.left} x2={M.left + innerW} y1={M.top + innerH} y2={M.top + innerH} />
			{#if active !== null}
				<line data-export-skip class="cross" x1={x(active)} x2={x(active)} y1={M.top} y2={M.top + innerH} />
			{/if}
		</svg>
		{#if tip}
			<Tooltip x={tip.x} y={tip.y} parentWidth={w} heading={tip.heading} rows={tip.rows} />
		{/if}
	</div>
	<p class="sr-only" aria-live="polite">{live}</p>

	{#snippet notes()}
		{#if selRow}<p>The ringed point is the month described in the answer card ({monthLabel(selected)}); hollow points are incomplete months. The full monthly series, with ranges and counts, is in the table and the Data tab's CSV.</p>{/if}
		{#if mode === 'cum'}<p>A season that starts before the dates shown has no line here, since its total so far is unknown. The usual line is the {baseline === 'mean' ? 'average' : 'median'} of the complete seasons' totals at each month.</p>{/if}
	{/snippet}

	{#snippet table()}
		<table class="data">
			<caption class="sr-only">{title}: {mode === 'month' ? 'fire-days per month' : 'fire-days so far each season'}</caption>
			<thead>
				<tr>
					<th scope="col">{start === 0 ? 'Year' : 'Season'}</th>
					{#each order as c (c)}<th scope="col">{MONTH_SHORT[c]}</th>{/each}
				</tr>
			</thead>
			<tbody>
				<tr>
					<th scope="row">Usual</th>
					{#each usual as u, i (i)}<td>{u === null ? '–' : fmt(u)}</td>{/each}
				</tr>
				{#each seasons as s (s.year)}
					<tr>
						<th scope="row">{label(s.year)}</th>
						{#each s.cells as m, i (i)}<td>{m && valsOf(s)[i] !== null ? fmt(valsOf(s)[i]!) + (m.complete ? '' : '*') : '–'}</td>{/each}
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="small">* incomplete month</p>
	{/snippet}
</ChartFrame>

<style>
	.wrap {
		position: relative;
		width: 100%;
	}
	svg {
		display: block;
		touch-action: pan-y;
	}
	svg:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
		border-radius: 4px;
	}
	.grid {
		stroke: var(--grid);
	}
	.base {
		stroke: var(--axis);
	}
	.axis {
		font-size: 11px;
		fill: var(--text-2);
		font-family: var(--font);
	}
	path {
		fill: none;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.other,
	.k-other {
		stroke: var(--muted);
		stroke-opacity: 0.3;
		stroke-width: 1;
	}
	.usual,
	.k-usual {
		stroke: var(--text);
		stroke-width: 2;
		stroke-dasharray: 5 3;
	}
	.sel-line,
	.k-sel {
		stroke: var(--line);
		stroke-width: 2.5;
	}
	.inc {
		fill: var(--surface);
		stroke: var(--line);
		stroke-width: 1.5;
	}
	.ring {
		fill: none;
		stroke: var(--text);
		stroke-width: 2;
	}
	.cross {
		stroke: var(--text-2);
		stroke-width: 1;
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.small {
		font-size: 0.78rem;
		color: var(--text-2);
	}
</style>
