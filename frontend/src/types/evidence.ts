export type EvidenceState = "observed" | "scenario" | "prototype" | "unavailable";
export type ValidationStatus = "not_validated" | "validated_for_demo";
export type DataOrigin = "official_source" | "derived_from_official_source" | "synthetic_demo";

export interface LayerProvenance {
  sourceName: string;
  sourceUrl: string;
  origin: DataOrigin;
  observationDate: string | null;
  publicationDate: string | null;
  ingestionDate: string | null;
  resolution: string | null;
  units: string | null;
  coordinateSystem: string | null;
  limitations: readonly string[];
}

export interface EvidenceLayer {
  id: string;
  label: string;
  family: string;
  state: EvidenceState;
  validationStatus: ValidationStatus;
  renderable: boolean;
  provenance: LayerProvenance;
}
