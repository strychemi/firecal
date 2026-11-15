<script lang="ts">
	// Map: MapLibre basemap, deck.gl hexagon layer, Terra Draw for drawing an area.
	// Drawing a box, polygon or circle sets the query area; the outline shown is the
	// one the API actually used (response.area.ring), so the map never disagrees with the numbers.
	import { onDestroy, onMount } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	// MapLibre 6 loads its web worker from a separate file; Vite copies it and gives its URL.
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
	import type { Map as MlMap } from 'maplibre-gl';
	import type { MapboxOverlay } from '@deck.gl/mapbox';
	import type { TerraDraw } from 'terra-draw';
	import type { Area, BBox, CellValue, Meta, QueryResponse } from '#lib/types.ts';
	import { seqClass, seqThresholds, seqVar } from '#lib/scales.ts';
	import { fmt, monthLabel } from '#lib/format.ts';

	interface Props {
		meta: Meta;
		data: QueryResponse | null;
		busy: boolean;
		onarea: (area: Area, name: string) => void;
	}
	let { meta, data, busy, onarea }: Props = $props();

	type Tool = 'move' | 'rectangle' | 'polygon' | 'circle';
	type Measure = 'month' | 'range';

	let container: HTMLDivElement;
	let map: MlMap | null = null;
	let overlay: MapboxOverlay | null = null;
	let draw: TerraDraw | null = null;
	let ready = $state(false);
	let failed = $state('');
	let tool = $state<Tool>('move');
	let measure = $state<Measure>('month');
	let scheme = $state<'light' | 'dark'>('light');
	let media: MediaQueryList | null = null;

	const STYLE = { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' };

	const TOOLS: { id: Tool; label: string; hint: string }[] = [
		{ id: 'move', label: 'Move', hint: 'Drag to pan, scroll or pinch to zoom. Arrow keys and +/− work when the map has focus.' },
		{ id: 'rectangle', label: 'Box', hint: 'Press and drag from one corner to the opposite one, or click both corners. Esc cancels.' },
		{ id: 'polygon', label: 'Polygon', hint: 'Click each corner, then click the first point again or press Enter to finish. Esc cancels.' },
		{ id: 'circle', label: 'Circle', hint: 'Press at the centre and drag out to the edge, or click the centre and then the edge. Esc cancels.' }
	];
	const hint = $derived(TOOLS.find((t) => t.id === tool)!.hint);

	/** Resolve a CSS custom property (or var(--x)) to an [r, g, b] triple. */
	function rgb(value: string): [number, number, number] {
		const name = value.startsWith('var(') ? value.slice(4, -1) : value;
		const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888888';
		const h = hex.replace('#', '');
		const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h.slice(0, 6);
		const n = parseInt(full, 16);
		return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
	}

	// Hexagons coloured by the chosen measure, in classes like the calendar.
	const cells = $derived<CellValue[]>(data?.cells ?? []);
	const shown = $derived(cells.filter((c) => c[measure] > 0));
	// Drop breaks at or below the smallest value, so no legend class is empty (VIIRS months are whole numbers).
	const thresholds = $derived.by(() => {
		const vals = shown.map((c) => c[measure]);
		const min = Math.min(...vals);
		return seqThresholds(vals).filter((t) => t > min);
	});
	const nClasses = $derived(thresholds.length + 1);
	const legend = $derived.by(() => {
		const out: { label: string; color: string }[] = [];
		const t = thresholds;
		for (let i = 0; i <= t.length; i++) {
			const label =
				t.length === 0 ? 'any' : i === 0 ? `under ${fmt(t[0])}` : i === t.length ? `${fmt(t[i - 1])}+` : `${fmt(t[i - 1])}–${fmt(t[i])}`;
			out.push({ label, color: seqVar(i + 1, nClasses) });
		}
		return out;
	});
	const measureLabel = $derived(
		!data ? '' : measure === 'month' ? `Fire-days in ${monthLabel(data.stats.month)}` : `Fire-days, ${monthLabel(data.start)} to ${monthLabel(data.end)}`
	);

	function bounds(ring: [number, number][]): [[number, number], [number, number]] {
		let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
		for (const [x, y] of ring) {
			x0 = Math.min(x0, x);
			y0 = Math.min(y0, y);
			x1 = Math.max(x1, x);
			y1 = Math.max(y1, y);
		}
		return [
			[x0, y0],
			[x1, y1]
		];
	}

	async function renderLayers() {
		if (!overlay || !data) return;
		const { hexLayer, outlineLayer } = await import('#lib/map-layers.ts');
		const colors = Array.from({ length: 8 }, (_, i) => rgb(`--seq-${i}`));
		const stepColor = (v: number) => {
			const cls = seqClass(v, thresholds);
			const step = Number(seqVar(cls, nClasses).match(/seq-(\d)/)![1]);
			return colors[step];
		};
		const surface = rgb('--surface');
		const ink = rgb('--text');
		const m = measure;
		const hexes = shown;
		overlay.setProps({
			layers: [
				hexLayer({
					data: hexes,
					getFillColor: (d) => [...stepColor(d[m]), 225],
					lineColor: [...surface, 200],
					highlightColor: [...ink, 90],
					updateTrigger: `${m}|${thresholds.join(',')}`
				}),
				outlineLayer(data.area.ring, [...ink, 230])
			],
			getTooltip: ({ object }: { object?: (typeof hexes)[number] }) =>
				object && data
					? {
							text:
								`${fmt(object.month)} fire-days in ${monthLabel(data.stats.month)}\n` +
								`${fmt(object.range)} fire-days, ${monthLabel(data.start)} to ${monthLabel(data.end)}`,
							style: {
								background: getComputedStyle(document.documentElement).getPropertyValue('--surface'),
								color: getComputedStyle(document.documentElement).getPropertyValue('--text'),
								border: '1px solid rgba(127,127,127,0.35)',
								borderRadius: '8px',
								fontSize: '12px',
								padding: '6px 8px'
							}
						}
					: null
		});
	}

	// Redraw on any change to the data or the measure; refit when the area outline changes.
	let lastRing = '';
	$effect(() => {
		void data;
		void measure;
		void thresholds;
		void scheme;
		if (!ready || !data) return;
		renderLayers();
		const key = JSON.stringify(data.area.ring);
		if (key !== lastRing && map) {
			const first = lastRing === '';
			lastRing = key;
			map.fitBounds(bounds(data.area.ring), { padding: 24, duration: first ? 0 : 600, maxZoom: 9 });
		}
	});

	function setTool(t: Tool) {
		tool = t;
		if (!draw) return;
		draw.setMode(t === 'move' ? 'static' : t);
	}

	const r1 = (x: number, dp = 4) => Math.round(x * 10 ** dp) / 10 ** dp;

	function haversineKm([lon1, lat1]: number[], [lon2, lat2]: number[]) {
		const rad = Math.PI / 180;
		const a =
			Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
			Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
		return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
	}

	function finished(id: string | number, mode: string) {
		if (!draw) return;
		const f = draw.getSnapshotFeature(id);
		draw.removeFeatures([id]);
		setTool('move');
		if (!f || f.geometry.type !== 'Polygon') return;
		const ring = f.geometry.coordinates[0] as [number, number][];
		if (mode === 'rectangle') {
			const [[x0, y0], [x1, y1]] = bounds(ring);
			const bbox: BBox = [r1(x0), r1(y0), r1(x1), r1(y1)];
			if (!(bbox[0] < bbox[2] && bbox[1] < bbox[3])) return;
			onarea({ bbox }, `Drawn box ${bbox.map((n) => n.toFixed(2)).join(', ')}`);
		} else if (mode === 'circle') {
			const pts = ring.slice(0, -1);
			const lon = pts.reduce((s, p) => s + p[0], 0) / pts.length;
			const lat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
			const stored = Number((f.properties as Record<string, unknown>).radiusKilometers);
			const km = Number.isFinite(stored) && stored > 0 ? stored : haversineKm([lon, lat], pts[0]);
			const radius = Math.min(2000, Math.max(0.5, Math.round(km * 10) / 10));
			onarea({ point: [r1(lon), r1(lat)], radius_km: radius }, `Drawn circle, ${fmt(radius)} km around ${lat.toFixed(2)}, ${lon.toFixed(2)}`);
		} else {
			const polygon = ring.map(([x, y]) => [r1(x), r1(y)] as [number, number]);
			onarea({ polygon }, `Drawn polygon (${polygon.length - 1} corners)`);
		}
	}

	async function startDraw() {
		if (!map) return;
		const td = await import('terra-draw');
		const { TerraDrawMapLibreGLAdapter } = await import('terra-draw-maplibre-gl-adapter');
		const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() as `#${string}`;
		const style = { fillColor: accent, outlineColor: accent, outlineWidth: 2, fillOpacity: 0.15 };
		draw = new td.TerraDraw({
			adapter: new TerraDrawMapLibreGLAdapter({ map }),
			modes: [
				new td.TerraDrawRectangleMode({ styles: style, drawInteraction: 'click-move-or-drag' }),
				new td.TerraDrawPolygonMode({ styles: { ...style, closingPointColor: accent, closingPointOutlineColor: accent } }),
				new td.TerraDrawCircleMode({ styles: style, drawInteraction: 'click-move-or-drag' })
			]
		});
		draw.start();
		draw.on('finish', (id, ctx) => finished(id, ctx.mode));
		draw.setMode(tool === 'move' ? 'static' : tool);
	}

	function onScheme() {
		const next = media?.matches ? 'dark' : 'light';
		if (next === scheme || !map) return;
		scheme = next;
		draw?.stop();
		draw = null;
		map.setStyle(STYLE[scheme]);
		map.once('style.load', () => startDraw());
	}

	onMount(async () => {
		media = window.matchMedia('(prefers-color-scheme: dark)');
		const forced = document.documentElement.dataset.theme;
		scheme = forced === 'dark' || forced === 'light' ? forced : media.matches ? 'dark' : 'light';
		media.addEventListener('change', onScheme);
		try {
			const maplibregl = await import('maplibre-gl');
			maplibregl.setWorkerUrl(workerUrl);
			const { MapboxOverlay } = await import('@deck.gl/mapbox');
			const b = meta.region.bbox;
			const m = new maplibregl.Map({
				container,
				style: STYLE[scheme],
				bounds: [
					[b[0], b[1]],
					[b[2], b[3]]
				],
				fitBoundsOptions: { padding: 16 },
				attributionControl: { compact: true },
				dragRotate: false,
				pitchWithRotate: false
			});
			map = m;
			m.touchZoomRotate.disableRotation();
			m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
			overlay = new MapboxOverlay({ interleaved: false, layers: [] });
			m.addControl(overlay);
			m.on('error', (e) => console.warn('map:', e.error?.message ?? e));
			m.once('load', async () => {
				await startDraw();
				ready = true;
			});
		} catch (e) {
			failed = `The map could not start: ${e instanceof Error ? e.message : String(e)}. Use the presets or type coordinates instead.`;
		}
	});

	onDestroy(() => {
		media?.removeEventListener('change', onScheme);
		draw?.stop();
		map?.remove();
	});

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && tool !== 'move') setTool('move');
	}
</script>

<svelte:window onkeydown={onKey} />

<div class="mapcard card" aria-busy={busy}>
	<div class="bar">
		<div class="tools" role="toolbar" aria-label="Map tools">
			{#each TOOLS as t (t.id)}
				<button
					type="button"
					class="tool"
					aria-pressed={tool === t.id}
					disabled={!ready}
					title={t.hint}
					onclick={() => setTool(t.id)}>{t.id === 'move' ? t.label : `Draw ${t.label.toLowerCase()}`}</button
				>
			{/each}
		</div>
		<fieldset class="measure">
			<legend class="sr">Colour hexagons by</legend>
			<label><input type="radio" name="measure" value="month" bind:group={measure} /> Month</label>
			<label><input type="radio" name="measure" value="range" bind:group={measure} /> Date range</label>
		</fieldset>
	</div>
	<p class="hint" aria-live="polite">{hint}</p>

	<div class="frame">
		<div class="map" bind:this={container} role="region" aria-label="Map of the selected area and its hexagons"></div>
		{#if failed}
			<p class="fail" role="alert">{failed}</p>
		{:else if ready && data && shown.length === 0}
			<p class="over">No fire detected in this area for the chosen {measure === 'month' ? 'month' : 'dates'}.</p>
		{/if}
	</div>

	{#if data && shown.length > 0}
		<div class="legend" aria-label="Map legend">
			<span class="lt">{measureLabel}, per hexagon (level {data.area.resolution}):</span>
			{#each legend as l (l.label)}
				<span class="li"><i style="background:{l.color}"></i>{l.label}</span>
			{/each}
			<span class="li"><i class="outline"></i>area searched</span>
		</div>
	{/if}
</div>

<style>
	.mapcard {
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 0;
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 16px;
		align-items: center;
		justify-content: space-between;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
	}
	.tool {
		min-height: 32px;
		padding: 0 10px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
		font-size: 0.85rem;
		cursor: pointer;
	}
	.tool[aria-pressed='true'] {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--accent-ink);
		font-weight: 600;
	}
	.tool:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.measure {
		display: flex;
		gap: 10px;
		border: 0;
		margin: 0;
		padding: 0;
		font-size: 0.85rem;
	}
	.measure label {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		cursor: pointer;
	}
	.measure input {
		accent-color: var(--accent);
		margin: 0;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
	.hint {
		margin: 0;
		font-size: 0.8rem;
		color: var(--text-2);
		min-height: 1.2em;
	}
	.frame {
		position: relative;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid var(--border);
	}
	.map {
		height: 380px;
		width: 100%;
		background: var(--wash);
	}
	.over,
	.fail {
		position: absolute;
		left: 8px;
		bottom: 8px;
		margin: 0;
		max-width: calc(100% - 16px);
		padding: 6px 10px;
		border-radius: 8px;
		background: var(--surface);
		border: 1px solid var(--border);
		font-size: 0.8rem;
	}
	.fail {
		inset: 8px auto auto 8px;
		background: var(--warn-bg);
		border-color: var(--warn-border);
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 12px;
		font-size: 0.78rem;
		color: var(--text-2);
	}
	.lt {
		color: var(--text);
		width: 100%;
	}
	.li {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.li i {
		width: 12px;
		height: 12px;
		border-radius: 3px;
		display: inline-block;
	}
	.li i.outline {
		background: none;
		border: 2px solid var(--text);
		border-radius: 2px;
	}
	.map :global(.maplibregl-ctrl-attrib) {
		font-size: 10px;
	}
	@media (max-width: 900px) {
		.map {
			height: 300px;
		}
	}
</style>
