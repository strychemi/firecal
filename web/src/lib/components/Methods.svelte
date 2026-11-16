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

<!-- The full methods, as section cards in two columns on wide screens; the dialog that holds it
     (MethodsPanel) provides the title. -->
<div class="methods">
	<div class="cols">
		<section class="sec" aria-labelledby="m-counted">
			<h3 id="m-counted">What is counted</h3>
			<p class="lead">Counts are fire-days, not raw hotspots.</p>
			<ul>
				<li>
					A fire-day is one small hexagon (about 0.7 km², H3 level 8) where a satellite detected fire in one day or night pass of one local day,
					so a hexagon can count twice a day.
				</li>
				<li>We count fire-days because newer satellites have smaller pixels and split one fire into more hotspots, so raw hotspot counts jump when the satellite changes.</li>
				<li>Before February 2012 the counts are converted from MODIS to what VIIRS would have seen. The technical unit is VIIRS-equivalent burning cell-days.</li>
			</ul>
		</section>

		<section class="sec" aria-labelledby="m-one-sat">
			<h3 id="m-one-sat">One satellite per day</h3>
			<p class="lead">Each day uses one satellite, never a sum:</p>
			<ol class="timeline">
				<li><span class="when">Nov 2000</span> Terra MODIS</li>
				<li><span class="when">Aug 2002</span> Aqua MODIS</li>
				<li><span class="when">Feb 2012</span> S-NPP VIIRS</li>
				<li><span class="when">After S-NPP</span> NOAA-20 VIIRS, from S-NPP's last day</li>
			</ol>
			<p>
				Missing days are filled by a backup satellite where possible{#if Object.keys(filledBy).length}{' '}({global
						? `${place}: `
						: ''}{Object.entries(filledBy)
						.map(([k, v]) => `${v} days by ${sat(k)}`)
						.join(', ')}){/if}.
			</p>
		</section>

		<section class="sec" aria-labelledby="m-scale">
			<h3 id="m-scale">Converted to one scale</h3>
			<ul>
				<li>
					MODIS months are converted to what S-NPP VIIRS would have counted, using day and night multipliers fitted only on places and passes both
					satellites observed (2013–2022), from NASA's records of where each one looked.
				</li>
				<li>
					Each area has a multiplier for each season, because the kind of fire, and so how many fires VIIRS sees for each one MODIS sees, changes
					through the year{#if global}{' '}(except in Europe, where seasons did not pass the tests){/if}.
				</li>
				{#if global}
					<li>
						Each continent is fitted on its own, and each fire-day takes its own continent's multiplier. A search uses the error ranges and days with
						data of the continent holding most of its fire-days.
					</li>
					<li>Antarctica has too few fires to fit, so its months before February 2012 have no data.</li>
				{/if}
				<li>A place where neither satellite saw fire on those shared passes borrows the multiplier of the larger region around it.</li>
				<li>
					VIIRS months are observed, not converted. On days without S-NPP data, NOAA-20 is counted as S-NPP: fitted multipliers (about 1.01) did
					not improve on that, so none is applied.
				</li>
			</ul>
		</section>

		<section class="sec" aria-labelledby="m-range">
			<h3 id="m-range">The 80 % range</h3>
			<p class="lead">Converted months carry an 80 % range, built for the size of the area searched. In tests on years left out, the true count fell inside it:</p>
			<ul>
				<li>8 times out of 10 for areas from about 1,500 km² to 2° squares (about 40,000 km²);</li>
				<li>about 7 times out of 10 for the whole study area, where 12 months a year make the figure rough.</li>
			</ul>
		</section>

		<section class="sec" aria-labelledby="m-trend">
			<h3 id="m-trend">Trend</h3>
			<p class="lead">The answer card says whether the selected month has been rising or falling over the whole record.</p>
			<ul>
				<li>It uses that calendar month in every complete year, on the converted counts, so the 2012 change from MODIS to VIIRS does not look like a rise. It needs at least 10 years.</li>
				<li>The rate is the Theil–Sen slope: the middle of the slopes between every pair of years, shown as a share of the month's median. One extreme year barely moves it.</li>
				<li>"A steady change, unlikely to be chance" means the Mann–Kendall test gives p below 0.05: years that mostly go one way. Otherwise the drift is within normal year-to-year variation.</li>
				<li>Each year is treated as independent. A run of wet or dry years can make a trend look surer than it is, and the converted MODIS years carry their own error (see the 80 % range).</li>
			</ul>
		</section>

		<section class="sec" aria-labelledby="m-scores">
			<h3 id="m-scores">How well the conversion works{global && continent && continent !== 'World' ? `: ${continentName(continent)}` : ''}</h3>
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
		</section>

		<section class="sec" aria-labelledby="m-gaps">
			<h3 id="m-gaps">Known gaps</h3>
			{#if gaps.length}
				<p>Days with no satellite data in {place}. Those months are marked incomplete and left out of the "usual" comparison.</p>
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
		</section>

		<section class="sec" aria-labelledby="m-limits">
			<h3 id="m-limits">Limits</h3>
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
		</section>
	</div>

	<section class="sec credit" aria-labelledby="m-credit">
		<h3 id="m-credit">Data and credits</h3>
		<ul>
			<li>Fire data: NASA FIRMS (Fire Information for Resource Management System).</li>
			<li>MODIS: MCD14ML Collection 6 and 6.1, with 2000–2017 hotspot types from the MODIS fire team's version-3 files.</li>
			<li>VIIRS: 375 m active fires from S-NPP and NOAA-20.</li>
			<li>Data version {meta.data_version}, {meta.series_start} to {meta.series_end}.</li>
			<li>Unit: {meta.unit}.</li>
		</ul>
	</section>
</div>

<style>
	.methods {
		display: flex;
		flex-direction: column;
		gap: 16px;
		line-height: 1.55;
	}
	/* Two columns of cards on wide screens, filled top to bottom so the reading order stays the DOM order. */
	.cols {
		columns: 2 340px;
		column-gap: 16px;
	}
	.sec {
		break-inside: avoid;
		margin: 0 0 16px;
		padding: 14px 16px;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: var(--page);
	}
	.cols .sec:last-child {
		margin-bottom: 0;
	}
	h3 {
		font-size: 0.95rem;
		margin: 0 0 8px;
	}
	p,
	ul,
	ol {
		margin: 0;
		font-size: 0.9rem;
		max-width: 68ch;
	}
	p + ul,
	p + ol,
	ol + p,
	p + table {
		margin-top: 8px;
	}
	.lead {
		font-weight: 600;
	}
	ul,
	ol {
		padding-left: 20px;
	}
	li + li {
		margin-top: 6px;
	}
	.timeline {
		list-style: none;
		padding-left: 0;
		border-left: 2px solid var(--grid);
	}
	.timeline li {
		padding-left: 12px;
	}
	.timeline li + li {
		margin-top: 4px;
	}
	.when {
		display: inline-block;
		min-width: 6.5em;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		color: var(--text-2);
	}
	div.scroll {
		max-height: 16em;
		overflow-y: auto;
		margin-top: 8px;
	}
	div.scroll:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}
	.credit ul {
		max-width: none;
	}
	table.data {
		font-size: 0.85rem;
	}
	table.data th,
	table.data td {
		white-space: normal;
	}
</style>
