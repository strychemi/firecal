<script lang="ts">
	// The burning calendar as a time control: one column per year, one row per calendar month.
	// Click (or Enter on) a month to map it; click a year to map the whole year.
	// One tab stop; arrow keys move between months, Home/End jump to the series ends.
	import { MONTH_SHORT, SOURCE_LABEL, fmt, fmt1, monthLabel, monthNote } from '#lib/format.ts';
	import type { MonthRow, YearMonth } from '#lib/types.ts';
	import { classOf, quantileBreaks } from '#lib/map/helpers.ts';

	interface Props {
		months: MonthRow[];
		/** The month on the map (month mode), or '' */
		month: YearMonth;
		/** The year on the map (year mode), or 0 */
		year: number;
		/** Years compared (change mode), or 0 */
		yearA: number;
		yearB: number;
		onmonth: (m: YearMonth) => void;
		onyear: (y: number) => void;
		busy?: boolean;
	}
	let { months, month, year, yearA, yearB, onmonth, onyear, busy = false }: Props = $props();

	const byMonth = $derived(new Map(months.map((m) => [m.month, m])));
	const years = $derived.by(() => {
		if (!months.length) return [] as number[];
		const a = Number(months[0].month.slice(0, 4));
		const b = Number(months[months.length - 1].month.slice(0, 4));
		return Array.from({ length: b - a + 1 }, (_, i) => a + i);
	});
	const breaks = $derived(quantileBreaks(months.map((m) => m.value)));
	const k = $derived(breaks.length + 1);
	const fillOf = (v: number) => {
		if (!(v > 0)) return 'var(--seq-0)';
		const i = classOf(v, breaks);
		const step = k <= 1 ? 6 : Math.round((i * 6) / (k - 1));
		return `var(--seq-${step + 1})`;
	};
	const legend = $derived.by(() => {
		const out: { label: string; color: string }[] = [{ label: '0', color: 'var(--seq-0)' }];
		for (let i = 0; i < k; i++) {
			const step = k <= 1 ? 6 : Math.round((i * 6) / (k - 1));
			const label = breaks.length === 0 ? 'any' : i === 0 ? `<${fmt(breaks[0])}` : i === breaks.length ? `${fmt(breaks[i - 1])}+` : `${fmt(breaks[i - 1])}–${fmt(breaks[i])}`;
			out.push({ label, color: `var(--seq-${step + 1})` });
		}
		return out;
	});

	const ym = (y: number, m: number) => `${y}-${String(m + 1).padStart(2, '0')}`;
	const label = (r: MonthRow) => {
		const note = monthNote(r);
		return `${monthLabel(r.month)}: ${fmt1(r.value)} fire-days, ${SOURCE_LABEL[r.source]}${note ? `, ${note}` : ''}`;
	};

	// Roving focus: the selected month (or the last month) holds the one tab stop.
	const focusMonth = $derived(byMonth.has(month) ? month : (months[months.length - 1]?.month ?? ''));
	let grid: HTMLDivElement;
	function onKey(e: KeyboardEvent) {
		const t = e.target as HTMLElement;
		const cur = t.dataset.month;
		if (!cur) return;
		let [y, m] = cur.split('-').map(Number);
		m -= 1;
		if (e.key === 'ArrowRight') y += 1;
		else if (e.key === 'ArrowLeft') y -= 1;
		else if (e.key === 'ArrowDown') m += 1;
		else if (e.key === 'ArrowUp') m -= 1;
		else if (e.key === 'Home') [y, m] = months[0].month.split('-').map((x, i) => Number(x) - i);
		else if (e.key === 'End') [y, m] = months[months.length - 1].month.split('-').map((x, i) => Number(x) - i);
		else return;
		if (m < 0) {
			m = 11;
			y -= 1;
		} else if (m > 11) {
			m = 0;
			y += 1;
		}
		const next = grid.querySelector<HTMLButtonElement>(`[data-month="${ym(y, m)}"]`);
		if (next) {
			e.preventDefault();
			next.focus();
		}
	}
</script>

<div class="cal" aria-busy={busy}>
	<div class="scroll">
		<div
			class="grid"
			bind:this={grid}
			style="--n:{years.length}"
			role="group"
			aria-label="Burning calendar: fire-days per month, one column per year. Arrow keys move, Enter maps the month."
		>
			<span></span>
			{#each years as y (y)}
				<button
					type="button"
					class="yr"
					class:on={year === y}
					class:mark={yearA === y || yearB === y}
					onclick={() => onyear(y)}
					aria-pressed={year === y}
					aria-label="Map all of {y}{yearA === y ? ' (year A)' : yearB === y ? ' (year B)' : ''}"
					title="Map all of {y}"
				>
					{#if yearA === y}<b>A</b>{:else if yearB === y}<b>B</b>{/if}{String(y).slice(2)}
				</button>
			{/each}
			{#each MONTH_SHORT as mname, mi (mname)}
				<span class="mlab">{mname}</span>
				{#each years as y (y)}
					{@const key = ym(y, mi)}
					{@const r = byMonth.get(key)}
					{#if r}
						<button
							type="button"
							class="cell"
							class:sel={month === key}
							class:inyear={year === y}
							class:incomplete={!r.complete}
							data-month={key}
							tabindex={key === focusMonth ? 0 : -1}
							style="background-color:{fillOf(r.value)}"
							aria-label={label(r)}
							aria-pressed={month === key}
							title={label(r)}
							onclick={() => onmonth(key)}
							onkeydown={onKey}
						></button>
					{:else}
						<span class="cell none" aria-hidden="true"></span>
					{/if}
				{/each}
			{/each}
		</div>
	</div>
	<div class="legend" aria-label="Calendar legend">
		<span>Fire-days per month:</span>
		{#each legend as l (l.label)}
			<span class="li"><i class="swatch" style="background:{l.color}"></i>{l.label}</span>
		{/each}
		<span class="li"><i class="swatch hatch"></i>incomplete or in progress</span>
		<span class="li"><i class="swatch ring"></i>on the map</span>
	</div>
</div>

<style>
	.cal {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-height: 0;
		height: 100%;
	}
	.cal[aria-busy='true'] .grid {
		opacity: 0.6;
	}
	.scroll {
		overflow-x: auto;
		overflow-y: hidden;
		flex: 1;
		min-height: 0;
		scrollbar-width: thin;
	}
	.grid {
		display: grid;
		grid-template-columns: 30px repeat(var(--n), minmax(18px, 1fr));
		grid-template-rows: 22px repeat(12, minmax(9px, 1fr));
		gap: 2px;
		height: 100%;
		min-width: calc(30px + var(--n) * 20px);
		transition: opacity 0.2s;
	}
	.yr {
		border: 0;
		background: transparent;
		color: var(--text-2);
		font: inherit;
		font-size: 0.7rem;
		padding: 0;
		cursor: pointer;
		border-radius: 4px;
		white-space: nowrap;
	}
	.yr:hover {
		background: var(--wash);
		color: var(--text);
	}
	.yr.on {
		background: var(--accent);
		color: var(--accent-ink);
		font-weight: 600;
	}
	.yr.mark {
		color: var(--text);
		font-weight: 600;
	}
	.yr b {
		font-size: 0.62rem;
		margin-right: 1px;
	}
	.mlab {
		font-size: 0.68rem;
		color: var(--text-2);
		align-self: center;
	}
	.cell {
		border: 0;
		padding: 0;
		border-radius: 2px;
		cursor: pointer;
		min-height: 0;
		position: relative;
	}
	.cell.none {
		background: transparent;
		cursor: default;
	}
	.cell.incomplete {
		background-image: repeating-linear-gradient(45deg, var(--hatch) 0 1px, transparent 1px 4px);
	}
	.cell.inyear {
		box-shadow: inset 0 0 0 1px var(--accent);
	}
	.cell:hover {
		outline: 1px solid var(--text-2);
		outline-offset: 0;
	}
	.cell.sel {
		outline: 2px solid var(--cell-ring);
		outline-offset: 1px;
		z-index: 1;
	}
	.cell:focus-visible,
	.yr:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 1px;
		z-index: 2;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 2px 10px;
		font-size: 0.72rem;
		color: var(--text-2);
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.swatch.hatch {
		background: var(--seq-0) repeating-linear-gradient(45deg, var(--hatch) 0 1px, transparent 1px 4px);
	}
	.swatch.ring {
		background: transparent;
		outline: 2px solid var(--cell-ring);
		outline-offset: -2px;
	}
</style>
