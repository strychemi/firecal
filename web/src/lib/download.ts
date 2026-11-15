// Client-side downloads: CSV from the response, SVG/PNG from rendered charts.
import type { MonthRow, QueryResponse } from './types';

export function downloadBlob(filename: string, blob: Blob): void {
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const CSV_FIELDS: (keyof MonthRow)[] = [
	'month',
	'source',
	'value',
	'lower',
	'upper',
	'raw',
	'detections',
	'frp',
	'days',
	'days_with_data',
	'complete'
];

function csvCell(v: unknown): string {
	if (v === null || v === undefined) return '';
	const s = String(v);
	return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function monthsToCsv(months: MonthRow[]): string {
	const lines = [CSV_FIELDS.join(',')];
	for (const m of months) lines.push(CSV_FIELDS.map((f) => csvCell(m[f])).join(','));
	return lines.join('\n') + '\n';
}

const STYLE_PROPS = [
	'fill',
	'fill-opacity',
	'stroke',
	'stroke-width',
	'stroke-opacity',
	'stroke-dasharray',
	'opacity',
	'font-family',
	'font-size',
	'font-weight',
	'text-anchor',
	'dominant-baseline',
	'visibility'
];

/** Serialise an on-screen SVG with its resolved colours inlined (CSS vars do not travel). */
export function svgToString(svg: SVGSVGElement, title: string): string {
	const clone = svg.cloneNode(true) as SVGSVGElement;
	const src = [svg, ...svg.querySelectorAll('*')];
	const dst = [clone, ...clone.querySelectorAll('*')];
	src.forEach((el, i) => {
		const cs = getComputedStyle(el);
		const target = dst[i] as SVGElement;
		target.removeAttribute('class');
		const style = STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(';');
		target.setAttribute('style', style);
	});
	clone.querySelectorAll('[data-export-skip]').forEach((n) => n.remove());
	const { width, height } = svg.viewBox.baseVal;
	clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
	clone.setAttribute('width', String(width));
	clone.setAttribute('height', String(height));
	const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
	bg.setAttribute('width', '100%');
	bg.setAttribute('height', '100%');
	bg.setAttribute('fill', getComputedStyle(document.body).getPropertyValue('--surface').trim() || '#fff');
	clone.insertBefore(bg, clone.firstChild);
	const t = document.createElementNS('http://www.w3.org/2000/svg', 'title');
	t.textContent = title;
	clone.insertBefore(t, clone.firstChild);
	return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clone);
}

export function downloadSvg(svg: SVGSVGElement, filename: string, title: string): void {
	downloadBlob(filename, new Blob([svgToString(svg, title)], { type: 'image/svg+xml' }));
}

export async function downloadPng(svg: SVGSVGElement, filename: string, title: string): Promise<void> {
	const text = svgToString(svg, title);
	const { width, height } = svg.viewBox.baseVal;
	const scale = 2;
	const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }));
	try {
		const img = new Image();
		await new Promise<void>((resolve, reject) => {
			img.onload = () => resolve();
			img.onerror = () => reject(new Error('Could not render the chart image.'));
			img.src = url;
		});
		const canvas = document.createElement('canvas');
		canvas.width = Math.round(width * scale);
		canvas.height = Math.round(height * scale);
		const ctx = canvas.getContext('2d')!;
		ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
		const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/png'));
		if (blob) downloadBlob(filename, blob);
	} finally {
		URL.revokeObjectURL(url);
	}
}

/** One row per hexagon with fire. `hex_id` is the column name Kepler.gl recognises as H3. */
export function cellsToCsv(data: QueryResponse): string {
	const head = ['hex_id', 'resolution', 'month', 'fire_days_month', 'start', 'end', 'fire_days_range'];
	const lines = [head.join(',')];
	for (const c of data.cells ?? [])
		lines.push([c.h3, data.area.resolution, data.stats.month, c.month, data.start, data.end, c.range].map(csvCell).join(','));
	return lines.join('\n') + '\n';
}
