<script lang="ts">
	import ChartFrame from './ChartFrame.svelte';
	import Tooltip, { type TipRow } from './Tooltip.svelte';
	import CategoryIcon from './CategoryIcon.svelte';
	import { MONTH_SHORT, SOURCE_LABEL, fmt, fmt1, monthLabel, monthNote } from '#lib/format.ts';
	import {
		CATEGORY_ICON,
		ICON_STROKE,
		CATEGORY_INK,
		CATEGORY_ORDER,
		CATEGORY_VAR,
		anomalies,
		seqClass,
		seqThresholds,
		seqVar
	} from '#lib/scales.ts';
	import type { MonthRow, YearMonth } from '#lib/types.ts';

	interface Props {
		months: MonthRow[];
		selected: YearMonth;
		onselect: (m: YearMonth) => void;
		filename: string;
		busy?: boolean;
		/** Area and dates, for saved images. */
		context?: string;
	}
	let { months, selected, onselect, filename, busy = false, context }: Props = $props();

	type Mode = 'value' | 'raw' | 'detections' | 'frp' | 'anomaly';
	const MODES: { id: Mode; label: string; unit: string }[] = [
		{ id: 'value', label: 'Fire-days (converted)', unit: 'fire-days' },
		{ id: 'raw', label: 'Raw satellite counts', unit: 'fire-days, as the satellite saw them' },
		{ id: 'detections', label: 'Hotspots detected', unit: 'hotspots' },
		{ id: 'frp', label: 'Fire power (FRP)', unit: 'MW total fire radiative power' },
		{ id: 'anomaly', label: 'Compared with usual', unit: '' }
	];
	let mode = $state<Mode>('value');
	const modeInfo = $derived(MODES.find((m) => m.id === mode)!);

	const LABEL_W = 36;
	const HEAD_H = 16;
	const CW = 28;
	const RH = 16;
	const W = LABEL_W + 12 * CW;

	const years = $derived.by(() => {
		if (!months.length) return [] as number[];
		const a = Number(months[0].month.slice(0, 4));
		const b = Number(months[months.length - 1].month.slice(0, 4));
		return Array.from({ length: b - a + 1 }, (_, i) => a + i);
	});
	const H = $derived(HEAD_H + years.length * RH + 2);

	const metric = (m: MonthRow) => (mode === 'anomaly' ? m.value : m[mode]);
	const thresholds = $derived(mode === 'anomaly' ? [] : seqThresholds(months.map(metric)));
	const nClasses = $derived(thresholds.length + 1);
	const anom = $derived(anomalies(months));

	interface Cell {
		m: MonthRow;
		x: number;
		y: number;
		fill: string;
		icon?: { d: string; outline: boolean };
		ink?: string;
	}
	const cells = $derived.by(() => {
		const y0 = years[0];
		return months.map((m): Cell => {
			const yi = Number(m.month.slice(0, 4)) - y0;
			const mi = Number(m.month.slice(5)) - 1;
			const c: Cell = { m, x: LABEL_W + mi * CW, y: HEAD_H + yi * RH, fill: '' };
			if (mode === 'anomaly') {
				const a = anom.get(m.month);
				if (!a) {
					c.fill = 'var(--seq-0)'; // in progress: compared on days 1..D in the answer card
					return c;
				}
				c.fill = CATEGORY_VAR[a.category];
				if (a.category !== 'about usual') {
					c.icon = CATEGORY_ICON[a.category];
					c.ink = CATEGORY_INK[a.category];
				}
			} else {
				c.fill = seqVar(seqClass(metric(m), thresholds), nClasses);
			}
			return c;
		});
	});

	const legendBins = $derived.by(() => {
		const out: { label: string; fill: string }[] = [{ label: '0', fill: 'var(--seq-0)' }];
		const t = thresholds;
		// Classes are [t[i-1], t[i]); the first starts just above zero.
		for (let i = 0; i <= t.length; i++) {
			let label: string;
			if (t.length === 0) label = 'above 0';
			else if (i === 0) label = `under ${fmt(t[0])}`;
			else if (i === t.length) label = `${fmt(t[i - 1])}+`;
			else label = `${fmt(t[i - 1])}–${fmt(t[i])}`;
			out.push({ label, fill: seqVar(i + 1, nClasses) });
		}
		return out;
	});

	// Interaction: one tab stop, arrow keys move the active cell.
	let active = $state<number | null>(null);
	let wrapW = $state(0);
	let svgEl = $state<SVGSVGElement | null>(null);
	const scale = $derived(wrapW > 0 ? wrapW / W : 1);
	const activeCell = $derived(active === null ? null : (cells[active] ?? null));

	function describe(m: MonthRow): string {
		const parts = [`${monthLabel(m.month)}:`];
		const a = mode === 'anomaly' ? anom.get(m.month) : undefined;
		if (mode === 'anomaly' && !a) {
			parts.push(`${fmt(m.value)} fire-days so far; select it to compare with the same days in other years`);
		} else if (a) {
			parts.push(
				`${fmt(m.value)} fire-days, ${a.category}` +
					(a.ratio !== null ? ` (${a.ratio.toFixed(1)}× the median of ${a.years} years)` : '')
			);
		} else {
			parts.push(`${mode === 'frp' ? fmt(m.frp) : fmt(metric(m))} ${modeInfo.unit}`);
		}
		if (m.lower !== null && m.upper !== null && (mode === 'value' || mode === 'anomaly'))
			parts.push(`80 % range ${fmt(m.lower)} to ${fmt(m.upper)}`);
		parts.push(SOURCE_LABEL[m.source]);
		if (!m.complete) parts.push(monthNote(m));
		return parts.join(', ');
	}

	const tip = $derived.by(() => {
		if (!activeCell) return null;
		const m = activeCell.m;
		const rows: TipRow[] = [];
		const a = mode === 'anomaly' ? anom.get(m.month) : undefined;
		if (mode === 'anomaly' && !a) {
			rows.push({ value: fmt(m.value), label: 'fire-days so far' });
			rows.push({ value: 'Select it', label: 'to compare with the same days in other years' });
		} else if (a) {
			rows.push({ value: a.category, label: '' });
			rows.push({ value: fmt(m.value), label: 'fire-days' });
			rows.push({ value: fmt(a.baseline), label: `median of ${a.years} years` });
			if (a.ratio !== null) rows.push({ value: `${a.ratio.toFixed(2)}×`, label: 'the median' });
		} else {
			rows.push({ value: mode === 'frp' ? fmt1(m.frp) : fmt(metric(m)), label: modeInfo.unit });
		}
		if (m.lower !== null && m.upper !== null && (mode === 'value' || mode === 'anomaly'))
			rows.push({ value: `${fmt(m.lower)}–${fmt(m.upper)}`, label: '80 % range' });
		if (mode !== 'value' && mode !== 'anomaly') rows.push({ value: fmt(m.value), label: 'converted' });
		return {
			x: (activeCell.x + CW) * scale,
			y: (activeCell.y + RH) * scale,
			heading: monthLabel(m.month),
			rows,
			foot:
				SOURCE_LABEL[m.source] +
				(m.complete ? '' : ` · ${monthNote(m)}`)
		};
	});

	let live = $state('');
	function setActive(i: number | null, announce = false) {
		active = i;
		if (announce && i !== null && cells[i]) live = describe(cells[i].m);
	}
	function onkey(e: KeyboardEvent) {
		const n = cells.length;
		if (!n) return;
		let i = active ?? cells.findIndex((c) => c.m.month === selected);
		if (i < 0) i = n - 1;
		const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -12, ArrowDown: 12, Home: -n, End: n };
		if (e.key in step) {
			e.preventDefault();
			setActive(Math.max(0, Math.min(n - 1, i + step[e.key])), true);
		} else if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			if (active !== null) onselect(cells[active].m.month);
		} else if (e.key === 'Escape') {
			setActive(null);
		}
	}
	function onfocus() {
		if (active === null) {
			const i = cells.findIndex((c) => c.m.month === selected);
			setActive(i < 0 ? cells.length - 1 : i, true);
		}
	}

	const incompleteCount = $derived(months.filter((m) => !m.complete).length);
	const title = 'Burning calendar';
</script>

<ChartFrame
	id="calendar"
	{title}
	subtitle="Each row is a year, each column a month. Darker means more burning. Click a month (or use the arrow keys and Enter) to describe it above."
	exportSubtitle="Each row is a year, each column a month. Darker means more burning. Ringed: the month in the answer card."
	{context}
	{filename}
	svg={svgEl}
	{busy}
>
	{#snippet controls()}
		<label class="ctl">
			<span>Show</span>
			<select bind:value={mode}>
				{#each MODES as m (m.id)}<option value={m.id}>{m.label}</option>{/each}
			</select>
		</label>
	{/snippet}
	{#snippet legend()}
		{#if mode === 'anomaly'}
			<span class="lt">Against the median of the same month in other complete years shown:</span>
			{#each CATEGORY_ORDER as c (c)}
				<span class="li"><span class="sw icon" style:background={CATEGORY_VAR[c]} style:color={CATEGORY_INK[c]}><CategoryIcon category={c} size={10} /></span>{c}</span>
			{/each}
		{:else}
			<span class="lt">{modeInfo.label}{mode === 'frp' ? ' (MW)' : ''}:</span>
			{#each legendBins as b (b.label)}
				<span class="li"><span class="sw" style:background={b.fill}></span>{b.label}</span>
			{/each}
		{/if}
		{#if incompleteCount}
			<span class="li">
				<svg width="14" height="14" aria-hidden="true"><rect width="14" height="14" rx="2" fill="var(--seq-0)" /><rect width="14" height="14" rx="2" fill="url(#hatch-legend)" /><defs><pattern id="hatch-legend" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="var(--hatch)" stroke-width="1.2" /></pattern></defs></svg>
				{months.some((m) => m.in_progress) ? 'Incomplete or in-progress month' : 'Incomplete month (missing satellite days)'}
			</span>
		{/if}
	{/snippet}

	<div class="scroll">
		<div class="wrap" bind:clientWidth={wrapW}>
			<!-- Keyboard-operable chart: one tab stop, arrow keys move the readout (announced via aria-live). -->
			<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
			<svg
				bind:this={svgEl}
				viewBox="0 0 {W} {H}"
				role="application"
				tabindex="0"
				aria-roledescription="calendar heatmap"
				aria-label="{title}: {modeInfo.label}, {years[0] ?? ''} to {years[years.length - 1] ?? ''}. Use arrow keys to read months, Enter to select."
				onkeydown={onkey}
				onfocus={onfocus}
				onblur={() => setActive(null)}
				onpointerleave={() => setActive(null)}
			>
				<defs>
					<pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
						<line x1="0" y1="0" x2="0" y2="4" stroke="var(--hatch)" stroke-width="1.2" />
					</pattern>
				</defs>
				{#each MONTH_SHORT as m, i (m)}
					<text class="axis" x={LABEL_W + i * CW + CW / 2} y={HEAD_H - 5} text-anchor="middle">{m[0]}{m.slice(1, 3)}</text>
				{/each}
				{#each years as y, i (y)}
					<text class="axis" x={LABEL_W - 5} y={HEAD_H + i * RH + RH / 2} text-anchor="end" dominant-baseline="central">{y}</text>
				{/each}
				{#each cells as c, i (c.m.month)}
					<g
						class="cell"
						role="presentation"
						onpointerenter={() => setActive(i)}
						onclick={() => onselect(c.m.month)}
					>
						<rect x={c.x + 1} y={c.y + 1} width={CW - 2} height={RH - 2} rx="2" fill={c.fill} />
						{#if !c.m.complete}
							<rect x={c.x + 1} y={c.y + 1} width={CW - 2} height={RH - 2} rx="2" fill="url(#hatch)" />
						{/if}
						{#if c.icon}
							<path
								class="glyph"
								transform="translate({c.x + CW / 2 - 5} {c.y + RH / 2 - 5}) scale({10 / 12})"
								d={c.icon.d}
								fill={c.icon.outline ? 'none' : c.ink}
								stroke={c.icon.outline ? c.ink : 'none'}
								stroke-width={ICON_STROKE}
								stroke-linejoin="round"
							/>
						{/if}
					</g>
				{/each}
				{#each cells as c, i (c.m.month)}
					{#if c.m.month === selected}
						<rect class="ring sel" x={c.x + 0.5} y={c.y + 0.5} width={CW - 1} height={RH - 1} rx="3" />
					{/if}
					{#if i === active}
						<rect class="ring act" data-export-skip x={c.x} y={c.y} width={CW} height={RH} rx="3" />
					{/if}
				{/each}
			</svg>
			{#if tip}
				<Tooltip x={tip.x} y={tip.y} parentWidth={wrapW} heading={tip.heading} rows={tip.rows} foot={tip.foot} />
			{/if}
		</div>
	</div>
	<p class="sr-only" aria-live="polite">{live}</p>

	{#snippet notes()}
		<p>The outlined cell is the month described in the answer card.</p>
	{/snippet}

	{#snippet table()}
		<table class="data">
			<caption class="sr-only">{title}: {modeInfo.label} by year and month</caption>
			<thead>
				<tr><th scope="col">Year</th>{#each MONTH_SHORT as m (m)}<th scope="col">{m}</th>{/each}</tr>
			</thead>
			<tbody>
				{#each years as y (y)}
					<tr>
						<th scope="row">{y}</th>
						{#each MONTH_SHORT as _m, mi (mi)}
							{@const row = months.find((r) => r.month === `${y}-${String(mi + 1).padStart(2, '0')}`)}
							<td>
								{#if row}
									{#if mode === 'anomaly'}
										{@const a = anom.get(row.month)}
										{!a || a.ratio === null ? '–' : `${a.ratio.toFixed(1)}×`}
									{:else}
										{fmt(metric(row))}
									{/if}{row.complete ? '' : '*'}
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="tnote">* incomplete month. {mode === 'anomaly' ? 'Values are multiples of the median for that calendar month.' : ''}</p>
	{/snippet}
</ChartFrame>

<style>
	.ctl {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-size: 0.9rem;
	}
	.lt {
		color: var(--text-2);
		flex-basis: 100%;
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
		box-shadow: inset 0 0 0 1px var(--border);
	}
	.sw.icon {
		display: inline-grid;
		place-items: center;
	}
	.scroll {
		overflow-x: auto;
	}
	.wrap {
		position: relative;
		min-width: 300px;
		max-width: 640px;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
		touch-action: manipulation;
	}
	svg:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
		border-radius: 4px;
	}
	.axis {
		font-size: 10px;
		fill: var(--text-2);
		font-family: var(--font);
	}
	.glyph {
		pointer-events: none;
	}
	.cell {
		cursor: pointer;
	}
	.ring {
		fill: none;
		pointer-events: none;
	}
	.ring.sel {
		stroke: var(--cell-ring);
		stroke-width: 1.5;
	}
	.ring.act {
		stroke: var(--focus);
		stroke-width: 2;
	}
	.tnote {
		font-size: 0.8rem;
		color: var(--text-2);
	}
</style>
