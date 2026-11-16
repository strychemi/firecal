<script lang="ts">
	// Kepler-style time bar: the whole series as a histogram (bars coloured by satellite era),
	// a brushed date range (drag across bars, or drag either handle) and a playhead for the
	// selected month (click a bar). Arrow keys move the month when the chart has focus.
	import type { MonthRow, YearMonth } from '#lib/types.ts';
	import { ERA_VAR } from '#lib/scales.ts';
	import { fmt, monthLabel, monthNote, monthShortLabel, SOURCE_LABEL } from '#lib/format.ts';

	interface Props {
		series: MonthRow[];
		start: YearMonth;
		end: YearMonth;
		month: YearMonth;
		onrange: (start: YearMonth, end: YearMonth) => void;
		onmonth: (m: YearMonth) => void;
		busy?: boolean;
	}
	let { series, start, end, month, onrange, onmonth, busy = false }: Props = $props();

	let w = $state(800);
	const H = 92;
	const M = { top: 6, right: 8, bottom: 18, left: 8 };
	const innerW = $derived(Math.max(10, w - M.left - M.right));
	const innerH = H - M.top - M.bottom;
	const n = $derived(series.length);
	const bw = $derived(innerW / Math.max(1, n));
	const max = $derived(Math.max(1, ...series.map((m) => m.value)));
	const index = $derived(new Map(series.map((m, i) => [m.month, i])));
	const i0 = $derived(index.get(start) ?? 0);
	const i1 = $derived(index.get(end) ?? n - 1);
	const im = $derived(index.get(month) ?? i1);
	const x = (i: number) => M.left + i * bw;
	const bh = (v: number) => Math.max(v > 0 ? 1 : 0, Math.sqrt(v / max) * innerH);
	const years = $derived(
		series
			.map((m, i) => ({ i, y: m.month.slice(0, 4), jan: m.month.endsWith('-01') }))
			.filter((d) => d.jan && Number(d.y) % (w < 600 ? 5 : 2) === 0)
	);

	let svg: SVGSVGElement;
	let hover = $state<number | null>(null);
	let focused = $state(false);
	let drag: { mode: 'start' | 'end' | 'new'; from: number; moved: boolean } | null = null;

	function idxAt(e: PointerEvent): number {
		const r = svg.getBoundingClientRect();
		return Math.max(0, Math.min(n - 1, Math.floor((e.clientX - r.left - M.left) / bw)));
	}
	function down(e: PointerEvent) {
		if (!n) return;
		const i = idxAt(e);
		const near = (j: number) => Math.abs(e.clientX - svg.getBoundingClientRect().left - x(j)) < 8;
		drag = { mode: near(i0) ? 'start' : near(i1 + 1) ? 'end' : 'new', from: i, moved: false };
		svg.setPointerCapture(e.pointerId);
	}
	function move(e: PointerEvent) {
		if (!n) return;
		const i = idxAt(e);
		hover = i;
		if (!drag) return;
		if (i !== drag.from) drag.moved = true;
		if (!drag.moved) return;
		if (drag.mode === 'start') onrange(series[Math.min(i, i1)].month, end);
		else if (drag.mode === 'end') onrange(start, series[Math.max(i, i0)].month);
		else onrange(series[Math.min(i, drag.from)].month, series[Math.max(i, drag.from)].month);
	}
	function up(e: PointerEvent) {
		if (drag && !drag.moved) {
			const m = series[idxAt(e)].month;
			if (m < start || m > end) onrange(m < start ? m : start, m > end ? m : end);
			onmonth(m);
		}
		drag = null;
	}
	function key(e: KeyboardEvent) {
		const step = { ArrowLeft: -1, ArrowRight: 1, PageUp: -12, PageDown: 12, Home: -n, End: n }[e.key] ?? 0;
		if (!step) return;
		e.preventDefault();
		hover = null;
		const j = Math.max(i0, Math.min(i1, im + step));
		onmonth(series[j].month);
	}

	// The details box follows the pointer, or the selected month while the bar has keyboard focus.
	const tipAt = $derived(hover ?? (focused ? im : null));
	const hov = $derived(tipAt != null ? series[tipAt] : null);
	const tipLeft = $derived(tipAt != null ? Math.min(Math.max(0, x(tipAt) - 110), w - 230) : 0);
	const sel = $derived(series[im]);
	const valueText = $derived(
		sel ? `${monthLabel(sel.month)}: ${fmt(sel.value)} fire-days, ${SOURCE_LABEL[sel.source]}${monthNote(sel) ? `, ${monthNote(sel)}` : ''}` : monthLabel(month)
	);
</script>

<div class="tb" bind:clientWidth={w} class:busy>
	<svg
		bind:this={svg}
		width={w}
		height={H}
		role="slider"
		tabindex="0"
		aria-label="Month"
		aria-describedby="timebar-help"
		aria-valuemin={0}
		aria-valuemax={Math.max(0, n - 1)}
		aria-valuenow={im}
		aria-valuetext={valueText}
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onpointerleave={() => (hover = null)}
		onfocus={() => (focused = true)}
		onblur={() => (focused = false)}
		onkeydown={key}
	>
		<rect x={x(i0)} y={M.top - 4} width={Math.max(2, (i1 - i0 + 1) * bw)} height={innerH + 4} class="sel" />
		{#each series as m, i (m.month)}
			<rect
				x={x(i) + (bw > 3 ? 0.5 : 0)}
				width={Math.max(0.6, bw - (bw > 3 ? 1 : 0))}
				y={M.top + innerH - bh(m.value)}
				height={bh(m.value)}
				fill={ERA_VAR[m.source]}
				opacity={i < i0 || i > i1 ? 0.28 : m.complete || m.in_progress ? 1 : 0.55}
			/>
		{/each}
		<line x1={M.left} x2={M.left + innerW} y1={M.top + innerH + 0.5} y2={M.top + innerH + 0.5} class="axis" />
		{#each years as t (t.i)}
			<line x1={x(t.i)} x2={x(t.i)} y1={M.top + innerH} y2={M.top + innerH + 4} class="axis" />
			<text x={x(t.i)} y={H - 4} class="tick">{t.y}</text>
		{/each}
		<!-- Brush handles -->
		<g class="handle">
			<rect x={x(i0) - 3} y={M.top + innerH / 2 - 12} width="6" height="24" rx="2" />
			<rect x={x(i1 + 1) - 3} y={M.top + innerH / 2 - 12} width="6" height="24" rx="2" />
		</g>
		<!-- Playhead -->
		<line x1={x(im) + bw / 2} x2={x(im) + bw / 2} y1={M.top - 4} y2={M.top + innerH} class="playhead" />
		<circle cx={x(im) + bw / 2} cy={M.top - 2} r="4" class="playhead-dot" />
	</svg>
	{#if hov}
		<div class="tip" style="left:{tipLeft}px">
			<strong>{monthLabel(hov.month)}</strong><br />
			{fmt(hov.value)} fire-days{#if hov.lower != null}
				(80 % range {fmt(hov.lower)}–{fmt(hov.upper)}){/if}<br />
			Raw: {fmt(hov.raw)} fire-days · {fmt(hov.detections)} hotspots<br />
			<span class="sw" style="background:{ERA_VAR[hov.source]}"></span>{SOURCE_LABEL[hov.source]}
			{#if monthNote(hov)}<br /><em>{monthNote(hov)}</em>{/if}
		</div>
	{/if}
	<p class="sr" id="timebar-help">Date range {monthShortLabel(start)} to {monthShortLabel(end)}. Drag across the bars to choose the date range, click a bar to choose the month, and use the arrow keys, Page Up and Page Down to move the month. To type exact dates, use the Dates tab.</p>
</div>

<style>
	.tb {
		position: relative;
		width: 100%;
		/* Horizontal drags brush the dates; vertical swipes still scroll the page. */
		touch-action: pan-y;
	}
	.tb.busy svg {
		opacity: 0.85;
	}
	svg {
		display: block;
		cursor: crosshair;
		outline: none;
		border-radius: 6px;
	}
	svg:focus-visible {
		box-shadow: 0 0 0 2px var(--focus);
	}
	.sel {
		fill: var(--wash);
		stroke: var(--axis);
		stroke-width: 1;
	}
	.axis {
		stroke: var(--axis);
	}
	.tick {
		font-size: 10px;
		fill: var(--muted);
		text-anchor: middle;
	}
	.handle rect {
		fill: var(--text);
		cursor: ew-resize;
	}
	.playhead {
		stroke: var(--text);
		stroke-width: 2;
	}
	.playhead-dot {
		fill: var(--text);
	}
	.tip {
		position: absolute;
		bottom: calc(100% + 6px);
		width: 220px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 6px 8px;
		font-size: 0.75rem;
		line-height: 1.45;
		pointer-events: none;
		box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
		z-index: 5;
	}
	.sw {
		display: inline-block;
		width: 9px;
		height: 9px;
		border-radius: 2px;
		margin-right: 4px;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
</style>
