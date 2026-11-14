import { useEffect, useState } from "react";
import { apiRequest } from "../services/apiClient.ts";

type Status = { mode: string; model: string; reasoning_effort: string; configured: boolean;
  budget?: { attempts: number; estimated_or_reserved_usd: number; max_attempts: number; budget_usd: number } };

export default function A0Status({ revision }: { revision?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const update = () => setRefresh((value) => value + 1);
    window.addEventListener("a0-usage-updated", update);
    return () => window.removeEventListener("a0-usage-updated", update);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    apiRequest("/api/v1/a0/status", (value) => {
      if (typeof value !== "object" || value === null) throw new Error("Invalid A0 status.");
      const item = value as Status;
      if (!["agentic", "deterministic"].includes(item.mode) || typeof item.model !== "string" || typeof item.configured !== "boolean") throw new Error("Invalid A0 status.");
      if (item.budget && (![item.budget.attempts, item.budget.estimated_or_reserved_usd, item.budget.max_attempts, item.budget.budget_usd].every((n) => typeof n === "number" && Number.isFinite(n) && n >= 0))) throw new Error("Invalid A0 usage.");
      return item;
    }, { signal: controller.signal }).then((value) => { if (!controller.signal.aborted) { setStatus(value); setError(null); } })
      .catch((error) => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "A0 status unavailable."); });
    return () => controller.abort();
  }, [revision, refresh]);
  return <div className="a0-status" role="status">
    {status ? <><p>A0 mode: <strong>{status.mode}</strong> · {status.model} / {status.reasoning_effort}</p>
      {status.mode === "agentic" && !status.configured && <p>Backend API credentials are missing.</p>}
      {status.budget && <p>API attempts: {status.budget.attempts}/{status.budget.max_attempts} · estimated/reserved ${status.budget.estimated_or_reserved_usd.toFixed(4)} / ${status.budget.budget_usd.toFixed(2)}. Codex subscription usage is separate.</p>}</> : <p>{error ?? "Loading A0 configuration…"}</p>}
  </div>;
}
