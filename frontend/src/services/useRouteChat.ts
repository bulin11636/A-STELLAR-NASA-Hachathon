import { useEffect, useRef, useState } from "react";
import type { PlanRouteResponse } from "../types/api.ts";
import type { RequestAttemptStatus } from "../types/attempts.ts";
import type { RouteMetadata } from "./metadata.ts";
import { ApiError } from "./apiClient.ts";
import { chatHistory, sendChat, type ChatResponse } from "./chat.ts";
import { getChatAttemptStatus } from "./attempts.ts";
import { buildAdvancedContext, type AdvancedContext } from "./advancedContext.ts";
import { asApiError, inspectFailure, localAttempt, readPending, rememberPending, requestId, usageUpdated } from "./requestRecovery.ts";

type ChatAction = { id: string; routeId: string; message: string; context?: AdvancedContext };
const storageKey = (routeId: string) => `a-stellar.pending-chat.v1.${routeId}`;
function restored(routeId: string): ChatAction | null {
  const saved = readPending(storageKey(routeId)) as ChatAction | null;
  try {
    if (!saved || saved.routeId !== routeId || !/^[A-Za-z0-9_-]{16,64}$/.test(saved.id) || !saved.message.trim() || saved.message.length > 1600) return null;
    if (saved.context) buildAdvancedContext(saved.context.route_objective, saved.context.required_waypoints, saved.context.analysis_focus, saved.context.allow_supported_revision);
    return saved;
  } catch { return null; }
}

export function useRouteChat(routeId: string, onRevision: (result: PlanRouteResponse, metadata: RouteMetadata) => void,
  context?: AdvancedContext, refreshKey = 0, disabled = false, selectionVersion = 0) {
  const [messages, setMessages] = useState<ChatResponse[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<RequestAttemptStatus | null>(null);
  const [hasPending, setHasPending] = useState(false);
  const active = useRef<AbortController | null>(null);
  const checking = useRef<AbortController | null>(null);
  const pending = useRef<ChatAction | null>(null);
  const version = useRef(0);
  const currentRoute = useRef(routeId); currentRoute.current = routeId;

  function save(action: ChatAction | null) {
    pending.current = action; setHasPending(Boolean(action)); rememberPending(storageKey(routeId), action);
  }
  async function refreshAttempt() {
    const action = pending.current; if (!action || active.current) return;
    checking.current?.abort(); const controller = new AbortController(); checking.current = controller;
    const epoch = version.current;
    try {
      const value = await getChatAttemptStatus(action.routeId, action.id, controller.signal);
      if (!controller.signal.aborted && epoch === version.current && pending.current?.id === action.id) setAttempt(value);
    } catch { /* An unavailable status endpoint cannot grant retry permission. */ }
    finally { if (checking.current === controller) checking.current = null; }
  }
  useEffect(() => {
    const controller = new AbortController(); const epoch = ++version.current;
    active.current?.abort(); active.current = null; checking.current?.abort();
    setMessages([]); setError(null); setBusy(false); setAttempt(null);
    const action = restored(routeId); save(action);
    if (action) {
      setText(action.message); setAttempt(localAttempt(action.id, "unknown"));
      getChatAttemptStatus(routeId, action.id, controller.signal).then(value => {
        if (!controller.signal.aborted && epoch === version.current && pending.current?.id === action.id) setAttempt(value);
      }).catch(() => {});
    } else setText("");
    chatHistory(routeId, controller.signal).then(items => {
      if (!controller.signal.aborted && epoch === version.current) setMessages(items);
    }).catch(reason => {
      if (!controller.signal.aborted && epoch === version.current) setError(reason instanceof Error ? reason.message : "Chat history unavailable.");
    });
    return () => { controller.abort(); version.current += 1; active.current?.abort(); active.current = null; checking.current?.abort(); };
  }, [routeId, refreshKey]);

  const contextKey = JSON.stringify(context ?? null);
  useEffect(() => {
    if (!active.current) return;
    version.current += 1; active.current.abort(); active.current = null; setBusy(false);
    if (pending.current) setAttempt(localAttempt(pending.current.id, "unknown"));
  }, [contextKey, disabled, selectionVersion]);

  async function run(action: ChatAction, retryAttempt?: number, replay = false) {
    if (active.current || disabled) return;
    const controller = new AbortController(); active.current = controller;
    checking.current?.abort(); const epoch = ++version.current;
    const current = () => !controller.signal.aborted && epoch === version.current && currentRoute.current === action.routeId;
    save(action); setBusy(true); setError(null); setAttempt(localAttempt(action.id, "running", null, retryAttempt === undefined ? 1 : retryAttempt + (replay ? 0 : 1)));
    try {
      const response = await sendChat(action.routeId, action.message, action.id, controller.signal, action.context, retryAttempt);
      if (!current()) return;
      if (response.message_id !== action.id || response.user_message !== action.message) throw new ApiError("The chat response does not match the saved request.", "INVALID_RESPONSE");
      if (action.context?.allow_supported_revision === false && response.result) throw new ApiError("An explanation-only request returned a revision; the current route is unchanged.", "INVALID_RESPONSE");
      setMessages(items => [...items.filter(item => item.message_id !== response.message_id), response]);
      setText(""); save(null); setAttempt(localAttempt(action.id, "succeeded", null, retryAttempt === undefined ? 1 : retryAttempt + (replay ? 0 : 1)));
      if (response.result && response.metadata) onRevision(response.result, response.metadata);
    } catch (reason) {
      if (!current()) return;
      const problem = asApiError(reason); setError(`${problem.code}: ${problem.message}`);
      const value = await inspectFailure(action.id, problem, () => getChatAttemptStatus(action.routeId, action.id, controller.signal));
      if (current() && pending.current?.id === action.id) setAttempt(value);
    } finally {
      usageUpdated(); if (active.current === controller) { active.current = null; setBusy(false); }
    }
  }
  const samePending = pending.current?.routeId === routeId && pending.current.message === text.trim() &&
    JSON.stringify(pending.current.context ?? null) === contextKey;
  const canSend = !busy && !disabled && Boolean(text.trim()) && text.trim().length <= 1600 && !samePending;
  async function submit() {
    if (!canSend) return;
    await run(structuredClone({ routeId, message: text.trim(), id: requestId("chat"), ...(context ? { context } : {}) }));
  }
  async function retry() {
    if (pending.current && attempt?.state === "failed" && attempt.retry_allowed && !attempt.retry_after_seconds) await run(pending.current, attempt.attempt);
  }
  async function recover() {
    if (pending.current && attempt?.state === "succeeded") await run(pending.current, attempt.attempt, true);
  }
  return { messages, text, setText, busy, error, attempt, hasPending, canSend, submit, retry, recover, refreshAttempt };
}
