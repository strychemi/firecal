// Shareable links: the search (area, dates, month, baseline) as URL query parameters, so a link
// reproduces it. Everything read from a link is checked against the data before it is used.
import type { Area, Baseline, Meta, YearMonth } from './types';

export interface Shared {
	area?: Area;
	areaName?: string;
	start?: YearMonth;
	end?: YearMonth;
	month?: YearMonth;
	baseline?: Baseline;
}

/** Most points a polygon may have in a link (a drawn polygon has a handful; a long link fails in some apps). */
export const MAX_LINK_POINTS = 200;

/** Whether a link can carry this area: every area but a polygon with too many points. */
export const shareable = (a: Area) => !('polygon' in a) || a.polygon.length <= MAX_LINK_POINTS;

// Numbers go into the link exactly as the search sent them (the shortest form that reads back the
// same), so the link reproduces the same hexagons. Drawn shapes are already rounded where drawn.
const num = (n: number) => String(n);

/** The search as query parameters (without the "?"), or null when the area cannot go in a link. */
export function toParams(s: { area: Area; start: YearMonth; end: YearMonth; month: YearMonth; baseline: Baseline }): string | null {
	const a = s.area;
	if (!shareable(a)) return null;
	const p = new URLSearchParams();
	if ('preset' in a) p.set('preset', a.preset);
	else if ('bbox' in a) p.set('bbox', a.bbox.map(num).join(','));
	else if ('point' in a) p.set('circle', [a.point[0], a.point[1], a.radius_km].map(num).join(','));
	else if ('polygon' in a) p.set('polygon', a.polygon.map((q) => q.map(num).join(',')).join(';'));
	p.set('start', s.start);
	p.set('end', s.end);
	p.set('month', s.month);
	if (s.baseline !== 'median') p.set('baseline', s.baseline);
	// Commas and semicolons are safe in a query string; keep them readable.
	return p.toString().replace(/%2C/g, ',').replace(/%3B/g, ';');
}

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

function numbers(s: string | null, n: number): number[] | null {
	if (s === null) return null;
	const xs = s.split(',').map(Number);
	return xs.length === n && xs.every(Number.isFinite) ? xs : null;
}

const okLon = (x: number) => x >= -180 && x <= 180;
const okLat = (y: number) => y >= -90 && y <= 90;

/** The search a link describes, keeping only the parts that are valid for this data. */
export function fromParams(q: URLSearchParams, meta: Meta): Shared {
	const out: Shared = {};
	const preset = q.get('preset');
	const bbox = numbers(q.get('bbox'), 4);
	const circle = numbers(q.get('circle'), 3);
	const poly = q.get('polygon');
	const p = preset ? meta.presets.find((x) => x.id === preset) : undefined;
	if (p) {
		out.area = { preset: p.id };
		out.areaName = p.name;
	} else if (bbox && bbox[0] < bbox[2] && bbox[1] < bbox[3] && [bbox[0], bbox[2]].every(okLon) && [bbox[1], bbox[3]].every(okLat)) {
		out.area = { bbox: bbox as [number, number, number, number] };
		out.areaName = `Box ${bbox.map((n) => n.toFixed(2)).join(', ')}`;
	} else if (circle && okLon(circle[0]) && okLat(circle[1]) && circle[2] > 0 && circle[2] <= 2000) {
		out.area = { point: [circle[0], circle[1]], radius_km: circle[2] };
		out.areaName = `${circle[2]} km around ${circle[1].toFixed(2)}, ${circle[0].toFixed(2)}`;
	} else if (poly) {
		const pts = poly.split(';').map((s) => numbers(s, 2));
		if (pts.length >= 3 && pts.length <= MAX_LINK_POINTS && pts.every((x) => x && okLon(x[0]) && okLat(x[1]))) {
			out.area = { polygon: pts as [number, number][] };
			out.areaName = `Shared polygon (${pts.length} points)`;
		}
	}
	const inSeries = (m: string | null): m is YearMonth => m !== null && MONTH.test(m) && m >= meta.series_start && m <= meta.series_end;
	const s = q.get('start');
	const e = q.get('end');
	if (inSeries(s) && inSeries(e) && s <= e) {
		out.start = s;
		out.end = e;
	}
	// The described month may lie outside the dates shown (the month picker allows any month in the series).
	const m = q.get('month');
	if (inSeries(m)) out.month = m;
	const b = q.get('baseline');
	if (b === 'median' || b === 'mean') out.baseline = b;
	return out;
}
