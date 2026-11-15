import type { useRoutePlanner } from "../services/useRoutePlanner.ts";
import { buildAdvancedContext } from "../services/advancedContext.ts";
import RouteChat from "./RouteChat.tsx";
import SpecialistTrace from "./SpecialistTrace.tsx";

export default function A0AssistantPanel({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  if (!planner.result) return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <h2 id="a0-assistant-title">A0 Assistant</h2>
    <p>Plan a computed route first. A0 then discusses that stored route and may only propose a supported revision.</p>
  </section>;
  if (planner.result.source !== "computed") return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <h2 id="a0-assistant-title">A0 Assistant</h2>
    <p>A0 discussion is unavailable for mock routes because they are not safety-validated route records.</p>
  </section>;
  const advancedContext = planner.interfaceMode === "advanced" && planner.metadata && planner.analysisFocus.length
    ? buildAdvancedContext(planner.metadata.request.mode, planner.metadata.request.waypoints, planner.analysisFocus, planner.allowSupportedRevision)
    : undefined;
  return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <div className="info-heading"><h2 id="a0-assistant-title">A0 Assistant</h2><span className="badge">A0</span></div>
    <p>Discussion is bound to route <code>{planner.result.route_id}</code>. It cannot silently replace your route.</p>
    {planner.advancedReply && <section aria-label="Advanced A0 response"><h3>Latest A0 response</h3><p>{planner.advancedReply.assistant_message}</p>
      <SpecialistTrace traces={planner.advancedReply.specialist_trace} />
      {!planner.advancedReply.result && <p>Informational reply. The base route did not change.</p>}
    </section>}
    <RouteChat routeId={planner.result.route_id} onRevision={planner.acceptRevision} refreshKey={planner.chatRefresh}
      disabled={planner.status === "loading" || !planner.metadata} selectionVersion={planner.draftVersion} advancedContext={advancedContext} />
  </section>;
}
