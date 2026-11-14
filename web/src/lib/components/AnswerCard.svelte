<script lang="ts">
	import { SOURCE_LABEL, fmt, monthLabel } from '#lib/format.ts';
	import { CATEGORY_GLYPH, CATEGORY_INK, CATEGORY_VAR } from '#lib/scales.ts';
	import type { MonthRow, QueryResponse } from '#lib/types.ts';

	interface Props {
		data: QueryResponse;
		areaName: string;
		busy?: boolean;
		computedLocally?: boolean;
	}
	let { data, areaName, busy = false, computedLocally = false }: Props = $props();

	const s = $derived(data.stats);
	const row = $derived<MonthRow | undefined>(data.months.find((m) => m.month === s.month));
	const nYears = $derived(s.baseline_years.length);
	const baselineWord = $derived(s.baseline === 'median' ? 'median' : 'average (mean)');
</script>

<section class="card answer" class:busy aria-labelledby="answer-title" aria-live="polite">
	<h2 id="answer-title" class="eyebrow">{areaName} · {monthLabel(s.month)}</h2>
	<p class="sentence">{s.sentence}</p>

	<div class="facts">
		<div class="fact">
			<span class="label">Burning places</span>
			<span class="big">{fmt(s.value)}</span>
			{#if s.lower !== null && s.upper !== null}
				<span class="small">80 % range {fmt(s.lower)}–{fmt(s.upper)}</span>
			{:else}
				<span class="small">{s.source === 'viirs' ? 'Observed by VIIRS (no conversion, no range)' : 'No range'}</span>
			{/if}
		</div>
		<div class="fact">
			<span class="label">Usual {monthLabel(s.month).split(' ')[0]}</span>
			<span class="big">{fmt(s.baseline_value)}</span>
			<span class="small">{baselineWord} of {nYears} {nYears === 1 ? 'year' : 'years'}</span>
		</div>
		<div class="fact">
			<span class="label">Compared with usual</span>
			{#if s.category}
				<span class="cat">
					<span class="chip" style:background={CATEGORY_VAR[s.category]} style:color={CATEGORY_INK[s.category]} aria-hidden="true">
						{CATEGORY_GLYPH[s.category]}
					</span>
					<span class="cat-text">{s.category}</span>
				</span>
				<span class="small">{s.ratio !== null ? `${s.ratio.toFixed(2)}× the ${s.baseline}` : ''}</span>
			{:else}
				<span class="cat-text">Usually no fire this month</span>
			{/if}
		</div>
		<div class="fact">
			<span class="label">Rank</span>
			<span class="big">{s.rank}<span class="of"> of {s.of}</span></span>
			<span class="small">1 = most burning{s.percentile !== null ? `; busier than ${s.percentile}% of years` : ''}</span>
		</div>
	</div>

	<ul class="meta">
		<li>Compared with {nYears} other complete {nYears === 1 ? 'year' : 'years'} of {monthLabel(s.month).split(' ')[0]} across the whole record.</li>
		<li>Source: {SOURCE_LABEL[s.source]}.</li>
		{#if row && !row.complete}
			<li class="warn">
				<span aria-hidden="true">⚠</span> Incomplete month: satellite data on {row.days_with_data} of {row.days} days, so the
				count is likely too low.
			</li>
		{/if}
		{#if computedLocally}
			<li>Worked out in your browser from the example data, using the same rules as the API.</li>
		{/if}
	</ul>
</section>

<style>
	.answer {
		display: flex;
		flex-direction: column;
		gap: 14px;
		transition: opacity 0.2s;
	}
	.answer.busy {
		opacity: 0.5;
	}
	.eyebrow {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--text-2);
		text-transform: none;
	}
	.sentence {
		margin: 0;
		font-size: clamp(1.25rem, 3.4vw, 1.75rem);
		line-height: 1.3;
		font-weight: 600;
		max-width: 46ch;
		text-wrap: pretty;
	}
	.facts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 12px;
	}
	.fact {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 10px 12px;
		border-radius: 8px;
		background: var(--wash);
		min-width: 0;
	}
	.label {
		font-size: 0.8rem;
		color: var(--text-2);
	}
	.big {
		font-size: 1.5rem;
		font-weight: 650;
		line-height: 1.2;
	}
	.of {
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-2);
	}
	.small {
		font-size: 0.8rem;
		color: var(--text-2);
	}
	.cat {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.chip {
		display: inline-grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border-radius: 6px;
		font-weight: 700;
		box-shadow: inset 0 0 0 1px var(--border);
		flex: none;
	}
	.cat-text {
		font-weight: 650;
		font-size: 1.05rem;
		line-height: 1.2;
	}
	.meta {
		margin: 0;
		padding-left: 18px;
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.warn {
		color: var(--text);
	}
</style>
