// Data layer: the firecal API (docs/api.md). The app has no other data source.
import type { Area, Meta, QueryRequest, QueryResponse, YearMonth } from './types';

export class HttpError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
		this.name = 'HttpError';
	}
}

/** Throws HttpError with the server's `error` message when there is one. */
async function send(url: string, init?: RequestInit): Promise<Response> {
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
	return res;
}

const post = (body: unknown): RequestInit => ({
	method: 'POST',
	headers: { 'content-type': 'application/json' },
	body: JSON.stringify(body)
});

/** GET /api/meta */
export async function fetchMeta(): Promise<Meta> {
	return (await send('/api/meta')).json();
}

/** POST /api/query */
export async function query(req: QueryRequest): Promise<QueryResponse> {
	return (await send('/api/query', post(req))).json();
}

/**
 * POST /api/export.csv: the filtered hotspots for an area and dates, as a CSV blob.
 * Throws HttpError with the server's message (413 when the search is over the row cap).
 */
export async function exportHotspots(req: { area: Area; start: YearMonth; end: YearMonth }): Promise<Blob> {
	return (await send('/api/export.csv', post(req))).blob();
}
