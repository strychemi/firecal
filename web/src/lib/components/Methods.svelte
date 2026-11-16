<script lang="ts">
	import { continentName, isGlobal } from '#lib/format.ts';
	import type { Meta, QueryResponse } from '#lib/types.ts';

	let { meta, data = null }: { meta: Meta; data?: QueryResponse | null } = $props();

	// The global app has one model per continent: show the numbers of the continent the search used.
	const global = $derived(isGlobal(meta));
	const continent = $derived(global && data?.continent ? data.continent : null);
	const info = $derived(continent ? meta.continents?.[continent] : undefined);
	const validation = $derived(global ? (info?.validation ?? {}) : meta.validation);
	const gaps = $derived(info?.gaps ?? meta.gaps);
	const filledBy = $derived(info?.days_filled_by ?? meta.days_filled_by);
	const place = $derived(continent && continent !== 'World' ? continentName(continent) : global ? 'the whole globe' : 'the study region');

	const SAT: Record<string, string> = {
		terra: 'Terra MODIS',
		aqua: 'Aqua MODIS',
		snpp: 'S-NPP VIIRS',
		noaa20: 'NOAA-20 VIIRS'
	};
	const sat = (k: string) => SAT[k] ?? k;
	const pct = (n: number) => `${n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 2 })} %`;
	const fmtDate = (d: string) =>
		new Date(`${d}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
</script>

<section class="card methods" aria-labelledby="methods-title">
	<h2 id="methods-title">Methods and limits</h2>

	<div class="cols">
		<div>
			<h3>What is counted</h3>
			<p>
				<strong>Counts are fire-days, not raw hotspots.</strong> A fire-day is one small hexagon (about 0.7 km²,
				H3 level 8) where a satellite detected fire in one day or night pass of one local day, so a hexagon can count
				twice a day. We count fire-days because newer satellites have smaller pixels and split one fire into more hotspots,
				so raw hotspot counts jump when the satellite changes. Before February 2012 the counts are converted from MODIS
				to what VIIRS would have seen; the technical unit is VIIRS-equivalent burning cell-days.
			</p>
			<h3>One satellite per day</h3>
			<p>
				Each day uses one satellite, never a sum: Terra MODIS from November 2000, Aqua MODIS from August 2002, and S-NPP
				VIIRS from February 2012, with NOAA-20 VIIRS taking over after S-NPP's last day. Missing days are filled by a
				backup satellite where possible
				{#if Object.keys(filledBy).length}
					({global ? `${place}: ` : ''}{Object.entries(filledBy)
						.map(([k, v]) => `${v} days by ${sat(k)}`)
						.join(', ')})
				{/if}.
			</p>
			<h3>Converted to one scale</h3>
			<p>
				MODIS months are converted to what S-NPP VIIRS would have counted, using day and night multipliers fitted only on
				places and passes both satellites observed (2013–2022), from NASA's records of where each one looked.
				Each area has a multiplier for each season, because the kind of fire, and so how many fires VIIRS sees
				for each one MODIS sees, changes through the year{#if global} (except in Europe, where seasons did not pass
				the tests){/if}.
				{#if global}
					Each continent is fitted on its own, and each fire-day takes its own continent's multiplier; a search
					uses the error ranges and days with data of the continent holding most of its fire-days. Antarctica has
					too few fires to fit, so its months before February 2012 have no data.
				{/if}
				A place where
				neither satellite saw fire on those shared passes borrows the multiplier of the larger region around it. VIIRS months are observed, not converted. On days without S-NPP data, NOAA-20
				is counted as S-NPP: fitted multipliers (about 1.01) did not improve on that, so none is applied. Converted months carry an
				<strong>80 % range</strong>, built for the size of the area searched: in tests on years left out, the true
				count fell inside it 8 times out of 10 for areas from about 1,500 km² to 2° squares (about 40,000 km²), and about 7
				times out of 10 for the whole study area, where 12 months a year make the figure rough.
			</p>
		</div>
		<div>
			<h3>How well the conversion works{global && continent && continent !== 'World' ? `: ${continentName(continent)}` : ''}</h3>
			{#if global && (!continent || continent === 'World')}
				<p>Each continent has its own scores; search an area with fire to see its continent's.</p>
			{:else if global && info && !info.fitted}
				<p>{continentName(continent!)} has no fitted model, so there are no scores; its MODIS months have no data.</p>
			{:else}
			<p>Typical error against S-NPP when predicting a year left out of the fit{global ? ` in ${place}` : ''}:</p>
			<table class="data">
				<thead>
					<tr><th scope="col">Satellite</th><th scope="col">Whole study area</th><th scope="col">Small areas</th><th scope="col">Gap at the join</th></tr>
				</thead>
				<tbody>
					{#each Object.entries(validation) as [k, v] (k)}
						<tr>
							<th scope="row">{sat(k)}{v.converted === false ? ' (no conversion)' : ''}</th>
							<td>{pct(v.whole_area_typical_error_pct)}</td>
							<td>{pct(v.small_area_typical_error_pct)}</td>
							<td>{pct(v.backward_join_gap_pct)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			{/if}
			<h3>Known gaps</h3>
			{#if gaps.length}
				<p>Days with no satellite data in {place} (those months are marked incomplete and left out of the "usual" comparison):</p>
				{#snippet gapList()}
					<ul>
						{#each gaps as g (g.start)}
							<li>{g.start === g.end ? fmtDate(g.start) : `${fmtDate(g.start)} – ${fmtDate(g.end)}`} ({g.days} {g.days === 1 ? 'day' : 'days'})</li>
						{/each}
					</ul>
				{/snippet}
				{#if gaps.length > 12}
					<!-- A long list scrolls; tabindex lets keyboard users focus and scroll it (axe: scrollable-region-focusable). -->
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div class="scroll" role="region" aria-label="Known gaps, {gaps.length} periods" tabindex="0">{@render gapList()}</div>
				{:else}
					{@render gapList()}
				{/if}
			{:else}
				<p>None.</p>
			{/if}
			<h3>Limits</h3>
			<ul>
				<li>Values before 2012 are a conversion that cannot be checked directly.</li>
				<li>The conversion tends to overshoot in busy months and undershoot in quiet ones.</li>
				<li>Small areas are noisier; their ranges are wider.</li>
				{#if global}
					<li>Archive only, November 2000 to {meta.series_end}: no recent days yet, and no hotspot CSV.</li>
				{:else}
					<li>Study region only for now: {[meta.region.countries].flat().map((c) => c.replace(/_/g, ' ')).join(', ')} (parts of).</li>
				{/if}
			</ul>
		</div>
	</div>
	<p class="credit">
		Fire data: NASA FIRMS (MODIS MCD14ML C6/C6.1, with 2000–2017 hotspot types from the MODIS fire team's version-3 files; VIIRS 375 m S-NPP and NOAA-20). Data version {meta.data_version}, {meta.series_start} to
		{meta.series_end}. Unit: {meta.unit}.
	</p>
</section>

<style>
	.methods {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	h2 {
		font-size: 1.1rem;
	}
	h3 {
		font-size: 0.95rem;
		margin-top: 12px;
	}
	p,
	ul {
		margin: 4px 0;
		font-size: 0.9rem;
		max-width: 68ch;
	}
	ul {
		padding-left: 18px;
	}
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 0 32px;
	}
	div.scroll {
		max-height: 16em;
		overflow-y: auto;
	}
	div.scroll:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}
	.credit {
		margin-top: 12px;
		padding-top: 12px;
		border-top: 1px solid var(--grid);
		color: var(--text-2);
		font-size: 0.85rem;
		max-width: none;
	}
	table.data th,
	table.data td {
		white-space: normal;
	}
</style>
