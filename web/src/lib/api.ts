// Data layer: the live API (docs/api.md), with a fallback to the saved
// example responses in static/example/ when the API is unreachable or when
// VITE_EXAMPLES=1.
import { reshapeExample } from './stats';
import type { Meta, QueryRequest, QueryResponse } from './types';

export type DataMode = 'api' | 'examples';

export class CustomAreaUnavailable extends Error {
	constructor() {
		super(
			'Custom boxes and circles need the live firecal API, which is not connected. ' +
				'The saved example data only covers the preset areas.'
		);
		this.name = 'CustomAreaUnavailable';
	}
}

const forceExamples = import.meta.env.VITE_EXAMPLES === '1';
let mode: DataMode = forceExamples ? 'examples' : 'api';
const exampleCache = new Map<string, Promise<QueryResponse>>();

export function dataMode(): DataMode {
	return mode;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
	const res = await fetch(url, init);
	if (!res.ok) {
		let msg = `${res.status} ${res.statusText}`;
		try {
			const body = await res.json();
			if (body && typeof body.error === 'string') msg = body.error;
		} catch {
			/* not JSON */
		}
		throw new HttpError(res.status, msg);
	}
	return (await res.json()) as T;
}

export class HttpError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
		this.name = 'HttpError';
	}
}

/** GET /api/meta, falling back to /example/meta.json on any failure. */
export async function fetchMeta(): Promise<{ meta: Meta; mode: DataMode }> {
	if (!forceExamples) {
		try {
			const meta = await getJson<Meta>('/api/meta');
			mode = 'api';
			return { meta, mode };
		} catch {
			/* fall through to examples */
		}
	}
	mode = 'examples';
	const meta = await getJson<Meta>('/example/meta.json');
	return { meta, mode };
}

/** POST /api/query (or the example file for a preset area in example mode). */
export async function query(req: QueryRequest, meta: Meta): Promise<QueryResponse> {
	if (mode === 'api') {
		return getJson<QueryResponse>('/api/query', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(req)
		});
	}
	if (!('preset' in req.area)) throw new CustomAreaUnavailable();
	const id = req.area.preset;
	if (!meta.presets.some((p) => p.id === id)) throw new Error(`Unknown preset "${id}".`);
	let p = exampleCache.get(id);
	if (!p) {
		p = getJson<QueryResponse>(`/example/query-${encodeURIComponent(id)}.json`);
		exampleCache.set(id, p);
		p.catch(() => exampleCache.delete(id));
	}
	const full = await p;
	const start = req.start ?? meta.series_start;
	const end = req.end ?? meta.series_end;
	return reshapeExample(full, start, end, req.month ?? end, req.baseline ?? 'median');
}
