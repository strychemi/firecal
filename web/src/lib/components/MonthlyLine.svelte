<script lang="ts">
	import ChartFrame from './ChartFrame.svelte';
	import Tooltip, { type TipRow } from './Tooltip.svelte';
	import { SOURCE_LABEL, SOURCE_SHORT, fmt, fmtTick, monthLabel, monthShortLabel } from '#lib/format.ts';
	import { linear, niceTicks } from '#lib/scales.ts';
	import type { MonthRow, Source, YearMonth } from '#lib/types.ts';

	interface Props {
		months: MonthRow[];
		selected: YearMonth;
		filename: string;
		busy?: boolean;
	}
	let { months, selected, filename, busy = false }: Props = $props();

	let w = $state(600);
	const H = 280;
	const M = { top: 26, right: 12, bottom: 30, left: 44 };
	const innerW = $derived(Math.max(10, w - M.left - M.right));
	const innerH = H - M.top - M.bottom;
	const n = $derived(months.length);
	const x = $derived(linear(0, Math.max(1, n - 1), M.left, M.left + innerW));
	const yMax = $derived(Math.max(1, ...months.map((m) => m.upper ?? m.value)));
	const ticks = $derived(niceTicks(yMax, 4));
	const y = $derived(linear(0, ticks[ticks.length - 1], M.top + innerH, M.top));

	const linePath = $derived(months.map((m, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(m.value).toFixed(1)}`).join(''));

	// 80 % band only where lower/upper exist (converted months with fire).
	const bandPaths = $derived.by(() => {
		const out: string[] = [];
		let run: number[] = [];
		const flush = () => {
			if (run.length) {
				const top = run.map((i) => `${x(i).toFixed(1)},${y(months[i].upper!).toFixed(1)}`);
				const bot = [...run].reverse().map((i) => `${x(i).toFixed(1)},${y(months[i].lower!).toFixed(1)}`);
				out.push(`M${top.join('L')}L${bot.join('L')}Z`);
			}
			run = [];
		};
		months.forEach((m, i) => {
			if (m.lower !== null && m.upper !== null) run.push(i);
			else flush();
		});
		flush();
		return out;
	});
	const hasBand = $derived(bandPaths.length > 0);

	const eras = $derived.by(() => {
		const runs: { source: Source; i0: number; i1: number }[] = [];
		months.forEach((m, i) => {
			const last = runs[runs.length - 1];
			if (last && last.source === m.source) last.i1 = i;
			else runs.push({ source: m.source, i0: i, i1: i });
		});
		const half = n > 1 ? (x(1) - x(0)) / 2 : 0;
		return runs.map((r, k) => ({
			...r,
			x0: Math.max(M.left, x(r.i0) - half),
			x1: Math.min(M.left + innerW, x(r.i1) + half),
			shade: k % 2 === 0
		}));
	});

	const yearTicks = $derived.by(() => {
		const janIdx = months.map((m, i) => (m.month.endsWith('-01') ? i : -1)).filter((i) => i >= 0);
		const pxPerYear = n > 1 ? (innerW / (n - 1)) * 12 : innerW;
		const every = pxPerYear >= 44 ? 1 : pxPerYear >= 22 ? 2 : pxPerYear >= 9 ? 5 : 10;
		return janIdx.filter((i) => Number(months[i].month.slice(0, 4)) % every === 0);
	});

	const selIdx = $derived(months.findIndex((m) => m.month === selected));
	const incomplete = $derived(months.map((m, i) => (m.complete ? -1 : i)).filter((i) => i >= 0));

	let active = $state<number | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);
	let live = $state('');

	function nearest(px: number): number {
		if (n <= 1) return 0;
		const i = Math.round(((px - M.left) / innerW) * (n - 1));
		return Math.max(0, Math.min(n - 1, i));
	}
	function onmove(e: PointerEvent) {
		const r = svgEl!.getBoundingClientRect();
		active = nearest(e.clientX - r.left);
	}
	function describe(m: MonthRow) {
		let s = `${monthLabel(m.month)}: ${fmt(m.value)} burning places`;
		if (m.lower !== null && m.upper !== null) s += `, 80 % range ${fmt(m.lower)} to ${fmt(m.upper)}`;
		s += `, ${SOURCE_LABEL[m.source]}`;
		if (!m.complete) s += ', incomplete month';
		return s;
	}
	function onkey(e: KeyboardEvent) {
		if (!n) return;
		let i = active ?? (selIdx >= 0 ? selIdx : n - 1);
		const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, PageUp: -12, PageDown: 12, Home: -n, End: n };
		if (e.key === 'Escape') {
			active = null;
			return;
		}
		if (!(e.key in step)) return;
		e.preventDefault();
		i = Math.max(0, Math.min(n - 1, i + step[e.key]));
		active = i;
		live = describe(months[i]);
	}

	const tip = $derived.by(() => {
		if (active === null || !months[active]) return null;
		const m = months[active];
		const rows: TipRow[] = [{ value: fmt(m.value), label: 'burning places (converted)', key: 'var(--line)' }];
		if (m.lower !== null && m.upper !== null) rows.push({ value: `${fmt(m.lower)}–${fmt(m.upper)}`, label: '80 % range' });
		rows.push({ value: fmt(m.raw), label: 'raw satellite count' });
		return {
			x: x(active),
			y: Math.min(y(m.value), H - 120),
			heading: monthLabel(m.month),
			rows,
			foot: SOURCE_LABEL[m.source] + (m.complete ? '' : ` · incomplete (${m.days_with_data} of ${m.days} days)`)
		};
	});

	const title = 'Monthly burning places';
</script>

<ChartFrame
	id="monthly"
	{title}
	subtitle="Converted burning places each month for the selected dates. The shaded band is the 80 % range for months converted from MODIS; VIIRS months are observed directly, so they have no band."
	{filename}
	svg={svgEl}
	{busy}
>
	{#snippet legend()}
		<span class="li"><svg width="18" height="10" aria-hidden="true"><line x1="0" x2="18" y1="5" y2="5" stroke="var(--line)" stroke-width="2" /></svg>Burning places (converted)</span>
		{#if hasBand}
			<span class="li"><span class="sw band"></span>80 % range</span>
		{/if}
		{#if incomplete.length}
			<span class="li"><svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="var(--text)" stroke-width="1.5" /></svg>Incomplete month</span>
		{/if}
		<span class="li"><span class="sw era"></span>Background bands: satellite record (labelled)</span>
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
			aria-roledescription="line chart"
			aria-label="{title} from {months[0] ? monthLabel(months[0].month) : ''} to {months[n - 1] ? monthLabel(months[n - 1].month) : ''}. Use arrow keys to read months, Page Up and Page Down to jump a year."
			onkeydown={onkey}
			onpointermove={onmove}
			onpointerleave={() => (active = null)}
			onblur={() => (active = null)}
		>
			{#each eras as e, i (i)}
				<rect x={e.x0} y={M.top} width={Math.max(0, e.x1 - e.x0)} height={innerH} style:fill={e.shade ? 'var(--era-shade-a)' : 'var(--era-shade-b)'} />
				<line class="era-tick" x1={e.x0} x2={e.x0} y1={M.top - 14} y2={M.top + innerH} />
				{#if e.x1 - e.x0 > 40}
					<text class="era-label" x={e.x0 + 4} y={M.top - 6}>{SOURCE_SHORT[e.source]}</text>
				{/if}
			{/each}
			{#each ticks as tk (tk)}
				<line class="grid" x1={M.left} x2={M.left + innerW} y1={y(tk)} y2={y(tk)} />
				<text class="axis" x={M.left - 6} y={y(tk)} text-anchor="end" dominant-baseline="central">{fmtTick(tk)}</text>
			{/each}
			{#each bandPaths as d, i (i)}
				<path d={d} class="band" />
			{/each}
			<path d={linePath} class="line" />
			{#each incomplete as i (i)}
				<circle cx={x(i)} cy={y(months[i].value)} r="3.5" class="inc" />
			{/each}
			{#if selIdx >= 0}
				<circle cx={x(selIdx)} cy={y(months[selIdx].value)} r="4.5" class="sel" />
			{/if}
			{#each yearTicks as i (i)}
				<line class="tick" x1={x(i)} x2={x(i)} y1={M.top + innerH} y2={M.top + innerH + 4} />
				<text class="axis" x={x(i)} y={H - M.bottom + 16} text-anchor="middle">{months[i].month.slice(0, 4)}</text>
			{/each}
			<line class="base" x1={M.left} x2={M.left + innerW} y1={M.top + innerH} y2={M.top + innerH} />
			{#if active !== null && months[active]}
				<g data-export-skip>
					<line class="cross" x1={x(active)} x2={x(active)} y1={M.top} y2={M.top + innerH} />
					<circle cx={x(active)} cy={y(months[active].value)} r="4" class="dot" />
				</g>
			{/if}
		</svg>
		{#if tip}
			<Tooltip x={tip.x} y={tip.y} parentWidth={w} heading={tip.heading} rows={tip.rows} foot={tip.foot} />
		{/if}
	</div>
	<p class="sr-only" aria-live="polite">{live}</p>

	{#snippet notes()}
		{#if selIdx >= 0}<p>The ringed point is the month described in the answer card ({monthShortLabel(selected)}).</p>{/if}
	{/snippet}

	{#snippet table()}
		<table class="data">
			<caption class="sr-only">{title}</caption>
			<thead>
				<tr><th scope="col">Month</th><th scope="col">Converted</th><th scope="col">80 % range</th><th scope="col">Raw</th><th scope="col">Hotspots</th><th scope="col">FRP (MW)</th><th scope="col">Record</th><th scope="col">Complete</th></tr>
			</thead>
			<tbody>
				{#each months as m (m.month)}
					<tr>
						<th scope="row">{m.month}</th>
						<td>{fmt(m.value)}</td>
						<td>{m.lower !== null && m.upper !== null ? `${fmt(m.lower)}–${fmt(m.upper)}` : '–'}</td>
						<td>{fmt(m.raw)}</td>
						<td>{fmt(m.detections)}</td>
						<td>{fmt(m.frp)}</td>
						<td>{SOURCE_SHORT[m.source]}</td>
						<td>{m.complete ? 'yes' : `no (${m.days_with_data}/${m.days} days)`}</td>
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
	.base,
	.tick {
		stroke: var(--axis);
	}
	.era-tick {
		stroke: var(--axis);
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
	.band {
		fill: var(--band);
		stroke: none;
	}
	.line {
		fill: none;
		stroke: var(--line);
		stroke-width: 2;
		stroke-linejoin: round;
	}
	.inc {
		fill: var(--surface);
		stroke: var(--text);
		stroke-width: 1.5;
	}
	.sel {
		fill: none;
		stroke: var(--text);
		stroke-width: 2;
	}
	.cross {
		stroke: var(--text-2);
		stroke-width: 1;
	}
	.dot {
		fill: var(--line);
		stroke: var(--surface);
		stroke-width: 2;
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.sw {
		width: 14px;
		height: 14px;
		border-radius: 3px;
	}
	.sw.band {
		background: var(--band);
	}
	.sw.era {
		background: var(--era-shade-a);
		box-shadow: inset 0 0 0 1px var(--border);
	}
</style>
