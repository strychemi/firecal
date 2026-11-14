<script lang="ts">
	import type { Snippet } from 'svelte';
	import { downloadPng, downloadSvg } from '#lib/download.ts';

	interface Props {
		id: string;
		title: string;
		subtitle?: string;
		filename: string;
		svg?: SVGSVGElement | null;
		controls?: Snippet;
		legend?: Snippet;
		table?: Snippet;
		notes?: Snippet;
		children: Snippet;
		busy?: boolean;
	}
	let { id, title, subtitle, filename, svg, controls, legend, table, notes, children, busy = false }: Props =
		$props();

	let err = $state('');
	async function png() {
		err = '';
		if (!svg) return;
		try {
			await downloadPng(svg, `${filename}.png`, title);
		} catch (e) {
			err = e instanceof Error ? e.message : String(e);
		}
	}
</script>

<section class="card chart" aria-labelledby="{id}-title">
	<header>
		<div>
			<h2 id="{id}-title">{title}</h2>
			{#if subtitle}<p class="sub">{subtitle}</p>{/if}
		</div>
		<div class="dl" role="group" aria-label="Download {title}">
			<button class="btn small" type="button" disabled={!svg} onclick={() => svg && downloadSvg(svg, `${filename}.svg`, title)}>
				SVG
			</button>
			<button class="btn small" type="button" disabled={!svg} onclick={png}>PNG</button>
		</div>
	</header>
	{#if controls}<div class="controls">{@render controls()}</div>{/if}
	{#if legend}<div class="legend">{@render legend()}</div>{/if}
	<div class="plot" class:busy>{@render children()}</div>
	{#if notes}<div class="notes">{@render notes()}</div>{/if}
	{#if err}<p class="err" role="alert">{err}</p>{/if}
	{#if table}
		<details>
			<summary>Show as a table</summary>
			<div class="table-scroll">{@render table()}</div>
		</details>
	{/if}
</section>

<style>
	.chart {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 12px;
		flex-wrap: wrap;
	}
	h2 {
		font-size: 1.1rem;
	}
	.sub {
		margin: 4px 0 0;
		color: var(--text-2);
		font-size: 0.9rem;
		max-width: 62ch;
	}
	.dl {
		display: flex;
		gap: 4px;
	}
	.small {
		min-height: 32px;
		padding: 4px 10px;
		font-size: 0.8rem;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 16px;
		align-items: center;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 16px;
		align-items: center;
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.plot {
		position: relative;
		min-width: 0;
		transition: opacity 0.2s;
	}
	.plot.busy {
		opacity: 0.5;
	}
	.notes {
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.notes :global(p) {
		margin: 0 0 4px;
	}
	details summary {
		cursor: pointer;
		color: var(--accent);
		font-size: 0.9rem;
		width: fit-content;
	}
	.err {
		color: var(--text);
		font-size: 0.85rem;
	}
</style>
