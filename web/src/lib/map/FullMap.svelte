<script lang="ts" generics="T extends { h3: string }">
	// Full-screen map: MapLibre basemap, deck.gl hexagons (flat or 3D),
	// Terra Draw for drawing an area, and an optional "the view is the search" callback.
	// The page owns every control; this component only draws and reports.
	import { onDestroy, onMount } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
	import type { Map as MlMap } from 'maplibre-gl';
	import type { MapboxOverlay } from '@deck.gl/mapbox';
	import type { TerraDraw } from 'terra-draw';
	import type { Area, BBox, Meta } from '#lib/types.ts';
	import { fmt } from '#lib/format.ts';
	import { rgb, ringBounds, viewBox, type RGBA } from './helpers.ts';

	import type { Tool } from './helpers.ts';

	interface Props {
		meta: Meta;
		hexes: T[];
		fill: (d: T) => RGBA;
		/** Change this whenever `fill` would give different colours. */
		fillKey: string;
		extruded?: boolean;
		elevation?: (d: T) => number;
		elevationKey?: string;
		opacity?: number;
		outline?: boolean;
		ring?: [number, number][] | null;
		/** Fit the map to `ring` whenever this changes (and is not empty). */
		fitKey?: string;
		tooltip?: (d: T) => string | null;
		onhex?: (d: T | null) => void;
		onarea?: (area: Area, name: string) => void;
		/** Called after the map stops moving, with the view as a search box. */
		onview?: (bbox: BBox, clipped: boolean) => void;
		theme?: 'auto' | 'dark' | 'light';
		tool?: Tool;
		padding?: { top: number; right: number; bottom: number; left: number };
		ready?: boolean;
		/** Id of a text summary of what the map shows. */
		describedby?: string;
		/** Where the map opens (default: the data's region). */
		initialBbox?: BBox;
	}
	let {
		meta,
		hexes,
		fill,
		fillKey,
		extruded = false,
		elevation,
		elevationKey = '',
		opacity = 0.88,
		outline = true,
		ring = null,
		fitKey = '',
		tooltip,
		onhex,
		onarea,
		onview,
		theme = 'auto',
		tool = $bindable('move'),
		padding = { top: 24, right: 24, bottom: 24, left: 24 },
		ready = $bindable(false),
		describedby,
		initialBbox
	}: Props = $props();

	let container: HTMLDivElement;
	let map: MlMap | null = null;
	let overlay: MapboxOverlay | null = null;
	let draw: TerraDraw | null = null;
	let failed = $state('');
	let scheme = $state<'light' | 'dark'>('light');
	let media: MediaQueryList | null = null;

	// No camera flights or growing columns for people who ask for reduced motion.
	let reduce = $state(false);
	let motionQuery: MediaQueryList | null = null;
	const onMotion = () => (reduce = !!motionQuery?.matches);
	const dur = (ms: number) => (reduce ? 0 : ms);

	const STYLE = { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' };

	export function flyTo(bbox: BBox) {
		map?.fitBounds(
			[
				[bbox[0], bbox[1]],
				[bbox[2], bbox[3]]
			],
			{ padding, duration: dur(700), maxZoom: 9 }
		);
	}
	export function viewNow(): { bbox: BBox; clipped: boolean } | null {
		return map ? viewBox(map.getBounds()) : null;
	}

	async function render() {
		if (!overlay) return;
		const { H3HexagonLayer } = await import('@deck.gl/geo-layers');
		const { PathLayer } = await import('@deck.gl/layers');
		const ink = rgb('--text');
		const surface = rgb('--surface');
		const layers: unknown[] = [
			new H3HexagonLayer<T>({
				id: 'hexes',
				data: hexes,
				getHexagon: (d) => d.h3,
				filled: true,
				stroked: outline && !extruded,
				extruded,
				wireframe: false,
				getElevation: elevation ?? (() => 0),
				elevationScale: 1,
				getFillColor: fill,
				getLineColor: [...surface, 160],
				lineWidthUnits: 'pixels',
				getLineWidth: 0.5,
				opacity,
				pickable: true,
				autoHighlight: true,
				highlightColor: [...ink, 80],
				material: { ambient: 0.6, diffuse: 0.5, shininess: 16 },
				transitions: { getElevation: dur(500) },
				updateTriggers: { getFillColor: fillKey, getElevation: elevationKey }
			})
		];
		if (ring?.length)
			layers.push(
				new PathLayer<{ path: [number, number][] }>({
					id: 'area',
					data: [{ path: ring }],
					getPath: (d) => d.path,
					getColor: [...ink, 220],
					widthUnits: 'pixels',
					getWidth: 2
				})
			);
		const cs = getComputedStyle(document.documentElement);
		overlay.setProps({
			layers: layers as never,
			onClick: ({ object }: { object?: T }) => onhex?.(object ?? null),
			getTooltip: ({ object }: { object?: T }) => {
				const t = object && tooltip?.(object);
				return t
					? {
							html: t,
							style: {
								background: cs.getPropertyValue('--surface'),
								color: cs.getPropertyValue('--text'),
								border: '1px solid rgba(127,127,127,0.35)',
								borderRadius: '8px',
								fontSize: '12px',
								lineHeight: '1.45',
								padding: '8px 10px',
								boxShadow: '0 4px 14px rgba(0,0,0,0.25)'
							}
						}
					: null;
			}
		});
	}

	$effect(() => {
		void hexes;
		void fillKey;
		void extruded;
		void elevationKey;
		void opacity;
		void outline;
		void ring;
		void scheme;
		void reduce;
		if (ready) render();
	});

	$effect(() => {
		if (!ready || !map) return;
		map.easeTo({ pitch: extruded ? 50 : 0, duration: dur(600) });
		if (extruded) map.dragRotate.enable();
		else {
			map.dragRotate.disable();
			map.easeTo({ bearing: 0, pitch: 0, duration: dur(600) });
		}
	});

	let lastFit = '';
	$effect(() => {
		const key = fitKey;
		if (!ready || !map || !key || key === lastFit || !ring?.length) return;
		lastFit = key;
		map.fitBounds(ringBounds(ring), { padding, duration: dur(700), maxZoom: 9 });
	});

	$effect(() => {
		const t = tool;
		if (draw && ready) draw.setMode(t === 'move' ? 'static' : t);
	});

	const r4 = (x: number) => Math.round(x * 1e4) / 1e4;
	function haversineKm([lon1, lat1]: number[], [lon2, lat2]: number[]) {
		const rad = Math.PI / 180;
		const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
		return 2 * 6371.0088 * Math.asin(Math.sqrt(a));
	}

	function finished(id: string | number, mode: string) {
		if (!draw) return;
		const f = draw.getSnapshotFeature(id);
		draw.removeFeatures([id]);
		tool = 'move';
		if (!f || f.geometry.type !== 'Polygon') return;
		const pts = f.geometry.coordinates[0] as [number, number][];
		if (mode === 'rectangle') {
			const [[x0, y0], [x1, y1]] = ringBounds(pts);
			const bbox: BBox = [r4(x0), r4(y0), r4(x1), r4(y1)];
			if (bbox[0] < bbox[2] && bbox[1] < bbox[3]) onarea?.({ bbox }, `Drawn box`);
		} else if (mode === 'circle') {
			const p = pts.slice(0, -1);
			const lon = p.reduce((s, q) => s + q[0], 0) / p.length;
			const lat = p.reduce((s, q) => s + q[1], 0) / p.length;
			const stored = Number((f.properties as Record<string, unknown>).radiusKilometers);
			const km = Number.isFinite(stored) && stored > 0 ? stored : haversineKm([lon, lat], p[0]);
			const radius = Math.min(2000, Math.max(0.5, Math.round(km * 10) / 10));
			onarea?.({ point: [r4(lon), r4(lat)], radius_km: radius }, `${fmt(radius)} km around ${lat.toFixed(2)}, ${lon.toFixed(2)}`);
		} else {
			onarea?.({ polygon: pts.map(([x, y]) => [r4(x), r4(y)] as [number, number]) }, `Drawn polygon`);
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

	function wantScheme(): 'light' | 'dark' {
		if (theme !== 'auto') return theme;
		const forced = document.documentElement.dataset.theme;
		if (forced === 'dark' || forced === 'light') return forced;
		return media?.matches ? 'dark' : 'light';
	}
	function onScheme() {
		const next = wantScheme();
		if (next === scheme || !map) return;
		scheme = next;
		draw?.stop();
		draw = null;
		map.setStyle(STYLE[scheme]);
		map.once('style.load', () => startDraw());
	}

	let moveTimer: ReturnType<typeof setTimeout> | undefined;
	onMount(async () => {
		motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
		onMotion();
		motionQuery.addEventListener('change', onMotion);
		media = window.matchMedia('(prefers-color-scheme: dark)');
		scheme = wantScheme();
		media.addEventListener('change', onScheme);
		try {
			const maplibregl = await import('maplibre-gl');
			maplibregl.setWorkerUrl(workerUrl);
			const { MapboxOverlay } = await import('@deck.gl/mapbox');
			const b = (initialBbox ?? meta.region.bbox).map((v, i) => (i % 2 ? Math.max(-60, Math.min(75, v)) : v));
			const m = new maplibregl.Map({
				container,
				style: STYLE[scheme],
				bounds: [
					[b[0], b[1]],
					[b[2], b[3]]
				],
				fitBoundsOptions: { padding },
				attributionControl: { compact: true },
				dragRotate: false,
				maxPitch: 60
			});
			map = m;
			m.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right');
			overlay = new MapboxOverlay({ interleaved: false, layers: [] });
			m.addControl(overlay);
			m.on('error', (e) => console.warn('map:', e.error?.message ?? e));
			m.on('moveend', () => {
				clearTimeout(moveTimer);
				moveTimer = setTimeout(() => {
					const v = viewBox(m.getBounds());
					onview?.(v.bbox, v.clipped);
				}, 250);
			});
			m.once('load', async () => {
				await startDraw();
				ready = true;
				const v = viewBox(m.getBounds());
				onview?.(v.bbox, v.clipped);
			});
		} catch (e) {
			failed = `The map could not start: ${e instanceof Error ? e.message : String(e)}`;
		}
	});

	onDestroy(() => {
		clearTimeout(moveTimer);
		media?.removeEventListener('change', onScheme);
		motionQuery?.removeEventListener('change', onMotion);
		draw?.stop();
		map?.remove();
	});
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && tool !== 'move' && (tool = 'move')} />

<div class="fullmap" bind:this={container} role="region" aria-label="Map of fire-days per hexagon" aria-describedby={describedby}></div>
{#if failed}<p class="fail" role="alert">{failed}</p>{/if}

<style>
	.fullmap {
		position: absolute;
		inset: 0;
		background: var(--wash);
	}
	.fail {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		background: var(--warn-bg);
		border: 1px solid var(--warn-border);
		padding: 10px 14px;
		border-radius: 8px;
	}
	/* A page whose panel covers the bottom of the map sets --map-ctrl-bottom (and a side panel
	   --map-ctrl-right) to keep the zoom buttons and attribution clear of it. */
	.fullmap :global(.maplibregl-ctrl-bottom-right),
	.fullmap :global(.maplibregl-ctrl-bottom-left) {
		bottom: var(--map-ctrl-bottom, 0px);
	}
	.fullmap :global(.maplibregl-ctrl-bottom-right) {
		right: var(--map-ctrl-right, 0px);
	}
	.fullmap :global(.maplibregl-ctrl-attrib) {
		font-size: 10px;
	}
</style>
