<script lang="ts">
	// A comparison category's drawn icon, in the current text colour.
	import { CATEGORY_ICON, ICON_STROKE } from '#lib/scales.ts';
	import type { Category } from '#lib/types.ts';

	let { category, size = 12 }: { category: Category; size?: number } = $props();
	const icon = $derived(CATEGORY_ICON[category]);
</script>

<svg viewBox="0 0 12 12" width={size} height={size} aria-hidden="true" focusable="false">
	{#if icon.outline}
		<path d={icon.d} fill="none" stroke="currentColor" stroke-width={ICON_STROKE} stroke-linejoin="round" />
	{:else}
		<path d={icon.d} fill="currentColor" />
	{/if}
</svg>

<style>
	svg {
		display: inline-block;
		flex: none;
		vertical-align: -0.1em;
	}
</style>
