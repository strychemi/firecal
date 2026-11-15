<script lang="ts">
	import type { Meta } from '#lib/types.ts';

	let { meta }: { meta: Meta } = $props();

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
				{#if Object.keys(meta.days_filled_by).length}
					({Object.entries(meta.days_filled_by)
						.map(([k, v]) => `${v} days by ${sat(k)}`)
						.join(', ')})
				{/if}.
			</p>
			<h3>Converted to one scale</h3>
			<p>
				MODIS months are converted to what S-NPP VIIRS would have counted, using day and night multipliers fitted where
				both satellites flew (2013–2022). VIIRS months are observed, not converted. On days without S-NPP data, NOAA-20
				is counted as S-NPP: fitted multipliers (about 1.01) did not improve on that, so none is applied. Converted months carry an
				<strong>80 % range</strong>: in tests, 8 times out of 10 the true count fell inside it.
			</p>
		</div>
		<div>
			<h3>How well the conversion works</h3>
			<p>Typical error against S-NPP when predicting a year left out of the fit:</p>
			<table class="data">
				<thead>
					<tr><th scope="col">Satellite</th><th scope="col">Whole study area</th><th scope="col">Small areas</th><th scope="col">Gap at the join</th></tr>
				</thead>
				<tbody>
					{#each Object.entries(meta.validation) as [k, v] (k)}
						<tr>
							<th scope="row">{sat(k)}{v.converted === false ? ' (no conversion)' : ''}</th>
							<td>{pct(v.whole_area_typical_error_pct)}</td>
							<td>{pct(v.small_area_typical_error_pct)}</td>
							<td>{pct(v.backward_join_gap_pct)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<h3>Known gaps</h3>
			{#if meta.gaps.length}
				<p>Days with no satellite data in the study region (those months are marked incomplete and left out of the "usual" comparison):</p>
				<ul>
					{#each meta.gaps as g (g.start)}
						<li>{g.start === g.end ? fmtDate(g.start) : `${fmtDate(g.start)} – ${fmtDate(g.end)}`} ({g.days} {g.days === 1 ? 'day' : 'days'})</li>
					{/each}
				</ul>
			{:else}
				<p>None.</p>
			{/if}
			<h3>Limits</h3>
			<ul>
				<li>Values before 2012 are a conversion that cannot be checked directly.</li>
				<li>The conversion tends to overshoot in busy months and undershoot in quiet ones.</li>
				<li>Small areas are noisier; their ranges are wider.</li>
				<li>Study region only for now: {meta.region.countries.map((c) => c.replace(/_/g, ' ')).join(', ')} (parts of).</li>
			</ul>
		</div>
	</div>
	<p class="credit">
		Fire data: NASA FIRMS (MODIS MCD14ML C6.1, VIIRS 375 m S-NPP and NOAA-20). Data version {meta.data_version}, {meta.series_start} to
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
