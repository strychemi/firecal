<script lang="ts">
	// Year + month selects (works everywhere, unlike <input type="month">).
	import { MONTH_NAMES } from '#lib/format.ts';
	import type { YearMonth } from '#lib/types.ts';

	interface Props {
		id: string;
		label: string;
		value: YearMonth;
		min: YearMonth;
		max: YearMonth;
		onchange: (v: YearMonth) => void;
	}
	let { id, label, value, min, max, onchange }: Props = $props();

	const y = $derived(Number(value.slice(0, 4)));
	const m = $derived(Number(value.slice(5)));
	const yMin = $derived(Number(min.slice(0, 4)));
	const yMax = $derived(Number(max.slice(0, 4)));
	const years = $derived(Array.from({ length: yMax - yMin + 1 }, (_, i) => yMin + i));

	const ym = (yy: number, mm: number) => `${yy}-${String(mm).padStart(2, '0')}`;
	const clamp = (v: YearMonth) => (v < min ? min : v > max ? max : v);
	const allowed = (mm: number) => {
		const v = ym(y, mm);
		return v >= min && v <= max;
	};
</script>

<fieldset class="mp">
	<legend>{label}</legend>
	<label class="sr-only" for="{id}-m">{label}: month</label>
	<select id="{id}-m" value={m} onchange={(e) => onchange(clamp(ym(y, Number(e.currentTarget.value))))}>
		{#each MONTH_NAMES as name, i (name)}
			<option value={i + 1} disabled={!allowed(i + 1)}>{name.slice(0, 3)}</option>
		{/each}
	</select>
	<label class="sr-only" for="{id}-y">{label}: year</label>
	<select id="{id}-y" value={y} onchange={(e) => onchange(clamp(ym(Number(e.currentTarget.value), m)))}>
		{#each years as yy (yy)}
			<option value={yy}>{yy}</option>
		{/each}
	</select>
</fieldset>

<style>
	.mp {
		border: 0;
		padding: 0;
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		align-items: center;
		min-width: 0;
	}
	legend {
		font-size: 0.8rem;
		color: var(--text-2);
		padding: 0;
		margin-bottom: 4px;
		float: left;
		width: 100%;
	}
	select {
		min-height: 36px;
		padding: 4px 6px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
	}
</style>
