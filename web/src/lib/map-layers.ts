// deck.gl layers for the map, imported by name so the bundler keeps only these.
// MapView loads this module lazily, after the page has rendered.
import { PathLayer } from '@deck.gl/layers';
import { H3HexagonLayer } from '@deck.gl/geo-layers';

export interface HexDatum {
	h3: string;
	month: number;
	range: number;
}

export interface HexLayerOptions {
	data: HexDatum[];
	getFillColor: (d: HexDatum) => [number, number, number, number];
	lineColor: [number, number, number, number];
	highlightColor: [number, number, number, number];
	updateTrigger: string;
}

/** Hexagons from their H3 index. H3HexagonLayer also handles cells that cross the antimeridian. */
export function hexLayer(o: HexLayerOptions) {
	return new H3HexagonLayer<HexDatum>({
		id: 'hexes',
		data: o.data,
		getHexagon: (d) => d.h3,
		extruded: false,
		getFillColor: o.getFillColor,
		getLineColor: o.lineColor,
		lineWidthUnits: 'pixels',
		getLineWidth: 0.5,
		stroked: true,
		filled: true,
		pickable: true,
		autoHighlight: true,
		highlightColor: o.highlightColor,
		updateTriggers: { getFillColor: o.updateTrigger }
	});
}

/** The searched area's outline. */
export function outlineLayer(ring: [number, number][], color: [number, number, number, number]) {
	return new PathLayer<{ path: [number, number][] }>({
		id: 'area',
		data: [{ path: ring }],
		getPath: (d) => d.path,
		getColor: color,
		widthUnits: 'pixels',
		getWidth: 2
	});
}
