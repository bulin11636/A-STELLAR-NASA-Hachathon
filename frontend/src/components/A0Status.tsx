import { useEffect, useState } from "react";
import { apiRequest } from "../services/apiClient.ts";
import {readableText} from '../services/domainNames.ts';

type Status = { mode: "agentic" | "deterministic"; model: string; reasoning_effort: string; configured: boolean;
  checks?: { planning: boolean; storage: boolean; model_credentials: boolean };
  provider?: { availability: string; last_request_outcome: string; last_http_status: number | null };
  budget?: { attempts: number; estimated_or_reserved_usd: number; max_attempts: number; budget_usd: number } | null };

export default function A0Status({ revision, routingMode }: { revision?: string; routingMode?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const update = () => setRefresh(value => value + 1);
    window.addEventListener("a0-usage-updated", update);
    return () => window.removeEventListener("a0-usage-updated", update);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    apiRequest("/api/v1/a0/status", value => {
      if (typeof value !== "object" || value === null) throw new Error("Invalid A0 status.");
      const item = value as Status;
      if (!["agentic", "deterministic"].includes(item.mode) || typeof item.model !== "string" || typeof item.configured !== "boolean") throw new Error("Invalid A0 status.");
      if (item.budget && ![item.budget.attempts, item.budget.estimated_or_reserved_usd, item.budget.max_attempts, item.budget.budget_usd].every(n => typeof n === "number" && Number.isFinite(n) && n >= 0)) throw new Error("Invalid A0 usage.");
      if (item.checks && ![item.checks.planning, item.checks.storage, item.checks.model_credentials].every(n => typeof n === "boolean")) throw new Error("Invalid readiness checks.");
      if (typeof item.reasoning_effort !== "string") throw new Error("Invalid model configuration.");
      if (item.provider && (!["disabled", "not_checked"].includes(item.provider.availability) ||
          !["not_requested", "response_received", "rejected", "unknown"].includes(item.provider.last_request_outcome) ||
          (item.provider.last_http_status !== null && (!Number.isInteger(item.provider.last_http_status) || item.provider.last_http_status < 100 || item.provider.last_http_status > 599)))) {
        throw new Error("Invalid provider observation.");
      }
      return item;
    }, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setStatus(value); setError(null); } })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "A0 status unavailable."); });
    return () => controller.abort();
  }, [revision, refresh]);
  return <section className="a0-status" aria-label="Backend runtime status">
    {status ? <>
      <p>Routing: <strong>{routingMode === "mock" ? "mock" : routingMode === "computed" ? `computed / ${status.mode}` : "loading"}</strong>. Planning model: {status.model} / {status.reasoning_effort}.</p>
      {status.checks && <p>Dataset/profile: <strong>{status.checks.planning ? "ready" : "unavailable"}</strong>. Storage: <strong>{status.checks.storage ? "ready" : "unavailable"}</strong>.</p>}
      <p>API credential: {status.configured ? "configured" : "not configured"}.{status.mode === "deterministic" ? " Live planning assistance is disabled; chat provides terrain explanations and ordered stops can be edited in Advanced." : " Configuration does not confirm current provider access."}</p>
      {status.mode === "agentic" && !status.configured && <p role="alert">Configure the API credential in the backend runtime file to use the planning assistant.</p>}
      {status.provider && <p>Provider availability: {status.provider.availability.replaceAll("_", " ")}. Last request: {status.provider.last_request_outcome.replaceAll("_", " ")}{status.provider.last_http_status ? ` (HTTP ${status.provider.last_http_status})` : ""}.</p>}
      {status.budget && <p>Local API limits: {status.budget.attempts}/{status.budget.max_attempts} requests · ${status.budget.estimated_or_reserved_usd.toFixed(4)} / ${status.budget.budget_usd.toFixed(2)} estimated/reserved.
        {status.budget.attempts>=status.budget.max_attempts && <span role="alert"> Request count limit reached. Update the backend request limit and restart the backend before retrying.</span>}</p>}
    </> : <p role="status">{error ? readableText(error) : "Loading backend configuration…"}</p>}
  </section>;
}
