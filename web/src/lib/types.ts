// Types for the firecal API contract (docs/api.md, v0 prototype).

/** "YYYY-MM" */
export type YearMonth = string;
/** [minLon, minLat, maxLon, maxLat] */
export type BBox = [number, number, number, number];
export type Source = 'terra_harmonized' | 'aqua_harmonized' | 'viirs';
export type Baseline = 'median' | 'mean';
export type Category =
	| 'much lower than usual'
	| 'lower than usual'
	| 'about usual'
	| 'higher than usual'
	| 'much higher than usual';

export interface Era {
	start: string; // YYYY-MM-DD
	end: string;
	source: Source;
	chain: string[];
}

export interface Gap {
	start: string;
	end: string;
	days: number;
}

export interface ValidationEntry {
	whole_area_typical_error_pct: number;
	small_area_typical_error_pct: number;
	backward_join_gap_pct: number;
}

export interface Preset {
	id: string;
	name: string;
	note: string;
	bbox: BBox;
}

export interface Meta {
	data_version: string;
	series_start: YearMonth;
	series_end: YearMonth;
	unit: string;
	region: { bbox: BBox; countries: string[] };
	eras: Era[];
	gaps: Gap[];
	days_filled_by: Record<string, number>;
	validation: Record<string, ValidationEntry>;
	presets: Preset[];
}

export type Area =
	| { preset: string }
	| { bbox: BBox }
	| { polygon: [number, number][] }
	| { point: [number, number]; radius_km: number };

export interface QueryRequest {
	area: Area;
	start?: YearMonth;
	end?: YearMonth;
	month?: YearMonth;
	baseline?: Baseline;
}

export interface MonthRow {
	month: YearMonth;
	source: Source;
	value: number;
	lower: number | null;
	upper: number | null;
	raw: number;
	detections: number;
	frp: number;
	days: number;
	days_with_data: number;
	complete: boolean;
}

export interface Stats {
	month: YearMonth;
	value: number;
	lower: number | null;
	upper: number | null;
	source: Source;
	baseline: Baseline;
	baseline_value: number;
	baseline_years: number[];
	ratio: number | null;
	rank: number;
	of: number;
	/** null when there are no comparison years (reference implementation; not in docs/api.md) */
	percentile: number | null;
	/** null when ratio is null (baseline 0) (reference implementation; not in docs/api.md) */
	category: Category | null;
	sentence: string;
}

export interface QueryResponse {
	data_version: string;
	area: { resolution: number; hexagons: number; active_hexagons: number };
	start: YearMonth;
	end: YearMonth;
	months: MonthRow[];
	stats: Stats;
}

export interface ApiError {
	error: string;
}
