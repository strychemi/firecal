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

const r4 = (n: number) => String(Math.round(n * 1e4) / 1e4);

/** The search as query parameters (without the "?"). A polygon with too many points is left out. */
export function toParams(s: { area: Area; start: YearMonth; end: YearMonth; month: YearMonth; baseline: Baseline }): string {
	const p = new URLSearchParams();
	const a = s.area;
	if ('preset' in a) p.set('preset', a.preset);
	else if ('bbox' in a) p.set('bbox', a.bbox.map(r4).join(','));
	else if ('point' in a) p.set('circle', [a.point[0], a.point[1], a.radius_km].map(r4).join(','));
	else if ('polygon' in a && a.polygon.length <= MAX_LINK_POINTS) p.set('polygon', a.polygon.map((q) => q.map(r4).join(',')).join(';'));
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
	const m = q.get('month');
	const lo = out.start ?? meta.series_start;
	const hi = out.end ?? meta.series_end;
	if (inSeries(m) && m >= lo && m <= hi) out.month = m;
	const b = q.get('baseline');
	if (b === 'median' || b === 'mean') out.baseline = b;
	return out;
}
