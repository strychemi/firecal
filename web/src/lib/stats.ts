// Client-side copy of the contract's stats rules (docs/api.md, "stats").
// Used only in example mode, where the static files hold the full-range
// response for the default month and baseline. The live API is the source of truth.
import { MONTH_NAMES, median, ordinal } from './format';
import type { Baseline, Category, MonthRow, QueryResponse, Stats, YearMonth } from './types';

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

const r = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;

export function computeStats(series: MonthRow[], selected: YearMonth, baseline: Baseline): Stats {
	const cur = series.find((m) => m.month === selected);
	if (!cur) throw new Error(`Month ${selected} is outside the data.`);
	if (cur.in_progress) throw new Error(`${selected} is in progress; its comparison needs the API.`);
	const mon = selected.slice(5);
	const others = series.filter((m) => m.month.slice(5) === mon && m.month !== selected && m.complete);
	const vals = others.map((m) => m.value);
	const base = vals.length
		? baseline === 'median'
			? median(vals)
			: vals.reduce((a, b) => a + b, 0) / vals.length
		: 0;
	const ratio = base > 0 ? cur.value / base : null;
	const rank = 1 + vals.filter((v) => v > cur.value).length;
	const pct = vals.length ? r((vals.filter((v) => v < cur.value).length / vals.length) * 100, 1) : null;
	const name = `${MONTH_NAMES[Number(mon) - 1]} ${selected.slice(0, 4)}`;
	const word = baseline === 'median' ? 'median' : 'average';
	const n = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(cur.value);
	let sentence: string;
	if (cur.value === 0 && base === 0) {
		sentence = `No fire was detected in ${name}, and the same month is usually fire-free here.`;
	} else if (ratio === null) {
		sentence = `${name} had ${n} fire-days; the same month is usually fire-free here.`;
	} else {
		sentence =
			`${name} had ${n} fire-days, ${ratio.toFixed(1)}× the usual ` +
			`${MONTH_NAMES[Number(mon) - 1]} (${word} of ${vals.length} years), ` +
			`${ordinal(rank)} highest of ${vals.length + 1} years.`;
	}
	return {
		month: selected,
		value: cur.value,
		lower: cur.lower,
		upper: cur.upper,
		source: cur.source,
		baseline,
		baseline_value: r(base, 2),
		baseline_years: others.map((m) => Number(m.month.slice(0, 4))),
		ratio: ratio === null ? null : r(ratio, 3),
		rank,
		of: vals.length + 1,
		percentile: pct,
		category: ratio === null ? null : categoryOf(ratio),
		sentence
	};
}

/** Re-shape a full-range example response as if the API had answered `req`. */
export function reshapeExample(
	full: QueryResponse & { to_date_stats?: Record<Baseline, Stats> },
	start: YearMonth,
	end: YearMonth,
	month: YearMonth,
	baseline: Baseline
): QueryResponse {
	return {
		...full,
		start,
		end,
		months: full.months.filter((m) => m.month >= start && m.month <= end),
		// The in-progress month's days-1..D comparison is saved in the example file (reference.write_examples).
		stats: full.months.find((m) => m.month === month)?.in_progress
			? (full.to_date_stats?.[baseline] ?? full.stats)
			: computeStats(full.months, month, baseline),
		// Per-hexagon values in an example file are only valid for the request it was saved from.
		cells: start === full.start && end === full.end && month === full.stats.month ? full.cells : null
	};
}
