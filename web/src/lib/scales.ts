import { median } from './format';
import type { Category, MonthRow, Source } from './types';

// Category thresholds on value / usual (docs/api.md, "stats"), for colouring past months in the charts.
const CATEGORIES: [number, Category][] = [
	[0.5, 'much lower than usual'],
	[0.8, 'lower than usual'],
	[1.25, 'about usual'],
	[2.0, 'higher than usual'],
	[Infinity, 'much higher than usual']
];

export function categoryOf(ratio: number): Category {
	return CATEGORIES.find(([t]) => ratio < t)![1];
}

export const ERA_VAR: Record<Source, string> = {
	terra_harmonized: 'var(--era-terra)',
	aqua_harmonized: 'var(--era-aqua)',
	viirs: 'var(--era-viirs)'
};

/** Simple linear scale. */
export function linear(d0: number, d1: number, r0: number, r1: number) {
	const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
	return (x: number) => r0 + (x - d0) * k;
}

/** Up to ~count "nice" ticks from 0 to max. */
export function niceTicks(max: number, count = 5): number[] {
	if (!(max > 0)) return [0];
	const raw = max / count;
	const p = 10 ** Math.floor(Math.log10(raw));
	const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw)!;
	const ticks: number[] = [];
	for (let v = 0; v <= max + step * 1e-9; v += step) ticks.push(v);
	if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
	return ticks;
}

function nice2(x: number): number {
	if (x <= 0) return 0;
	const p = 10 ** (Math.floor(Math.log10(x)) - 1);
	return Math.max(1, Math.round(x / p) * p);
}

/**
 * Sequential classes for the heatmap: 0 is its own class; non-zero values are
 * split into up to 7 classes at quantiles of the visible non-zero values,
 * rounded to two significant figures.
 */
export function seqThresholds(values: number[]): number[] {
	const nz = values.filter((v) => v > 0).sort((a, b) => a - b);
	if (!nz.length) return [];
	const t: number[] = [];
	for (let i = 1; i < 7; i++) {
		const q = nz[Math.min(nz.length - 1, Math.floor((i / 7) * nz.length))];
		const v = nice2(q);
		if (v > 0 && (t.length === 0 || v > t[t.length - 1])) t.push(v);
	}
	return t;
}

/** Class 0 for zero, otherwise 1..(thresholds.length+1). */
export function seqClass(v: number, thresholds: number[]): number {
	if (!(v > 0)) return 0;
	let i = 0;
	while (i < thresholds.length && v >= thresholds[i]) i++;
	return i + 1;
}

/** Map a class index onto the 7-step ramp, spreading when there are fewer classes. */
export function seqVar(cls: number, nClasses: number): string {
	if (cls === 0) return 'var(--seq-0)';
	const step = nClasses <= 1 ? 7 : Math.round(1 + ((cls - 1) * 6) / (nClasses - 1));
	return `var(--seq-${step})`;
}

export const CATEGORY_ORDER: Category[] = [
	'much lower than usual',
	'lower than usual',
	'about usual',
	'higher than usual',
	'much higher than usual'
];

export const CATEGORY_VAR: Record<Category, string> = {
	'much lower than usual': 'var(--div-mlo)',
	'lower than usual': 'var(--div-lo)',
	'about usual': 'var(--div-mid)',
	'higher than usual': 'var(--div-hi)',
	'much higher than usual': 'var(--div-mhi)'
};

/** Glyph carried with each category so colour is never the only cue. */
export const CATEGORY_GLYPH: Record<Category, string> = {
	'much lower than usual': '⇓',
	'lower than usual': '↓',
	'about usual': '=',
	'higher than usual': '↑',
	'much higher than usual': '⇑'
};

export const CATEGORY_INK: Record<Category, string> = {
	'much lower than usual': 'var(--div-ink-strong)',
	'lower than usual': 'var(--div-ink-soft)',
	'about usual': 'var(--div-ink-soft)',
	'higher than usual': 'var(--div-ink-soft)',
	'much higher than usual': 'var(--div-ink-strong)'
};

export interface Anomaly {
	baseline: number;
	ratio: number | null;
	category: Category;
	years: number;
}

/**
 * Each month against the median of the same calendar month in the other
 * complete years of `months` (same rule as the contract's stats, but limited
 * to the months on screen).
 */
export function anomalies(months: MonthRow[]): Map<string, Anomaly> {
	const out = new Map<string, Anomaly>();
	const byCal = new Map<string, MonthRow[]>();
	for (const m of months) {
		const k = m.month.slice(5);
		if (!byCal.has(k)) byCal.set(k, []);
		byCal.get(k)!.push(m);
	}
	for (const m of months) {
		// An in-progress month is compared on days 1..D by the API (answer card), not here against whole months.
		if (m.in_progress) continue;
		const others = byCal.get(m.month.slice(5))!.filter((o) => o.month !== m.month && o.complete);
		const base = median(others.map((o) => o.value));
		let ratio: number | null = null;
		let category: Category;
		if (base > 0) {
			ratio = m.value / base;
			category = categoryOf(ratio);
		} else {
			category = m.value > 0 ? 'much higher than usual' : 'about usual';
		}
		out.set(m.month, { baseline: base, ratio, category, years: others.length });
	}
	return out;
}
