<script lang="ts">
	// The limits that matter for this answer, in two lines, with the full methods in a dialog.
	import Methods from './Methods.svelte';
	import { continentName, isGlobal } from '#lib/format.ts';
	import type { Meta, QueryResponse } from '#lib/types.ts';

	let { meta, data }: { meta: Meta; data: QueryResponse } = $props();

	const global = $derived(isGlobal(meta));
	const info = $derived(global && data.continent ? meta.continents?.[data.continent] : undefined);
	const validation = $derived(global ? (info?.validation ?? {}) : meta.validation);
	const gaps = $derived(info?.gaps ?? meta.gaps);
	const place = $derived(global && data.continent && data.continent !== 'World' ? continentName(data.continent) : global ? 'the globe' : 'the study region');

	const SAT: Record<string, string> = { terra: 'Terra', aqua: 'Aqua' };
	const pct = (n: number) => `${n.toLocaleString('en-US', { maximumFractionDigits: 1 })} %`;
	const errors = $derived(
		Object.entries(validation)
			.filter(([k, v]) => k in SAT && v.converted !== false)
			.map(([k, v]) => `${SAT[k]} ${pct(v.small_area_typical_error_pct)}`)
	);
	const converted = $derived(data.start < '2012-02');
	const gapsHere = $derived(gaps.filter((g) => g.end >= `${data.start}-01` && g.start <= `${data.end}-31`));
	const gapDays = $derived(gapsHere.reduce((s, g) => s + g.days, 0));

	let dialog = $state<HTMLDialogElement | null>(null);

	// closedby="any" closes the dialog on a click outside it; Safari lacks it, so do the same there.
	// Test the pointer position, not the target: the dialog is also the target of its own padding.
	let pressedOutside = false;
	const outside = (e: PointerEvent) => {
		const r = dialog!.getBoundingClientRect();
		return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
	};
	const needsFallback = typeof HTMLDialogElement !== 'undefined' && !('closedBy' in HTMLDialogElement.prototype);
	function down(e: PointerEvent) {
		if (needsFallback) pressedOutside = outside(e);
	}
	function up(e: PointerEvent) {
		if (needsFallback && pressedOutside && outside(e)) dialog?.close();
	}
</script>

<section class="card summary" aria-labelledby="limits-title">
	<h2 id="limits-title">Limits for this answer</h2>
	<ul>
		{#if converted}
			<li>
				Months before February 2012 are converted from MODIS to the VIIRS scale{#if errors.length}; typical error for small areas in {place}: {errors.join(', ')}{/if}.
			</li>
		{:else}
			<li>All these months are observed by VIIRS: no conversion.</li>
		{/if}
		<li>
			{#if gapsHere.length}
				{gapsHere.length} {gapsHere.length === 1 ? 'period' : 'periods'} ({gapDays} {gapDays === 1 ? 'day' : 'days'}) without satellite data in these dates; those months are marked incomplete.
			{:else}
				No days without satellite data in these dates.
			{/if}
		</li>
	</ul>
	<button class="btn" type="button" aria-haspopup="dialog" onclick={() => dialog?.showModal()}>Methods and limits</button>
</section>

<!-- Esc closes natively; closedby="any" also closes on a click outside where supported. -->
<dialog bind:this={dialog} aria-labelledby="methods-title" closedby="any" onpointerdown={down} onpointerup={up}>
	<header class="head">
		<div>
			<h2 id="methods-title">Methods and limits</h2>
			<p class="sub">How firecal counts and converts fire, how well it works{global && data.continent && data.continent !== 'World' ? ` in ${place}` : ''}, and what it cannot tell you.</p>
		</div>
		<form method="dialog">
			<!-- svelte-ignore a11y_autofocus -->
			<button class="btn" type="submit" autofocus>Close</button>
		</form>
	</header>
	<div class="body">
		<Methods {meta} {data} />
	</div>
</dialog>

<style>
	.summary h2 {
		font-size: 1rem;
		margin: 0 0 6px;
	}
	ul {
		margin: 0 0 10px;
		padding-left: 18px;
		font-size: 0.88rem;
	}
	li + li {
		margin-top: 4px;
	}
	dialog {
		width: min(1000px, calc(100vw - 32px));
		max-height: calc(100dvh - 48px);
		padding: 0;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--surface);
		color: var(--text);
		overflow: auto;
	}
	/* Scrolling inside the dialog or over the backdrop must not scroll the page behind it. */
	dialog:modal {
		overscroll-behavior: contain;
	}
	dialog::backdrop {
		background: rgb(0 0 0 / 0.45);
		overflow: hidden;
		overscroll-behavior: contain;
	}
	.head {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		padding: 16px 20px 12px;
		background: var(--surface);
		border-bottom: 1px solid var(--border);
	}
	.head h2 {
		margin: 0;
		font-size: 1.15rem;
	}
	.sub {
		margin: 4px 0 0;
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.body {
		padding: 16px 20px 20px;
	}
</style>
