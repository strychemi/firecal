<script lang="ts">
	import { Tween } from 'svelte/motion';
	import { cubicInOut } from 'svelte/easing';
	import ChartFrame from './ChartFrame.svelte';
	import Tooltip, { type TipRow } from './Tooltip.svelte';
	import { SOURCES, SOURCE_SATELLITE, SOURCE_SHORT, fmt, fmtTick, median } from '#lib/format.ts';
	import { ERA_VAR, linear, niceTicks } from '#lib/scales.ts';
	import type { MonthRow, Source } from '#lib/types.ts';

	interface Props {
		months: MonthRow[];
		filename: string;
		busy?: boolean;
	}
	let { months, filename, busy = false }: Props = $props();

	let mode = $state<'value' | 'raw'>('value');

	const reduceMotion =
		typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	const t = new Tween(1, { duration: reduceMotion ? 0 : 900, easing: cubicInOut });
	$effect(() => {
		t.target = mode === 'value' ? 1 : 0;
	});

	interface Year {
		year: number;
		nMonths: number;
		value: number;
		raw: number;
		bySource: { source: Source; value: number; raw: number; months: number }[];
	}
	const years = $derived.by(() => {
		const map = new Map<number, Year>();
		for (const m of months) {
			const y = Number(m.month.slice(0, 4));
			let e = map.get(y);
			if (!e) {
				e = { year: y, nMonths: 0, value: 0, raw: 0, bySource: [] };
				map.set(y, e);
			}
			e.nMonths++;
			e.value += m.value;
			e.raw += m.raw;
			let s = e.bySource.find((b) => b.source === m.source);
			if (!s) {
				s = { source: m.source, value: 0, raw: 0, months: 0 };
				e.bySource.push(s);
			}
			s.value += m.value;
			s.raw += m.raw;
			s.months++;
		}
		for (const e of map.values()) e.bySource.sort((a, b) => SOURCES.indexOf(a.source) - SOURCES.indexOf(b.source));
		return [...map.values()].sort((a, b) => a.year - b.year);
	});

	// Shared y-scale for both views, so VIIRS bars stay still and MODIS bars move.
	const yMax = $derived(Math.max(1, ...years.map((y) => Math.max(y.value, y.raw))));
	const ticks = $derived(niceTicks(yMax, 4));

	let w = $state(600);
	const H = 280;
	const M = { top: 26, right: 8, bottom: 30, left: 44 };
	const innerW = $derived(Math.max(10, w - M.left - M.right));
	const innerH = H - M.top - M.bottom;
	const band = $derived(innerW / Math.max(1, years.length));
	const barW = $derived(Math.max(3, Math.min(28, band - 2)));
	const y = $derived(linear(0, ticks[ticks.length - 1], innerH, 0));
	const labelEvery = $derived(band >= 30 ? 1 : band >= 16 ? 2 : 5);

	const mix = (raw: number, value: number) => raw + (value - raw) * t.current;

	interface Seg {
		source: Source;
		x: number;
		y: number;
		h: number;
		top: boolean;
	}
	const bars = $derived(
		years.map((yr, i) => {
			const x = M.left + i * band + (band - barW) / 2;
			let acc = 0;
			const segs: Seg[] = yr.bySource.map((s) => {
				const v = mix(s.raw, s.value);
				const y0 = y(acc);
				acc += v;
				const y1 = y(acc);
				return { source: s.source, x, y: M.top + y1, h: Math.max(0, y0 - y1), top: false };
			});
			// gap of 2px between stacked segments; round the data end
			for (let k = 0; k < segs.length - 1; k++) segs[k + 1].h = Math.max(0, segs[k + 1].h - 2);
			if (segs.length) segs[segs.length - 1].top = true;
			return { yr, x, segs, total: mix(yr.raw, yr.value) };
		})
	);

	function topRounded(x: number, y0: number, wd: number, h: number, r: number) {
		r = Math.min(r, wd / 2, h);
		return `M${x},${y0 + h}V${y0 + r}Q${x},${y0} ${x + r},${y0}H${x + wd - r}Q${x + wd},${y0} ${x + wd},${y0 + r}V${y0 + h}Z`;
	}

	// Era labels above the bars: contiguous runs of years by main source.
	const eraRuns = $derived.by(() => {
		const runs: { source: Source; x0: number; x1: number }[] = [];
		years.forEach((yr, i) => {
			for (const s of yr.bySource) {
				const last = runs.findLast((r) => r.source === s.source);
				const x0 = M.left + i * band;
				if (last && Math.abs(last.x1 - x0) < 1) last.x1 = x0 + band;
				else runs.push({ source: s.source, x0, x1: x0 + band });
			}
		});
		return runs;
	});

	const partial = $derived(years.filter((yr) => yr.nMonths < 12 || yr.bySource.length > 1));

	const jump = $derived.by(() => {
		const aqua = years.filter((yr) => yr.nMonths === 12 && yr.bySource.length === 1 && yr.bySource[0].source === 'aqua_harmonized');
		const viirs = years.filter((yr) => yr.nMonths === 12 && yr.bySource.length === 1 && yr.bySource[0].source === 'viirs');
		if (aqua.length < 2 || viirs.length < 2) return null;
		const r = (k: 'raw' | 'value') => median(viirs.map((v) => v[k])) / Math.max(1e-9, median(aqua.map((v) => v[k])));
		return { raw: r('raw'), value: r('value'), aqua: aqua.length, viirs: viirs.length };
	});

	let active = $state<number | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let live = $state('');

	function describe(yr: Year): string {
		const parts = yr.bySource.map((s) => `${SOURCE_SHORT[s.source]} ${s.months} months`).join(', ');
		return `${yr.year}: ${fmt(yr.value)} converted, ${fmt(yr.raw)} raw. ${parts}.`;
	}
	function onkey(e: KeyboardEvent) {
		if (!years.length) return;
		let i = active ?? years.length - 1;
		if (e.key === 'ArrowLeft') i--;
		else if (e.key === 'ArrowRight') i++;
		else if (e.key === 'Home') i = 0;
		else if (e.key === 'End') i = years.length - 1;
		else if (e.key === 'Escape') {
			active = null;
			return;
		} else return;
		e.preventDefault();
		active = Math.max(0, Math.min(years.length - 1, i));
		live = describe(years[active]);
	}

	const tip = $derived.by(() => {
		if (active === null || !bars[active]) return null;
		const b = bars[active];
		const yr = b.yr;
		const rows: TipRow[] = [
			{ value: fmt(yr.value), label: 'fire-days, converted' },
			{ value: fmt(yr.raw), label: 'raw satellite counts' }
		];
		for (const s of yr.bySource)
			rows.push({ value: fmt(s.value), label: `${SOURCE_SHORT[s.source]}, ${s.months} mo (raw ${fmt(s.raw)})`, key: ERA_VAR[s.source] });
		return {
			x: b.x + barW,
			y: Math.min(M.top + y(b.total), H - 120),
			heading: String(yr.year) + (yr.nMonths < 12 ? ` (${yr.nMonths} months shown)` : ''),
			rows
		};
	});

	const title = 'Yearly totals';
</script>

<ChartFrame
	id="yearly"
	{title}
	subtitle="Fire-days per year. Switch to raw satellite counts to see the jump in 2012 when the record moves from MODIS to VIIRS, whose smaller pixels see more small fires. Converted counts put both on the VIIRS scale."
	{filename}
	svg={svgEl}
	{busy}
>
	{#snippet controls()}
		<div class="seg" role="group" aria-label="Yearly totals: which numbers">
			<button type="button" class="btn" aria-pressed={mode === 'value'} onclick={() => (mode = 'value')}>
				Converted (one scale)
			</button>
			<button type="button" class="btn" aria-pressed={mode === 'raw'} onclick={() => (mode = 'raw')}>
				Raw satellite counts
			</button>
		</div>
	{/snippet}
	{#snippet legend()}
		<span class="lt">Satellite record:</span>
		{#each SOURCES as s (s)}
			<span class="li"><span class="sw" style:background={ERA_VAR[s]}></span>{SOURCE_SATELLITE[s]}</span>
		{/each}
	{/snippet}

	<div class="wrap" bind:clientWidth={w}>
		<!-- Keyboard-operable chart: one tab stop, arrow keys move the readout (announced via aria-live). -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
		<svg
			bind:this={svgEl}
			viewBox="0 0 {w} {H}"
			width={w}
			height={H}
			role="application"
			tabindex="0"
			aria-roledescription="bar chart"
			aria-label="{title}, {mode === 'value' ? 'converted' : 'raw satellite counts'}, stacked by satellite record. Use left and right arrow keys to read years."
			onkeydown={onkey}
			onblur={() => (active = null)}
			onpointerleave={() => (active = null)}
		>
			{#each ticks as tk (tk)}
				<line class="grid" x1={M.left} x2={w - M.right} y1={M.top + y(tk)} y2={M.top + y(tk)} />
				<text class="axis" x={M.left - 6} y={M.top + y(tk)} text-anchor="end" dominant-baseline="central">{fmtTick(tk)}</text>
			{/each}
			{#each eraRuns as r, i (i)}
				<line class="era-rule" x1={r.x0 + 2} x2={r.x1 - 2} y1={12} y2={12} style:stroke={ERA_VAR[r.source]} />
				{#if r.x1 - r.x0 > 34}
					<text class="era-label" x={(r.x0 + r.x1) / 2} y={8} text-anchor="middle">{SOURCE_SHORT[r.source]}</text>
				{/if}
			{/each}
			{#each bars as b, i (b.yr.year)}
				<g role="presentation" onpointerenter={() => (active = i)}>
					<rect class="hit" class:act={i === active} x={M.left + i * band} y={M.top} width={band} height={innerH} />
					{#each b.segs as s (s.source)}
						{#if s.top}
							<path d={topRounded(s.x, s.y, barW, s.h, 3)} style:fill={ERA_VAR[s.source]} />
						{:else}
							<rect x={s.x} y={s.y} width={barW} height={s.h} style:fill={ERA_VAR[s.source]} />
						{/if}
					{/each}
				</g>
				{#if i % labelEvery === 0 || (i === bars.length - 1 && i % labelEvery >= Math.ceil(labelEvery / 2) + 1)}
					<text class="axis" x={b.x + barW / 2} y={H - M.bottom + 14} text-anchor="middle">{b.yr.year}{partial.includes(b.yr) ? '*' : ''}</text>
				{/if}
			{/each}
			<line class="base" x1={M.left} x2={w - M.right} y1={M.top + innerH} y2={M.top + innerH} />
		</svg>
		{#if tip}
			<Tooltip x={tip.x} y={tip.y} parentWidth={w} heading={tip.heading} rows={tip.rows} />
		{/if}
	</div>
	<p class="sr-only" aria-live="polite">{live}</p>

	{#snippet notes()}
		{#if jump}
			<p>
				<strong>Typical year, VIIRS ({jump.viirs} full years) against Aqua MODIS ({jump.aqua} full years):</strong>
				raw counts {jump.raw.toFixed(1)}×, converted counts {jump.value.toFixed(1)}×.
			</p>
		{/if}
		{#if partial.length}
			<p>
				* Not a full year from one satellite:
				{partial
					.map((yr) =>
						yr.nMonths < 12
							? `${yr.year} (${yr.nMonths} months${yr.year === 2000 ? ', the record starts in November' : ''})`
							: `${yr.year} (${yr.bySource.map((s) => SOURCE_SHORT[s.source]).join(' then ')})`
					)
					.join('; ')}.
			</p>
		{/if}
	{/snippet}

	{#snippet table()}
		<table class="data">
			<caption class="sr-only">{title}</caption>
			<thead>
				<tr><th scope="col">Year</th><th scope="col">Months</th><th scope="col">Record</th><th scope="col">Converted</th><th scope="col">Raw</th></tr>
			</thead>
			<tbody>
				{#each years as yr (yr.year)}
					<tr>
						<th scope="row">{yr.year}</th>
						<td>{yr.nMonths}</td>
						<td>{yr.bySource.map((s) => SOURCE_SHORT[s.source]).join(' + ')}</td>
						<td>{fmt(yr.value)}</td>
						<td>{fmt(yr.raw)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/snippet}
</ChartFrame>

<style>
	.wrap {
		position: relative;
		width: 100%;
	}
	svg {
		display: block;
		touch-action: manipulation;
	}
	svg:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
		border-radius: 4px;
	}
	.grid {
		stroke: var(--grid);
		stroke-width: 1;
	}
	.base {
		stroke: var(--axis);
		stroke-width: 1;
	}
	.axis {
		font-size: 11px;
		fill: var(--text-2);
		font-family: var(--font);
	}
	.era-label {
		font-size: 11px;
		font-weight: 600;
		fill: var(--text);
		font-family: var(--font);
	}
	.era-rule {
		stroke-width: 2;
		stroke-linecap: round;
	}
	.hit {
		fill: transparent;
	}
	.hit.act {
		fill: var(--wash);
	}
	.lt {
		color: var(--text-2);
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		white-space: nowrap;
	}
	.sw {
		width: 14px;
		height: 14px;
		border-radius: 3px;
	}
</style>
