<script lang="ts" module>
	// One floating tooltip positioned inside a relatively positioned parent.
	// Rows: [value, label, optional key colour]. Values lead, labels follow.
	export interface TipRow {
		value: string;
		label: string;
		key?: string;
	}
</script>

<script lang="ts">
	interface Props {
		x: number;
		y: number;
		/** width of the positioning parent, to flip the tooltip near the right edge */
		parentWidth: number;
		heading: string;
		rows: TipRow[];
		foot?: string;
	}
	let { x, y, parentWidth, heading, rows, foot }: Props = $props();
	let w = $state(200);
	const left = $derived.by(() => {
		let l = x + 14;
		if (l + w > parentWidth) l = x - w - 14;
		return Math.max(0, Math.min(l, parentWidth - w));
	});
</script>

<div class="tip" bind:clientWidth={w} style:left="{left}px" style:top="{Math.max(0, y - 10)}px" aria-hidden="true">
	<div class="h">{heading}</div>
	{#each rows as r (r.label)}
		<div class="row">
			{#if r.key}<span class="key" style:background={r.key}></span>{/if}
			<strong>{r.value}</strong>
			<span class="lab">{r.label}</span>
		</div>
	{/each}
	{#if foot}<div class="foot">{foot}</div>{/if}
</div>

<style>
	.tip {
		position: absolute;
		z-index: 5;
		pointer-events: none;
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
		border-radius: 8px;
		padding: 8px 10px;
		font-size: 0.8rem;
		max-width: 260px;
		line-height: 1.35;
	}
	.h {
		font-weight: 600;
		margin-bottom: 4px;
	}
	.row {
		display: flex;
		align-items: baseline;
		gap: 6px;
	}
	.row strong {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.lab {
		color: var(--text-2);
	}
	.key {
		display: inline-block;
		width: 12px;
		height: 2px;
		border-radius: 1px;
		transform: translateY(-3px);
		flex: none;
	}
	.foot {
		margin-top: 4px;
		color: var(--text-2);
	}
</style>
