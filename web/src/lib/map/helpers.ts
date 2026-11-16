// Map helpers: colours read from the page tokens, class breaks, the map view as a search box, a query cache, per-hexagon comparisons.
import { query } from '#lib/api.ts';
import { median } from '#lib/format.ts';
import { categoryOf, CATEGORY_ORDER } from '#lib/scales.ts';
import type { Area, BBox, Baseline, Category, QueryRequest, QueryResponse, YearMonth } from '#lib/types.ts';

export type Tool = 'move' | 'rectangle' | 'polygon' | 'circle';
export type RGB = [number, number, number];
export type RGBA = [number, number, number, number];

/** Resolve a CSS custom property (`--x` or `var(--x)`) to [r, g, b]. */
export function rgb(value: string): RGB {
	const name = value.startsWith('var(') ? value.slice(4, -1) : value;
	const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888888';
	const h = hex.replace('#', '');
	const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h.slice(0, 6);
	const n = parseInt(full, 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** The 7 non-zero sequential steps, light to dark (dark mode: dark to light), read from the page's tokens. */
export const seqColors = (): RGB[] => Array.from({ length: 7 }, (_, i) => rgb(`--seq-${i + 1}`));

/** Diverging colours for the five categories, in CATEGORY_ORDER. */
export const divColors = (): Record<Category, RGB> => {
	const vars = ['--div-mlo', '--div-lo', '--div-mid', '--div-hi', '--div-mhi'];
	return Object.fromEntries(CATEGORY_ORDER.map((c, i) => [c, rgb(vars[i])])) as Record<Category, RGB>;
};

/** Quantile class breaks (up to 7 classes) of the positive values. */
export function quantileBreaks(values: number[], n = 7): number[] {
	const nz = values.filter((v) => v > 0).sort((a, b) => a - b);
	if (!nz.length) return [];
	const out: number[] = [];
	for (let i = 1; i < n; i++) {
		const v = nz[Math.min(nz.length - 1, Math.floor((i / n) * nz.length))];
		if (!out.length || v > out[out.length - 1]) out.push(v);
	}
	return out.filter((t) => t > nz[0]);
}

/** Class 0..breaks.length for a positive value. */
export function classOf(v: number, breaks: number[]): number {
	let i = 0;
	while (i < breaks.length && v >= breaks[i]) i++;
	return i;
}

/** Colour for class i of k, spread across the 7 sequential steps. */
export function stepColor(i: number, k: number, colors: RGB[]): RGB {
	const step = k <= 1 ? 6 : Math.round((i * 6) / (k - 1));
	return colors[step];
}

/**
 * The map view as a search box. A view showing the whole world (or more) searches the whole world.
 * Boxes cannot cross the 180° line, so a view across it is cut there, keeping the side with the centre.
 */
export function viewBox(b: { getWest(): number; getEast(): number; getSouth(): number; getNorth(): number }): {
	bbox: BBox;
	clipped: boolean;
} {
	let w = b.getWest();
	let e = b.getEast();
	// Clamp both edges to the Web Mercator limit, so a view at a pole can never put south above north.
	const LAT = 85.0511;
	const s = Math.min(LAT, Math.max(-LAT, b.getSouth()));
	const n = Math.min(LAT, Math.max(-LAT, b.getNorth()));
	let clipped = false;
	if (e - w >= 360) {
		w = -180;
		e = 180;
	}
	// Shift into [-180, 180].
	const shift = Math.round((w + e) / 2 / 360) * 360;
	w -= shift;
	e -= shift;
	if (w < -180) {
		w = -180;
		clipped = true;
	}
	if (e > 180) {
		e = 180;
		clipped = true;
	}
	// Round outwards (minima down, maxima up), so a tiny view never collapses to zero width or height.
	const lo = (x: number) => Math.floor(x * 1000) / 1000;
	const hi = (x: number) => Math.ceil(x * 1000) / 1000;
	return { bbox: [lo(w), lo(s), hi(e), hi(n)], clipped };
}

/** Bounds of a ring as [[w, s], [e, n]]. */
export function ringBounds(ring: [number, number][]): [[number, number], [number, number]] {
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

// A small cache, so scrubbing back and forth through months doesn't refetch.
const cache = new Map<string, Promise<QueryResponse>>();
export function cachedQuery(req: QueryRequest): Promise<QueryResponse> {
	const key = JSON.stringify(req);
	let p = cache.get(key);
	if (!p) {
		p = query(req);
		p.catch(() => cache.delete(key));
		cache.set(key, p);
		if (cache.size > 400) cache.delete(cache.keys().next().value!);
	}
	return p;
}

/** Run tasks with at most `n` in flight. */
export async function pool<T>(tasks: (() => Promise<T>)[], n: number, onDone?: (done: number) => void): Promise<T[]> {
	const out: T[] = new Array(tasks.length);
	let next = 0;
	let done = 0;
	async function worker() {
		while (next < tasks.length) {
			const i = next++;
			out[i] = await tasks[i]();
			onDone?.(++done);
		}
	}
	await Promise.all(Array.from({ length: Math.min(n, tasks.length) }, worker));
	return out;
}

export interface HexAnomaly {
	h3: string;
	value: number;
	usual: number;
	ratio: number | null;
	category: Category;
	/** fire in this month here, usual 0 */
	isNew: boolean;
}

/**
 * Per-hexagon comparison of `month` with the same calendar month in `years` (the years the
 * area's own comparison used, data.stats.baseline_years). One search per year: the API has
 * no per-hexagon baseline, so the prototype asks for each year's month and takes the median
 * (or mean) per hexagon itself. A hexagon missing from a year had no fire then (0).
 */
export async function hexAnomalies(
	area: Area,
	month: YearMonth,
	current: { h3: string; month: number }[],
	years: number[],
	baseline: Baseline,
	onProgress?: (done: number, total: number) => void
): Promise<HexAnomaly[]> {
	const mm = month.slice(5);
	const tasks = years.map((y) => () => {
		const m = `${y}-${mm}`;
		return cachedQuery({ area, start: m, end: m, month: m, baseline: 'median' }).then((r) => r.cells);
	});
	const perYear = await pool(tasks, 6, (d) => onProgress?.(d, tasks.length));
	const hist = new Map<string, number[]>();
	perYear.forEach((cells, yi) => {
		for (const c of cells) {
			if (!(c.month > 0)) continue;
			if (!hist.has(c.h3)) hist.set(c.h3, new Array(years.length).fill(0));
			hist.get(c.h3)![yi] = c.month;
		}
	});
	const now = new Map(current.filter((c) => c.month > 0).map((c) => [c.h3, c.month]));
	const ids = new Set([...hist.keys(), ...now.keys()]);
	const out: HexAnomaly[] = [];
	for (const h3 of ids) {
		const xs = hist.get(h3) ?? new Array(years.length).fill(0);
		const usual = baseline === 'mean' ? xs.reduce((s, x) => s + x, 0) / Math.max(1, xs.length) : median(xs);
		const value = now.get(h3) ?? 0;
		if (usual === 0 && value === 0) continue;
		const ratio = usual > 0 ? value / usual : null;
		out.push({
			h3,
			value,
			usual,
			ratio,
			category: ratio == null ? 'much higher than usual' : categoryOf(ratio),
			isNew: usual === 0
		});
	}
	return out;
}

export const yearOf = (m: YearMonth) => Number(m.slice(0, 4));
