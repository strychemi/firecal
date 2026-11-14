import type { Source, YearMonth } from './types';

export const MONTH_NAMES = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];
export const MONTH_SHORT = MONTH_NAMES.map((m) => m.slice(0, 3));

const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

/** Whole number with thousands separators; null-safe. */
export function fmt(n: number | null | undefined): string {
	return n == null || !Number.isFinite(n) ? '–' : nf0.format(n);
}
export function fmt1(n: number | null | undefined): string {
	return n == null || !Number.isFinite(n) ? '–' : nf1.format(n);
}
/** Compact axis tick: 12k, 1.2M. */
export function fmtTick(n: number): string {
	const a = Math.abs(n);
	if (a >= 1e6) return `${nf1.format(n / 1e6)}M`;
	if (a >= 1e3) return `${nf1.format(n / 1e3)}k`;
	return nf0.format(n);
}

export function monthLabel(ym: YearMonth): string {
	const [y, m] = ym.split('-');
	return `${MONTH_NAMES[Number(m) - 1]} ${y}`;
}
export function monthShortLabel(ym: YearMonth): string {
	const [y, m] = ym.split('-');
	return `${MONTH_SHORT[Number(m) - 1]} ${y}`;
}

export const SOURCE_LABEL: Record<Source, string> = {
	terra_harmonized: 'Terra MODIS (converted)',
	aqua_harmonized: 'Aqua MODIS (converted)',
	viirs: 'VIIRS (observed)'
};
export const SOURCE_SATELLITE: Record<Source, string> = {
	terra_harmonized: 'Terra MODIS',
	aqua_harmonized: 'Aqua MODIS',
	viirs: 'VIIRS (S-NPP, then NOAA-20)'
};
export const SOURCE_SHORT: Record<Source, string> = {
	terra_harmonized: 'Terra',
	aqua_harmonized: 'Aqua',
	viirs: 'VIIRS'
};
export const SOURCES: Source[] = ['terra_harmonized', 'aqua_harmonized', 'viirs'];

export function ordinal(n: number): string {
	const s = n % 100 >= 10 && n % 100 <= 20 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
	return `${n}${s}`;
}

/** Inclusive list of YYYY-MM between a and b. */
export function monthRange(a: YearMonth, b: YearMonth): YearMonth[] {
	const out: YearMonth[] = [];
	let [y, m] = a.split('-').map(Number);
	const [ye, me] = b.split('-').map(Number);
	while (y < ye || (y === ye && m <= me)) {
		out.push(`${y}-${String(m).padStart(2, '0')}`);
		m++;
		if (m > 12) {
			m = 1;
			y++;
		}
	}
	return out;
}

export function median(xs: number[]): number {
	if (!xs.length) return 0;
	const s = [...xs].sort((a, b) => a - b);
	const k = Math.floor(s.length / 2);
	return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2;
}
