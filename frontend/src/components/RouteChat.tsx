import type { RouteMetadata } from "../services/metadata.ts";
import type { PlanRouteResponse } from "../types/api.ts";
import type { AdvancedContext } from "../services/advancedContext.ts";
import { useRouteChat } from "../services/useRouteChat.ts";
import SpecialistTrace from "./SpecialistTrace.tsx";
import RequestRecovery from "./RequestRecovery.tsx";

export default function RouteChat({ routeId, onRevision, advancedContext, refreshKey = 0, disabled = false, selectionVersion = 0 }: {
  routeId: string; onRevision: (result: PlanRouteResponse, metadata: RouteMetadata) => void;
  advancedContext?: AdvancedContext; refreshKey?: number; disabled?: boolean; selectionVersion?: number;
}) {
  const chat = useRouteChat(routeId, onRevision, advancedContext, refreshKey, disabled, selectionVersion);
  return <section className="route-chat" aria-label="A0 route chat">
    <h3>Discuss this route with A0</h3>
    <p>Discuss the displayed route. Ask why, request shortest/safest, or specify longitude,latitude coordinates in visit order.</p>
    <div className="chat-transcript" aria-live="polite">{chat.messages.map(message => <article key={message.message_id}>
      <p><strong>You:</strong> {message.user_message}</p><p><strong>A0:</strong> {message.assistant_message}</p>
      {message.result ? <p>Revision: {message.result.route_id}</p> : <p>Informational reply. The route did not change.</p>}
      <SpecialistTrace traces={message.specialist_trace} />
      {message.usage && <small>{message.usage.input_tokens} input / {message.usage.output_tokens} output tokens · estimated ${message.usage.estimated_cost_usd.toFixed(4)}</small>}
    </article>)}</div>
    <form onSubmit={async event => { event.preventDefault(); await chat.submit(); }}>
      <label>Message A0<textarea value={chat.text} onChange={event => chat.setText(event.target.value)} maxLength={1600} rows={3} disabled={chat.busy || disabled} /></label>
      <button disabled={!chat.canSend} type="submit">{chat.busy ? "A0 is working…" : "Send to A0"}</button>
    </form>
    {chat.error && <p role="alert">{chat.error}</p>}
    {chat.hasPending ? <RequestRecovery label="Chat" status={chat.attempt} busy={chat.busy || disabled}
      onRefresh={() => void chat.refreshAttempt()} onRetry={() => void chat.retry()} onRecover={() => void chat.recover()} />
      : chat.attempt && <p role="status">Chat request: {chat.attempt.state}.</p>}
  </section>;
}
