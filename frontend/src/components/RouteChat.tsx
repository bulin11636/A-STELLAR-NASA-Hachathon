import { useEffect, useRef, useState } from "react";
import { chatHistory, sendChat, type ChatResponse } from "../services/chat.ts";
import type { RouteMetadata } from "../services/metadata.ts";
import type { PlanRouteResponse } from "../types/api.ts";

export default function RouteChat({ routeId, onRevision }: { routeId: string; onRevision: (result: PlanRouteResponse, metadata: RouteMetadata) => void }) {
  const [messages, setMessages] = useState<ChatResponse[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const pendingId = useRef<{ route: string; text: string; id: string } | null>(null);
  const currentRoute = useRef(routeId); currentRoute.current = routeId;
  useEffect(() => {
    const controller = new AbortController();
    setMessages([]); setError(null); setBusy(false); pendingId.current = null;
    chatHistory(routeId, controller.signal).then((items) => { if (!controller.signal.aborted) setMessages(items); })
      .catch((error) => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Chat history unavailable."); });
    return () => { controller.abort(); active.current?.abort(); active.current = null; };
  }, [routeId]);
  return <section className="route-chat" aria-label="A0 route chat">
    <h3>Discuss this route with A0</h3>
    <p>Ask why, request shortest/safest, or specify waypoint coordinates as longitude,latitude in visit order. An explicit change creates a new route revision.</p>
    <div className="chat-transcript" aria-live="polite">{messages.map((message) => <article key={message.message_id}>
      <p><strong>You:</strong> {message.user_message}</p><p><strong>A0:</strong> {message.assistant_message}</p>
      {message.result && <p>Revision: {message.result.route_id}</p>}
      {message.usage && <small>{message.usage.input_tokens} input / {message.usage.output_tokens} output tokens · estimated ${message.usage.estimated_cost_usd.toFixed(4)}</small>}
    </article>)}</div>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (!text.trim() || active.current) return;
      const controller = new AbortController(); active.current = controller;
      setBusy(true); setError(null);
      try {
        const input = text.trim();
        if (pendingId.current?.route !== routeId || pendingId.current?.text !== input) {
          pendingId.current = { route: routeId, text: input, id: crypto.randomUUID() };
        }
        const response = await sendChat(routeId, input, pendingId.current.id, controller.signal);
        if (controller.signal.aborted || currentRoute.current !== routeId) return;
        setMessages((items) => [...items, response]); setText(""); pendingId.current = null;
        if (response.result && response.metadata) onRevision(response.result, response.metadata);
      } catch (error) {
        if (!controller.signal.aborted && currentRoute.current === routeId) setError(error instanceof Error ? error.message : "A0 request failed; previous route preserved.");
      } finally {
        if (typeof window !== "undefined") window.dispatchEvent(new Event("a0-usage-updated"));
        if (active.current === controller) { active.current = null; setBusy(false); }
      }
    }}>
      <label>Message A0<textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1600} rows={3} disabled={busy} /></label>
      <button disabled={busy || !text.trim()} type="submit">{busy ? "A0 is working…" : "Send to A0"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
  </section>;
}
