import WMTSCapabilities from "ol/format/WMTSCapabilities.js";
import Projection from "ol/proj/Projection.js";
import { addProjection } from "ol/proj.js";
import WMTS, { optionsFromCapabilities } from "ol/source/WMTS.js";
import WMTSTileGrid from "ol/tilegrid/WMTS.js";
import type { Extent } from "ol/extent.js";

// A NASA Jezero mosaic gives the registration workflow suitable imagery for
// the local 20 m CTX DEM. It remains unregistered until independent controls
// pass in the backend; source selection is not evidence of alignment.
export const LAYER_ID = "NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018";
export const NASA_CRS = "urn:ogc:def:crs:EPSG::104905";
export const CAPABILITIES_URL =
  `https://trek.nasa.gov/tiles/Mars/EQ/${LAYER_ID}/1.0.0/WMTSCapabilities.xml`;
export const CATALOG_URL = "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars";

const WMTS_NS = "http://www.opengis.net/wmts/1.0";
const OWS_NS = "http://www.opengis.net/ows/1.1";
const WORLD: Extent = [-180, -90, 180, 90];

function text(node: Element, ns: string, name: string): string {
  const value = node.getElementsByTagNameNS(ns, name)[0]?.textContent?.trim();
  if (!value) throw new Error(`NASA metadata is missing ${name}.`);
  return value;
}

function pair(value: string): number[] {
  const values = value.split(/\s+/).map(Number);
  if (values.length !== 2 || values.some((v) => !Number.isFinite(v))) {
    throw new Error("NASA metadata contains invalid coordinates.");
  }
  return values;
}

export async function loadMarsWmts(signal: AbortSignal) {
  const response = await fetch(CAPABILITIES_URL, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
  });
  if (!response.ok) throw new Error(`NASA metadata request failed (HTTP ${response.status}).`);
  return createMarsWmts(await response.text());
}

export function createMarsWmts(xml: string) {
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.querySelector("parsererror")) throw new Error("NASA returned invalid WMTS XML.");
  const layer = [...document.getElementsByTagNameNS(WMTS_NS, "Layer")].find(
    (element) => text(element, OWS_NS, "Identifier") === LAYER_ID,
  );
  if (!layer) throw new Error("The expected NASA Mars layer was not found.");
  const matrixSetId = text(layer, WMTS_NS, "TileMatrixSet");
  const matrixSet = [...document.getElementsByTagNameNS(WMTS_NS, "TileMatrixSet")].find(
    (element) => element.getElementsByTagNameNS(WMTS_NS, "TileMatrix").length > 0 &&
      text(element, OWS_NS, "Identifier") === matrixSetId,
  );
  if (!matrixSet || text(matrixSet, OWS_NS, "SupportedCRS") !== NASA_CRS) {
    throw new Error("NASA changed the Mars CRS or tile matrix set; review the integration.");
  }
  const bbox = [...layer.getElementsByTagNameNS(OWS_NS, "BoundingBox")].find(
    (element) => element.getAttribute("crs") === NASA_CRS,
  );
  if (!bbox) throw new Error("NASA metadata has no native Mars bounding box.");
  const extent: Extent = [
    ...pair(text(bbox, OWS_NS, "LowerCorner")),
    ...pair(text(bbox, OWS_NS, "UpperCorner")),
  ];
  if (extent[0] < WORLD[0] || extent[1] < WORLD[1] || extent[2] > WORLD[2] || extent[3] > WORLD[3]
    || extent[0] >= extent[2] || extent[1] >= extent[3]) {
    throw new Error("NASA metadata advertises an invalid native map coverage extent.");
  }

  // NASA uses an EPSG-shaped URN for Esri's Mars 2000 identifier. Its published
  // ESRI:104905 definition is an ellipsoidal geographic CRS. OpenLayers uses
  // native longitude/planetographic-latitude degrees; the API adapter makes
  // the planetocentric conversion explicitly rather than borrowing Earth CRS
  // transforms.
  const projection = new Projection({
    code: NASA_CRS,
    units: "degrees",
    axisOrientation: "enu",
    extent: WORLD,
    global: false,
    metersPerUnit: (3396190 * Math.PI) / 180,
  });
  addProjection(projection);

  const matrices = [...matrixSet.getElementsByTagNameNS(WMTS_NS, "TileMatrix")].map(
    (matrix) => {
      const origin = pair(text(matrix, WMTS_NS, "TopLeftCorner"));
      const width = Number(text(matrix, WMTS_NS, "MatrixWidth"));
      const height = Number(text(matrix, WMTS_NS, "MatrixHeight"));
      const tileWidth = Number(text(matrix, WMTS_NS, "TileWidth"));
      const tileHeight = Number(text(matrix, WMTS_NS, "TileHeight"));
      const resolution = 360 / (width * tileWidth);
      if (
        [width, height, tileWidth, tileHeight].some((v) => !Number.isInteger(v) || v <= 0) ||
        origin[0] !== WORLD[0] || origin[1] !== WORLD[3] ||
        Math.abs(resolution - 180 / (height * tileHeight)) > 1e-10
      ) throw new Error("NASA's tile grid no longer matches the verified global angular layout.");
      return {
        id: text(matrix, OWS_NS, "Identifier"), origin,
        resolution, size: [width, height], tileSize: [tileWidth, tileHeight],
      };
    },
  ).sort((a, b) => b.resolution - a.resolution);
  if (!matrices.length) throw new Error("NASA metadata contains no tile matrices.");

  const capabilities = new WMTSCapabilities().read(xml);
  const options = optionsFromCapabilities(capabilities, {
    layer: LAYER_ID, matrixSet: matrixSetId, requestEncoding: "REST",
  });
  if (!options?.urls?.length) throw new Error("NASA metadata has no usable REST tile URL.");

  // Preserve the advertised identifiers, style, format and ResourceURL. Replace
  // only the scale-derived grid: NASA's ScaleDenominator values use a different
  // metres/degree convention. Matrix dimensions and global degree bounds give
  // exact angular resolutions without borrowing an Earth radius. The layer may
  // cover only Jezero while its tile matrix remains global.
  const tileGrid = new WMTSTileGrid({
    extent,
    origins: matrices.map((matrix) => matrix.origin),
    resolutions: matrices.map((matrix) => matrix.resolution),
    matrixIds: matrices.map((matrix) => matrix.id),
    sizes: matrices.map((matrix) => matrix.size),
    tileSizes: matrices.map((matrix) => matrix.tileSize),
  });
  const source = new WMTS({
    ...options, projection, tileGrid, wrapX: false, crossOrigin: "anonymous",
    attributions: 'NASA / JPL-Caltech · Mars Global Surveyor / MOLA · <a href="https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars" target="_blank" rel="noreferrer">Mars Trek</a>',
  });
  return { source, projection, extent, matrixSetId, resolutions: tileGrid.getResolutions() };
}
