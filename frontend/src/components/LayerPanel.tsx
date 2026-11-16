import { useState } from "react";
import { EVIDENCE_LAYERS, canToggleLayer, stateLabel } from "../map/layerRegistry.ts";

export interface LayerDisplayState {
  visible: boolean;
  opacity: number;
}

export default function LayerPanel({ layers, onLayerChange, availability = {}, issues = {} }: {
  layers: Readonly<Record<string, LayerDisplayState>>;
  availability?: Readonly<Record<string, boolean>>;
  issues?: Readonly<Record<string, string>>;
  onLayerChange: (id: string, change: Partial<LayerDisplayState>) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section className="layer-panel" aria-labelledby="layer-panel-title">
      <div className="info-heading">
        <h2 id="layer-panel-title">Layers & evidence</h2>
        <span className="badge">F2</span>
      </div>
      <p className="panel-intro">Layer availability is explicit. Disabled controls have no browser-ready artifact to display.</p>
      <ul className="layer-list">
        {EVIDENCE_LAYERS.map((layer) => {
          const control = layers[layer.id] ?? { visible: false, opacity: 1 };
          const toggleable = availability[layer.id] ?? canToggleLayer(layer);
          const open = expanded === layer.id;
          return <li key={layer.id} className="layer-card">
            <div className="layer-title-row">
              <div><strong>{layer.label}</strong><span className={`state-chip ${layer.state}`}>{stateLabel(layer.state)}</span></div>
              <label className="visibility-control">
                <input aria-label={`Show ${layer.label}`} type="checkbox" checked={control.visible}
                  disabled={!toggleable} onChange={(event) => onLayerChange(layer.id, { visible: event.target.checked })} />
                Show
              </label>
            </div>
            <p>{layer.family} · {layer.validationStatus === "validated_for_demo" ? "validated for demo" : "not validated"}</p>
            {issues[layer.id] && <p role="status" className="notice">{issues[layer.id]}</p>}
            {toggleable && <label className="opacity-control">Opacity
              <input aria-label={`${layer.label} opacity`} type="range" min="0" max="1" step="0.05" value={control.opacity}
                onChange={(event) => onLayerChange(layer.id, { opacity: Number(event.target.value) })} />
              <output>{Math.round(control.opacity * 100)}%</output>
            </label>}
            <button type="button" className="details-button" aria-expanded={open}
              onClick={() => setExpanded(open ? null : layer.id)}>{open ? "Hide details" : "Source & limitations"}</button>
            {open && <div className="layer-details">
              <dl>
                <dt>Source</dt><dd><a href={layer.provenance.sourceUrl} target="_blank" rel="noreferrer">{layer.provenance.sourceName} ↗</a></dd>
                <dt>Origin</dt><dd>{layer.provenance.origin}</dd>
                <dt>Resolution</dt><dd>{layer.provenance.resolution ?? "Unknown"}</dd>
                <dt>Units</dt><dd>{layer.provenance.units ?? "Unknown"}</dd>
                <dt>Coordinates</dt><dd>{layer.provenance.coordinateSystem ?? "Unknown"}</dd>
              </dl>
              <ul>{layer.provenance.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>}
          </li>;
        })}
      </ul>
    </section>
  );
}
