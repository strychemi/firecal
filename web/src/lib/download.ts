// Client-side downloads: CSV from the response, SVG/PNG from rendered charts (with title, area, description and legend).
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

const NS = 'http://www.w3.org/2000/svg';

/** Copy each element's resolved style onto its clone (CSS variables and classes do not travel). */
function inlineStyles(src: Element, dst: Element): void {
	const a = [src, ...src.querySelectorAll('*')];
	const b = [dst, ...dst.querySelectorAll('*')];
	a.forEach((el, i) => {
		const cs = getComputedStyle(el);
		const target = b[i];
		target.removeAttribute('class');
		target.setAttribute('style', STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(';'));
	});
}

function node(name: string, attrs: Record<string, string | number>, text?: string): SVGElement {
	const n = document.createElementNS(NS, name);
	for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
	if (text !== undefined) n.textContent = text;
	return n;
}

/** What goes around the chart in a saved image. */
export interface ChartParts {
	title: string;
	/** Area and dates, shown under the title. */
	context?: string;
	subtitle?: string;
	/** The on-screen legend; its items are redrawn in the image. */
	legend?: HTMLElement | null;
}

const PAD = 20;
const TITLE = 17;
const SMALL = 12.5;

/**
 * The chart as a standalone SVG: title, area and dates, description and legend above the plot,
 * in the colours on screen.
 */
export function chartImage(svg: SVGSVGElement, parts: ChartParts): { text: string; width: number; height: number } {
	const page = getComputedStyle(document.body);
	const color = (v: string, d: string) => page.getPropertyValue(v).trim() || d;
	const ink = color('--text', '#0b0b0b');
	const ink2 = color('--text-2', '#52514e');
	const family = page.fontFamily;
	const ctx = document.createElement('canvas').getContext('2d')!;
	const measure = (s: string, font: string) => ((ctx.font = font), ctx.measureText(s).width);
	const fTitle = `600 ${TITLE}px ${family}`;
	const fSmall = `${SMALL}px ${family}`;
	const fContext = `500 ${SMALL}px ${family}`;

	const { width: cw, height: ch } = svg.viewBox.baseVal;
	const W = Math.max(cw, 420) + PAD * 2;
	const inner = W - PAD * 2;
	const wrap = (text: string, font: string): string[] => {
		const lines: string[] = [];
		let line = '';
		for (const word of text.split(/\s+/).filter(Boolean)) {
			const next = line ? `${line} ${word}` : word;
			if (line && measure(next, font) > inner) {
				lines.push(line);
				line = word;
			} else line = next;
		}
		if (line) lines.push(line);
		return lines;
	};

	const out = document.createElementNS(NS, 'svg') as SVGSVGElement;
	const head: SVGElement[] = [];
	let y = PAD;
	const textLines = (lines: string[], size: number, fill: string, weight: string, lh: number) => {
		for (const l of lines) {
			head.push(node('text', { x: PAD, y: y + size, fill, 'font-family': family, 'font-size': size, 'font-weight': weight }, l));
			y += lh;
		}
	};
	textLines(wrap(parts.title, fTitle), TITLE, ink, '600', 22);
	if (parts.context) textLines(wrap(parts.context, fContext), SMALL, ink, '500', 18);
	if (parts.subtitle) {
		y += 4;
		textLines(wrap(parts.subtitle, fSmall), SMALL, ink2, '400', 18);
	}

	// Legend: each item is a swatch (a coloured box and/or a small inline SVG) and its label.
	if (parts.legend) {
		y += 8;
		const ROW = 20;
		let x = 0;
		const newline = () => {
			if (x > 0) {
				y += ROW;
				x = 0;
			}
		};
		for (const item of Array.from(parts.legend.children) as HTMLElement[]) {
			const label = Array.from(item.childNodes)
				.filter((n) => n.nodeType === Node.TEXT_NODE)
				.map((n) => n.textContent)
				.join('')
				.replace(/\s+/g, ' ')
				.trim();
			const sw = item.firstElementChild as HTMLElement | SVGElement | null;
			if (!sw) {
				// A heading such as "Satellite record:" starts its own line when it is long.
				const w = measure(label, fSmall);
				if (x > 0 && x + w > inner) newline();
				if (w > inner) {
					newline();
					for (const l of wrap(label, fSmall)) {
						head.push(node('text', { x: PAD, y: y + 14, fill: ink2, 'font-family': family, 'font-size': SMALL }, l));
						y += ROW;
					}
					continue;
				}
				head.push(node('text', { x: PAD + x, y: y + 14, fill: ink2, 'font-family': family, 'font-size': SMALL }, label));
				x += w + 14;
				continue;
			}
			const box = sw.getBoundingClientRect();
			const w = box.width + 6 + measure(label, fSmall);
			if (x > 0 && x + w > inner) newline();
			const g = node('g', { transform: `translate(${PAD + x} ${y + (ROW - box.height) / 2})` });
			const cs = getComputedStyle(sw);
			const bg = cs.backgroundColor;
			if (sw instanceof HTMLElement && bg && bg !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(bg)) {
				g.append(node('rect', { width: box.width, height: box.height, rx: parseFloat(cs.borderTopLeftRadius) || 0, fill: bg }));
			}
			const svgs = sw instanceof SVGSVGElement ? [sw] : Array.from(sw.querySelectorAll('svg'));
			for (const s of svgs) {
				const r = s.getBoundingClientRect();
				const c = s.cloneNode(true) as SVGSVGElement;
				inlineStyles(s, c);
				c.setAttribute('x', String(r.left - box.left));
				c.setAttribute('y', String(r.top - box.top));
				c.setAttribute('width', String(r.width));
				c.setAttribute('height', String(r.height));
				g.append(c);
			}
			head.push(g);
			head.push(node('text', { x: PAD + x + box.width + 6, y: y + 14, fill: ink2, 'font-family': family, 'font-size': SMALL }, label));
			x += w + 16;
		}
		y += x > 0 ? ROW : 0;
	}
	y += 12;

	const plot = svg.cloneNode(true) as SVGSVGElement;
	inlineStyles(svg, plot);
	plot.querySelectorAll('[data-export-skip]').forEach((n) => n.remove());
	for (const a of ['role', 'tabindex', 'aria-label', 'aria-roledescription']) plot.removeAttribute(a);
	plot.setAttribute('x', String(PAD + (inner - cw) / 2));
	plot.setAttribute('y', String(y));
	plot.setAttribute('width', String(cw));
	plot.setAttribute('height', String(ch));
	const H = Math.ceil(y + ch + PAD);

	out.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
	out.setAttribute('viewBox', `0 0 ${W} ${H}`);
	out.setAttribute('width', String(W));
	out.setAttribute('height', String(H));
	out.append(node('title', {}, parts.title));
	const desc = [parts.context, parts.subtitle].filter(Boolean).join('. ');
	if (desc) out.append(node('desc', {}, desc));
	out.append(node('rect', { width: '100%', height: '100%', fill: color('--surface', '#ffffff') }));
	out.append(...head, plot);
	return { text: '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(out), width: W, height: H };
}

export function downloadSvg(svg: SVGSVGElement, filename: string, parts: ChartParts): void {
	downloadBlob(filename, new Blob([chartImage(svg, parts).text], { type: 'image/svg+xml' }));
}

export async function downloadPng(svg: SVGSVGElement, filename: string, parts: ChartParts): Promise<void> {
	const { text, width, height } = chartImage(svg, parts);
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
		const c = canvas.getContext('2d')!;
		c.drawImage(img, 0, 0, canvas.width, canvas.height);
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
