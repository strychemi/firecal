<script lang="ts">
	// Typical fire season: the usual value of each calendar month (median or mean over complete
	// years) as bars, with one year's months as a line on top, and the peak season named in words.
	import { MONTH_NAMES, MONTH_SHORT, fmt, fmt1, fmtTick, median } from '#lib/format.ts';
	import { downloadPng, downloadSvg } from '#lib/download.ts';
	import { niceTicks } from '#lib/scales.ts';
	import type { Baseline, MonthRow } from '#lib/types.ts';

	interface Props {
		months: MonthRow[];
		baseline: Baseline;
		year: number;
		filename: string;
	}
	let { months, baseline, year, filename }: Props = $props();

	const typical = $derived.by(() =>
		Array.from({ length: 12 }, (_, i) => {
			const xs = months.filter((m) => m.complete && Number(m.month.slice(5)) === i + 1).map((m) => m.value);
			return {
				value: xs.length ? (baseline === 'mean' ? xs.reduce((s, x) => s + x, 0) / xs.length : median(xs)) : 0,
				n: xs.length
			};
		})
	);
	const nYears = $derived(Math.max(...typical.map((t) => t.n)));
	const yearRows = $derived(
		Array.from({ length: 12 }, (_, i) => months.find((m) => m.month === `${year}-${String(i + 1).padStart(2, '0')}`) ?? null)
	);

	/** The run of months around the busiest one that are at least half as busy (wrapping Dec→Jan). */
	const season = $derived.by(() => {
		const v = typical.map((t) => t.value);
		const max = Math.max(...v);
		if (!(max > 0)) return null;
		const top = v.indexOf(max);
		let a = top;
		let b = top;
		for (let s = 0; s < 11 && v[(a + 11) % 12] >= max / 2 && (a + 11) % 12 !== b; s++) a = (a + 11) % 12;
		for (let s = 0; s < 11 && v[(b + 1) % 12] >= max / 2 && (b + 1) % 12 !== a; s++) b = (b + 1) % 12;
		const share = (() => {
			const tot = v.reduce((s, x) => s + x, 0);
			let sum = 0;
			for (let i = a; ; i = (i + 1) % 12) {
				sum += v[i];
				if (i === b) break;
			}
			return tot > 0 ? sum / tot : 0;
		})();
		return { a, b, top, share };
	});
	const sentence = $derived(
		!season
			? 'No fire in any complete year here, so there is no fire season to show.'
			: `Fire season peaks in ${season.a === season.b ? MONTH_NAMES[season.a] : `${MONTH_NAMES[season.a]}–${MONTH_NAMES[season.b]}`}` +
					` (busiest: ${MONTH_NAMES[season.top]}), with ${Math.round(season.share * 100)} % of a usual year's fire-days.`
	);

	let w = $state(320);
	const H = 190;
	const M = { top: 12, right: 8, bottom: 22, left: 36 };
	const iw = $derived(Math.max(10, w - M.left - M.right));
	const ih = H - M.top - M.bottom;
	const max = $derived(Math.max(1, ...typical.map((t) => t.value), ...yearRows.map((r) => r?.value ?? 0)));
	const ticks = $derived(niceTicks(max, 4));
	const top = $derived(ticks[ticks.length - 1]);
	const y = (v: number) => M.top + ih - (v / top) * ih;
	const bw = $derived(iw / 12);
	const x = (i: number) => M.left + i * bw;
	const line = $derived(
		yearRows
			.map((r, i) => (r ? `${x(i) + bw / 2},${y(r.value)}` : null))
			.filter(Boolean)
			.join(' ')
	);

	let svg = $state<SVGSVGElement | null>(null);
	const title = $derived(`Typical fire season (${baseline} of ${nYears} years) and ${year}`);
	let tableOpen = $state(false);
</script>

<section class="prof" aria-labelledby="prof-h">
	<div class="head">
		<h3 id="prof-h">Typical fire season</h3>
		<div class="dl">
			<button type="button" class="pbtn" onclick={() => svg && downloadSvg(svg, `${filename}.svg`, title)}>SVG</button>
			<button type="button" class="pbtn" onclick={() => svg && downloadPng(svg, `${filename}.png`, title)}>PNG</button>
		</div>
	</div>
	<p class="sent">{sentence}</p>
	<div class="legend">
		<span class="li"><i class="swatch" style="background:var(--seq-3)"></i>Usual month ({baseline === 'median' ? 'median' : 'mean'} of {nYears} years)</span>
		<span class="li"><i class="ln"></i>{year}</span>
	</div>
	<div class="plot" bind:clientWidth={w}>
		<svg bind:this={svg} width={w} height={H} role="img" aria-label="{title}. {sentence}">
			{#each ticks as t (t)}
				<line x1={M.left} x2={M.left + iw} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
				<text x={M.left - 4} y={y(t)} text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--muted)">{fmtTick(t)}</text>
			{/each}
			{#each typical as t, i (i)}
				{@const h = Math.max(0, y(0) - y(t.value))}
				<path
					d="M{x(i) + 2},{y(0)} v{-Math.max(0, h - 3)} q0,-3 3,-3 h{Math.max(0, bw - 10)} q3,0 3,3 v{Math.max(0, h - 3)} z"
					fill={season && (season.a <= season.b ? i >= season.a && i <= season.b : i >= season.a || i <= season.b) ? 'var(--seq-4)' : 'var(--seq-2)'}
				>
					<title>{MONTH_NAMES[i]}: usual {fmt1(t.value)} fire-days; {year}: {yearRows[i] ? fmt1(yearRows[i]!.value) : 'no data'}</title>
				</path>
				<text x={x(i) + bw / 2} y={H - 6} text-anchor="middle" font-size="10" fill="var(--muted)">{MONTH_SHORT[i][0]}</text>
			{/each}
			<line x1={M.left} x2={M.left + iw} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
			<polyline points={line} fill="none" stroke="var(--text)" stroke-width="2" stroke-linejoin="round" />
			{#each yearRows as r, i (i)}
				{#if r}
					<circle cx={x(i) + bw / 2} cy={y(r.value)} r="4" fill={r.complete ? 'var(--text)' : 'var(--surface)'} stroke="var(--text)" stroke-width="1.5" />
				{/if}
			{/each}
		</svg>
	</div>
	<button type="button" class="linkish" aria-expanded={tableOpen} onclick={() => (tableOpen = !tableOpen)}>{tableOpen ? 'Hide' : 'Show'} table</button>
	{#if tableOpen}
		<table>
			<thead><tr><th>Month</th><th>Usual</th><th>{year}</th></tr></thead>
			<tbody>
				{#each typical as t, i (i)}
					<tr><td>{MONTH_NAMES[i]}</td><td>{fmt(t.value)}</td><td>{yearRows[i] ? fmt(yearRows[i]!.value) : '–'}</td></tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>

<style>
	.prof {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	h3 {
		font-size: 0.95rem;
		margin: 0;
	}
	.dl {
		display: flex;
		gap: 4px;
	}
	.dl .pbtn {
		min-height: 26px;
		font-size: 0.75rem;
	}
	.sent {
		margin: 0;
		font-size: 0.86rem;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		font-size: 0.75rem;
		color: var(--text-2);
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.ln {
		display: inline-block;
		width: 16px;
		height: 2px;
		background: var(--text);
	}
	.plot {
		width: 100%;
	}
	svg {
		display: block;
	}
	.linkish {
		align-self: flex-start;
		background: none;
		border: 0;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-size: 0.78rem;
		cursor: pointer;
	}
	table {
		font-size: 0.78rem;
		border-collapse: collapse;
	}
	th,
	td {
		text-align: right;
		padding: 2px 8px;
		border-bottom: 1px solid var(--grid);
	}
	th:first-child,
	td:first-child {
		text-align: left;
	}
</style>
