import type { useRoutePlanner } from "../services/useRoutePlanner.ts";
import { buildAdvancedContext } from "../services/advancedContext.ts";
import RouteChat from "./RouteChat.tsx";
import SpecialistTrace from "./SpecialistTrace.tsx";
import {domainName,readableText} from '../services/domainNames.ts';

export default function A0AssistantPanel({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  if (!planner.result) return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <h2 id="a0-assistant-title">{domainName('A0')}</h2>
    <p>Plan a route first, then discuss its results or request a supported revision with the planning assistant.</p>
  </section>;
  if (planner.result.source !== "computed") return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <h2 id="a0-assistant-title">{domainName('A0')}</h2>
    <p>The planning assistant requires a computed route. Plan one to start the discussion.</p>
  </section>;
  const advancedContext = planner.interfaceMode === "advanced" && planner.metadata && planner.analysisFocus.length
    ? buildAdvancedContext(planner.metadata.request.mode, planner.metadata.request.waypoints, planner.analysisFocus, planner.allowSupportedRevision)
    : undefined;
  return <section className="a0-assistant" aria-labelledby="a0-assistant-title">
    <div className="info-heading"><h2 id="a0-assistant-title">{domainName('A0')}</h2></div>
    <p>Discussion is bound to route <code>{planner.result.route_id}</code>. It cannot silently replace your route.</p>
    {planner.advancedReply && <section aria-label="Planning assistant response"><h3>Latest response</h3><p>{readableText(planner.advancedReply.assistant_message)}</p>
      <SpecialistTrace traces={planner.advancedReply.specialist_trace} />
      {!planner.advancedReply.result && <p>Informational reply. The base route did not change.</p>}
    </section>}
    <RouteChat routeId={planner.result.route_id} onRevision={planner.acceptRevision} refreshKey={planner.chatRefresh}
      disabled={planner.status === "loading" || !planner.metadata} selectionVersion={planner.draftVersion} advancedContext={advancedContext} />
  </section>;
}
