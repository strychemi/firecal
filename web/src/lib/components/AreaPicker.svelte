<script lang="ts">
	import type { Area, BBox, Meta } from '#lib/types.ts';

	interface Props {
		meta: Meta;
		area: Area;
		onarea: (area: Area, name: string) => void;
	}
	let { meta, area, onarea }: Props = $props();

	type Tab = 'preset' | 'box' | 'circle';
	let tab = $state<Tab>('preset');
	const currentPreset = $derived('preset' in area ? area.preset : null);

	// Custom box form (strings, so partial input can be validated).
	const rb = $derived(meta.region.bbox);
	let box = $state({ minLon: '-60.8', minLat: '-34.3', maxLon: '-58.3', maxLat: '-32.0' });
	let circle = $state({ lon: '-71.3', lat: '-41.1', r: '50' });
	let boxErrors = $state<Record<string, string>>({});
	let circleErrors = $state<Record<string, string>>({});

	function num(s: string): number | null {
		const t = s.trim().replace(',', '.');
		if (t === '') return null;
		const v = Number(t);
		return Number.isFinite(v) ? v : null;
	}
	function checkLon(v: number | null) {
		return v === null ? 'Enter a number.' : v < -180 || v > 180 ? 'Longitude must be between −180 and 180.' : '';
	}
	function checkLat(v: number | null) {
		return v === null ? 'Enter a number.' : v < -90 || v > 90 ? 'Latitude must be between −90 and 90.' : '';
	}
	const outsideRegion = (lon: number, lat: number) => lon < rb[0] || lon > rb[2] || lat < rb[1] || lat > rb[3];

	let boxWarn = $state('');
	function submitBox(e: SubmitEvent) {
		e.preventDefault();
		const v = { minLon: num(box.minLon), minLat: num(box.minLat), maxLon: num(box.maxLon), maxLat: num(box.maxLat) };
		const errs: Record<string, string> = {};
		for (const k of ['minLon', 'maxLon'] as const) if (checkLon(v[k])) errs[k] = checkLon(v[k]);
		for (const k of ['minLat', 'maxLat'] as const) if (checkLat(v[k])) errs[k] = checkLat(v[k]);
		if (!errs.minLon && !errs.maxLon && v.minLon! >= v.maxLon!) errs.maxLon = 'East (max) longitude must be greater than west (min).';
		if (!errs.minLat && !errs.maxLat && v.minLat! >= v.maxLat!) errs.maxLat = 'North (max) latitude must be greater than south (min).';
		boxErrors = errs;
		if (Object.keys(errs).length) {
			focusFirstError('box');
			return;
		}
		const bbox: BBox = [v.minLon!, v.minLat!, v.maxLon!, v.maxLat!];
		boxWarn =
			outsideRegion(bbox[0], bbox[1]) || outsideRegion(bbox[2], bbox[3])
				? 'Part of this box is outside the study region, where there is no data yet.'
				: '';
		onarea({ bbox }, `Box ${bbox.map((n) => n.toFixed(2)).join(', ')}`);
	}

	let circleWarn = $state('');
	function submitCircle(e: SubmitEvent) {
		e.preventDefault();
		const lon = num(circle.lon);
		const lat = num(circle.lat);
		const r = num(circle.r);
		const errs: Record<string, string> = {};
		if (checkLon(lon)) errs.lon = checkLon(lon);
		if (checkLat(lat)) errs.lat = checkLat(lat);
		if (r === null) errs.r = 'Enter a number.';
		else if (r <= 0 || r > 2000) errs.r = 'Radius must be more than 0 and at most 2,000 km.';
		circleErrors = errs;
		if (Object.keys(errs).length) {
			focusFirstError('circle');
			return;
		}
		circleWarn = outsideRegion(lon!, lat!) ? 'This point is outside the study region, where there is no data yet.' : '';
		onarea({ point: [lon!, lat!], radius_km: r! }, `${r} km around ${lat!.toFixed(2)}, ${lon!.toFixed(2)}`);
	}

	function focusFirstError(form: string) {
		queueMicrotask(() => {
			const el = document.querySelector<HTMLInputElement>(`#${form}-form [aria-invalid="true"]`);
			el?.focus();
		});
	}

	const TABS: { id: Tab; label: string }[] = [
		{ id: 'preset', label: 'Presets' },
		{ id: 'box', label: 'Custom box' },
		{ id: 'circle', label: 'Circle' }
	];
	function tabKey(e: KeyboardEvent, i: number) {
		const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
		if (!d) return;
		e.preventDefault();
		const next = TABS[(i + d + TABS.length) % TABS.length];
		tab = next.id;
		document.getElementById(`tab-${next.id}`)?.focus();
	}
</script>

<div class="picker">
	<div class="tabs" role="tablist" aria-label="How to choose the area">
		{#each TABS as t, i (t.id)}
			<button
				id="tab-{t.id}"
				type="button"
				role="tab"
				class="tab"
				aria-selected={tab === t.id}
				aria-controls="panel-{t.id}"
				tabindex={tab === t.id ? 0 : -1}
				onclick={() => (tab = t.id)}
				onkeydown={(e) => tabKey(e, i)}>{t.label}</button
			>
		{/each}
	</div>

	{#if tab === 'preset'}
		<div id="panel-preset" role="tabpanel" aria-labelledby="tab-preset" class="panel">
			<div class="presets">
				{#each meta.presets as p (p.id)}
					<button
						type="button"
						class="preset"
						aria-pressed={currentPreset === p.id}
						onclick={() => onarea({ preset: p.id }, p.name)}
					>
						<span class="pname">{p.name}</span>
						<span class="pnote">{p.note}</span>
					</button>
				{/each}
			</div>
		</div>
	{:else if tab === 'box'}
		<div id="panel-box" role="tabpanel" aria-labelledby="tab-box" class="panel">
			<form id="box-form" onsubmit={submitBox} novalidate>
				<p class="hint">Decimal degrees; west and south are negative. Study region: longitude {rb[0]} to {rb[2]}, latitude {rb[1]} to {rb[3]}.</p>
				<div class="grid4">
					{#each [['minLon', 'West (min longitude)'], ['maxLon', 'East (max longitude)'], ['minLat', 'South (min latitude)'], ['maxLat', 'North (max latitude)']] as [k, lab] (k)}
						{@const key = k as keyof typeof box}
						<div class="field">
							<label for="box-{k}">{lab}</label>
							<input
								id="box-{k}"
								inputmode="decimal"
								autocomplete="off"
								bind:value={box[key]}
								aria-invalid={boxErrors[k] ? 'true' : undefined}
								aria-describedby={boxErrors[k] ? `box-${k}-err` : undefined}
							/>
							{#if boxErrors[k]}<span id="box-{k}-err" class="err">{boxErrors[k]}</span>{/if}
						</div>
					{/each}
				</div>
				<button class="btn primary" type="submit">Show this box</button>
				{#if boxWarn}<p class="warn" role="status">{boxWarn}</p>{/if}
			</form>
		</div>
	{:else}
		<div id="panel-circle" role="tabpanel" aria-labelledby="tab-circle" class="panel">
			<form id="circle-form" onsubmit={submitCircle} novalidate>
				<p class="hint">Decimal degrees; west and south are negative. The circle is drawn as a 64-sided polygon.</p>
				<div class="grid4">
					{#each [['lat', 'Latitude'], ['lon', 'Longitude'], ['r', 'Radius (km)']] as [k, lab] (k)}
						{@const key = k as keyof typeof circle}
						<div class="field">
							<label for="circle-{k}">{lab}</label>
							<input
								id="circle-{k}"
								inputmode="decimal"
								autocomplete="off"
								bind:value={circle[key]}
								aria-invalid={circleErrors[k] ? 'true' : undefined}
								aria-describedby={circleErrors[k] ? `circle-${k}-err` : undefined}
							/>
							{#if circleErrors[k]}<span id="circle-{k}-err" class="err">{circleErrors[k]}</span>{/if}
						</div>
					{/each}
				</div>
				<button class="btn primary" type="submit">Show this circle</button>
				{#if circleWarn}<p class="warn" role="status">{circleWarn}</p>{/if}
			</form>
		</div>
	{/if}
</div>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	.tabs {
		display: flex;
		flex-wrap: wrap;
		gap: 2px;
		border-bottom: 1px solid var(--grid);
	}
	.tab {
		border: 0;
		background: none;
		padding: 8px 10px;
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		color: var(--text-2);
		font-size: 0.9rem;
	}
	.tab[aria-selected='true'] {
		color: var(--text);
		border-bottom-color: var(--accent);
		font-weight: 600;
	}
	.panel {
		min-width: 0;
	}
	.presets {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 8px;
	}
	.preset {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
		text-align: left;
		padding: 10px 12px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		cursor: pointer;
	}
	.preset:hover {
		background: var(--wash);
	}
	.preset[aria-pressed='true'] {
		border-color: var(--accent);
		box-shadow: inset 0 0 0 1px var(--accent);
	}
	.preset[aria-pressed='true'] .pname::before {
		content: '✓ ';
	}
	.pname {
		font-weight: 600;
	}
	.pnote {
		font-size: 0.8rem;
		color: var(--text-2);
	}
	form {
		display: flex;
		flex-direction: column;
		gap: 10px;
		align-items: flex-start;
	}
	.hint {
		margin: 0;
		font-size: 0.85rem;
		color: var(--text-2);
	}
	.grid4 {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 8px 12px;
		width: 100%;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.field label {
		font-size: 0.8rem;
		color: var(--text-2);
	}
	input {
		min-height: 36px;
		padding: 4px 8px;
		border-radius: 8px;
		border: 1px solid var(--axis);
		background: var(--surface);
		width: 100%;
	}
	input[aria-invalid='true'] {
		border-color: var(--div-mhi);
		border-width: 2px;
	}
	.err {
		font-size: 0.8rem;
		color: var(--text);
	}
	.err::before {
		content: '⚠ ';
	}
	.warn {
		margin: 0 0 8px;
		padding: 8px 10px;
		border-radius: 8px;
		background: var(--warn-bg);
		border: 1px solid var(--warn-border);
		font-size: 0.85rem;
	}
</style>
