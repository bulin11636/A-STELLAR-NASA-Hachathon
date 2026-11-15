import { useEffect, useRef, useState } from "react";
import { COORDINATE_SYSTEM, type MarsCoordinate, type PlanRouteRequest, type PlanRouteResponse, type RouteMode, type WalkingMission } from "../types/api.ts";
import type { RequestAttemptStatus } from "../types/attempts.ts";
import { ApiError } from "./apiClient.ts";
import { validateApiCoordinate } from "../geo/marsCoordinates.ts";
import { planRoute, validateRouteRequest } from "./routes.ts";
import { getStoredRoute, requireMatchingResult, type RouteMetadata } from "./metadata.ts";
import { getChatAttemptStatus, getPlanRequestStatus } from "./attempts.ts";
import { buildAdvancedContext, type AdvancedContext, type AnalysisFocus } from "./advancedContext.ts";
import { sendChat, type ChatResponse } from "./chat.ts";
import { asApiError, inspectFailure, localAttempt, readPending, rememberPending, requestId, usageUpdated } from "./requestRecovery.ts";

export type { AnalysisFocus } from "./advancedContext.ts";
export type PickMode = "inspect" | "start" | "goal" | "waypoint";
export type PlanningInterfaceMode = "quick" | "advanced";
type AdvancedInput = { message: string; focus: AnalysisFocus[]; allowRevision: boolean };
type PlanWork = { kind: "plan"; id: string; request: PlanRouteRequest; computed: boolean; advanced?: AdvancedInput };
type ChatWork = { kind: "chat"; id: string; routeId: string; message: string; context: AdvancedContext; baseRequest: PlanRouteRequest };
type Work = PlanWork | ChatWork;
const SESSION_KEY = "a-stellar.pending-planner.v1";

function rememberRoute(id: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("route", id); else url.searchParams.delete("route");
  window.history.replaceState(null, "", url);
}
function routeKey(request: { region_id: string; coordinate_system: string; start: MarsCoordinate; goal: MarsCoordinate; mode: RouteMode; waypoints?: MarsCoordinate[]; mission?: WalkingMission | null }) {
  return JSON.stringify([request.region_id, request.coordinate_system, [request.start.longitude, request.start.latitude], [request.goal.longitude, request.goal.latitude], request.mode, (request.waypoints ?? []).map(point => [point.longitude, point.latitude]), request.mission ? [request.mission.mode,request.mission.speed_m_s,request.mission.stop_minutes_per_waypoint,request.mission.exposure_duration_min,request.mission.radiation_budget_usv,request.mission.required_analyses] : null]);
}
function savedWork(): Work | null {
  const value = readPending(SESSION_KEY) as Work | null;
  try {
    if (!value || !/^[A-Za-z0-9_-]{16,64}$/.test(value.id)) return null;
    if (value.kind === "plan") {
      validateRouteRequest(value.request);
      if (typeof value.computed !== "boolean") return null;
      if (value.advanced) {
        if (!value.advanced.message.trim() || value.advanced.message.length > 1600 || typeof value.advanced.allowRevision !== "boolean") return null;
        buildAdvancedContext(value.request.mode, value.request.waypoints ?? [], value.advanced.focus, value.advanced.allowRevision);
      }
    } else if (value.kind === "chat") {
      if (!/^route-[a-f0-9]{32}$/.test(value.routeId) || !value.message.trim() || value.message.length > 1600) return null;
      validateRouteRequest(value.baseRequest);
      const c = value.context;
      buildAdvancedContext(c.route_objective, c.required_waypoints, c.analysis_focus, c.allow_supported_revision);
    } else return null;
    return value;
  } catch { return null; }
}

export function useRoutePlanner() {
  const [start, setStart] = useState<MarsCoordinate | null>(null);
  const [goal, setGoal] = useState<MarsCoordinate | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>("inspect");
  const [mode, setMode] = useState<RouteMode>("safest");
  const [waypoints, setWaypoints] = useState<MarsCoordinate[]>([]);
  const [interfaceMode, setInterfaceModeState] = useState<PlanningInterfaceMode>("quick");
  const [analysisFocus, setAnalysisFocus] = useState<AnalysisFocus[]>(["terrain"]);
  const [allowSupportedRevision, setAllowSupportedRevision] = useState(true);
  const [additionalRequirements, setAdditionalRequirements] = useState("");
  const [walkingSpeed, setWalkingSpeed] = useState("");
  const [waypointDwell, setWaypointDwell] = useState("0");
  const [exposureDuration, setExposureDuration] = useState("");
  const [radiationBudget, setRadiationBudget] = useState("");
  const [requiredAnalyses, setRequiredAnalyses] = useState<Array<"A2" | "A3" | "A4" | "A6">>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [result, setResult] = useState<PlanRouteResponse | null>(null);
  const [metadata, setMetadata] = useState<RouteMetadata | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attemptStatus, setAttemptStatus] = useState<RequestAttemptStatus | null>(null);
  const [pending, setPending] = useState<Work | null>(null);
  const [advancedReply, setAdvancedReply] = useState<ChatResponse | null>(null);
  const [chatRefresh, setChatRefresh] = useState(0);
  const [draftVersion, setDraftVersion] = useState(0);
  const active = useRef<AbortController | null>(null);
  const checking = useRef<AbortController | null>(null);
  const pendingRef = useRef<Work | null>(null);
  const displayed = useRef<PlanRouteResponse | null>(null);
  const version = useRef(0);

  function savePending(value: Work | null) {
    pendingRef.current = value; setPending(value); rememberPending(SESSION_KEY, value);
  }
  function cancelFlight() {
    version.current += 1;
    active.current?.abort(); active.current = null;
    checking.current?.abort(); checking.current = null;
  }
  function editDraft() {
    const wasActive = Boolean(active.current);
    setDraftVersion(value => value + 1); setAdvancedReply(null);
    cancelFlight(); setMetadataError(null); setError(null); setStatus("idle");
    if (!displayed.current) { setResult(null); setMetadata(null); }
    if (wasActive && pendingRef.current) setAttemptStatus(localAttempt(pendingRef.current.id, "unknown"));
    else if (!pendingRef.current) setAttemptStatus(null);
  }
  function applyResult(value: PlanRouteResponse, meta: RouteMetadata | null, updateDraft = true) {
    if (meta || value.source === "mock") displayed.current = value;
    setResult(value); setMetadata(meta); setMetadataError(null);
    if (updateDraft) {
      setStart(meta?.request.start ?? value.route[0]); setGoal(meta?.request.goal ?? value.route[value.route.length - 1]);
      setMode(value.mode); setWaypoints(meta?.request.waypoints ?? []); setPickMode("inspect");
      const mission=meta?.request.mission;
      if (mission) setInterfaceModeState("advanced");
      setWalkingSpeed(mission?.speed_m_s == null ? "" : String(mission.speed_m_s));
      setWaypointDwell(String(mission?.stop_minutes_per_waypoint ?? 0));
      setExposureDuration(mission?.exposure_duration_min == null ? "" : String(mission.exposure_duration_min));
      setRadiationBudget(mission?.radiation_budget_usv == null ? "" : String(mission.radiation_budget_usv));
      setRequiredAnalyses(mission?.required_analyses ?? []);
    }
    if (meta || value.source === "mock") rememberRoute(value.source === "computed" ? value.route_id : null);
  }
  function selectPoint(point: MarsCoordinate) {
    if (pickMode === "inspect" || (pickMode === "waypoint" && (interfaceMode !== "advanced" || waypoints.length >= 16))) return;
    editDraft();
    if (pickMode === "start") { setStart(point); setPickMode("goal"); }
    else if (pickMode === "goal") { setGoal(point); setPickMode("inspect"); }
    else addWaypoint(point);
  }
  function addWaypoint(point: MarsCoordinate) {
    try {
      if (interfaceMode !== "advanced") throw new Error("Choose Advanced mode to add required waypoints.");
      if (waypoints.length >= 16) throw new Error("Use at most 16 ordered waypoints.");
      validateApiCoordinate(point);
      const next = [...waypoints, point];
      if (start && goal) validateRouteRequest({ region_id: "jezero", coordinate_system: COORDINATE_SYSTEM, start, goal, mode, waypoints: next });
      editDraft(); setWaypoints(next);
    } catch (reason) { selectionError(reason instanceof Error ? reason.message : "Invalid waypoint."); }
  }
  function changeMode(value: RouteMode) { editDraft(); setMode(value); }
  function setInterfaceMode(value: PlanningInterfaceMode) { editDraft(); setInterfaceModeState(value); setPickMode("inspect"); }
  function loadExample(request: PlanRouteRequest) {
    validateRouteRequest(request); editDraft();
    setStart(request.start); setGoal(request.goal); setMode(request.mode); setPickMode("inspect"); setWaypoints(request.waypoints ?? []);
  }
  function clear() {
    cancelFlight(); savePending(null); displayed.current = null;
    rememberRoute(null); setResult(null); setMetadata(null); setMetadataError(null); setError(null); setAttemptStatus(null);
    setWalkingSpeed(""); setWaypointDwell("0"); setExposureDuration(""); setRadiationBudget(""); setRequiredAnalyses([]);
    setAdvancedReply(null); setStatus("idle"); setStart(null); setGoal(null); setWaypoints([]); setPickMode("inspect");
  }
  function moveWaypoint(index: number, direction: -1 | 1) {
    const target = index + direction; if (target < 0 || target >= waypoints.length) return;
    editDraft(); setWaypoints(items => { const next = [...items]; [next[index], next[target]] = [next[target], next[index]]; return next; });
  }
  function removeWaypoint(index: number) { editDraft(); setWaypoints(items => items.filter((_, i) => i !== index)); }
  function acceptRevision(value: PlanRouteResponse, revised: RouteMetadata) {
    cancelFlight(); savePending(null); setError(null); setAttemptStatus(null);
    applyResult(value, revised); setStatus("success");
  }
  function selectionError(message: string) {
    setError(new ApiError(message, "VALIDATION_ERROR")); setStatus("error");
  }
  function missionSettings(): WalkingMission | undefined {
    if (interfaceMode !== "advanced" || (!walkingSpeed.trim() && Number(waypointDwell || '0') === 0 && !exposureDuration.trim() && !radiationBudget.trim() && !requiredAnalyses.length)) return undefined;
    return { mode: "walking", speed_m_s: walkingSpeed.trim() ? Number(walkingSpeed) : null,
      stop_minutes_per_waypoint: Number(waypointDwell || '0'), exposure_duration_min: exposureDuration.trim() ? Number(exposureDuration) : null,
      radiation_budget_usv: radiationBudget.trim() ? Number(radiationBudget) : null, required_analyses: [...requiredAnalyses] };
  }
  function currentRequest(): PlanRouteRequest {
    if (!start || !goal) throw new Error("Select both Start and Goal.");
    return { region_id: "jezero", coordinate_system: COORDINATE_SYSTEM, start, goal, mode,
      ...(interfaceMode === "advanced" && waypoints.length ? { waypoints } : {}), ...(missionSettings() ? { mission: missionSettings() } : {}) };
  }
  function sameDraft(work: Work | null) {
    if (!work || !start || !goal) return false;
    if (work.kind === "plan") return routeKey(work.request) === routeKey(currentRequest()) &&
      JSON.stringify(work.advanced ?? null) === JSON.stringify(interfaceMode === "advanced" ? { message: additionalRequirements.trim(), focus: analysisFocus, allowRevision: allowSupportedRevision } : null);
    return interfaceMode === "advanced" && routeKey(work.baseRequest) === routeKey(currentRequest()) && work.message === additionalRequirements.trim() &&
      work.context.route_objective === mode && JSON.stringify(work.context.required_waypoints) === JSON.stringify(waypoints) &&
      JSON.stringify(work.context.analysis_focus) === JSON.stringify(analysisFocus) && work.context.allow_supported_revision === allowSupportedRevision;
  }
  const blockedByPending = sameDraft(pending);
  let inputError: string | null = null;
  if (start && goal) { try { validateRouteRequest(currentRequest()); } catch (reason) { inputError = reason instanceof Error ? reason.message : "Invalid inputs."; } }
  const canSubmit = !inputError && Boolean(start && goal) && status !== "loading" && !blockedByPending &&
    (interfaceMode === "quick" || (analysisFocus.length > 0 && additionalRequirements.trim().length > 0 && additionalRequirements.trim().length <= 1600));

  function loadStatus(work: Work, signal?: AbortSignal) {
    return work.kind === "plan" ? getPlanRequestStatus(work.id, signal) : getChatAttemptStatus(work.routeId, work.id, signal);
  }
  async function refreshAttempt() {
    const work = pendingRef.current; if (!work || active.current) return;
    checking.current?.abort(); const controller = new AbortController(); checking.current = controller;
    const epoch = version.current;
    try {
      const value = await loadStatus(work, controller.signal);
      if (!controller.signal.aborted && epoch === version.current && pendingRef.current?.id === work.id) setAttemptStatus(value);
    } catch { /* Keep the last known outcome; never turn a failed status read into permission to execute. */ }
    finally { if (checking.current === controller) checking.current = null; }
  }
  async function execute(work: Work, retryAttempt?: number, replay = false) {
    if (active.current) return;
    checking.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const epoch = ++version.current;
    const current = () => !controller.signal.aborted && epoch === version.current;
    let action = work;
    savePending(action); setError(null); setMetadataError(null); setStatus("loading");
    setAttemptStatus(localAttempt(action.id, "running", null, retryAttempt === undefined ? (attemptStatus?.request_id === action.id ? attemptStatus.attempt : 1) : retryAttempt + (replay ? 0 : 1)));
    try {
      if (action.kind === "plan") {
        const response = await planRoute(action.request, controller.signal, action.computed ? { idempotencyKey: action.id, retryAttempt } : {});
        if (!current()) return;
        if (response.source !== "computed") applyResult(response, null);
        else {
          if (!displayed.current) applyResult(response, null, false);
          try {
            const stored = await getStoredRoute(response.route_id, controller.signal);
            if (!current()) return;
            requireMatchingResult(stored, response);
            if (routeKey(stored.metadata.request) !== routeKey(action.request)) throw new Error("Stored route inputs do not match the submitted request.");
            applyResult(response, stored.metadata);
            if (action.advanced) {
              action = { kind: "chat", id: requestId("advanced"), routeId: response.route_id, message: action.advanced.message, baseRequest: structuredClone(action.request),
                context: buildAdvancedContext(stored.metadata.request.mode, stored.metadata.request.waypoints, action.advanced.focus, action.advanced.allowRevision) };
              savePending(action); retryAttempt = undefined;
              setAttemptStatus(localAttempt(action.id, "running"));
            }
          } catch (reason) {
            if (!current()) return;
            setMetadataError(reason instanceof Error ? reason.message : "Route metadata unavailable.");
            throw reason instanceof ApiError ? reason : new ApiError("The base route metadata could not be verified. A0 chat was not sent.", "INVALID_RESPONSE");
          }
        }
      }
      if (action.kind === "chat") {
        const reply = await sendChat(action.routeId, action.message, action.id, controller.signal, action.context, retryAttempt);
        if (!current()) return;
        if (!action.context.allow_supported_revision && reply.result) throw new ApiError("An explanation-only request returned a revision; the displayed route is unchanged.", "INVALID_RESPONSE");
        if (reply.result && reply.metadata) applyResult(reply.result, reply.metadata);
        setAdvancedReply(reply); setChatRefresh(value => value + 1);
      }
      if (!current()) return;
      setAttemptStatus(localAttempt(action.id, "succeeded", null, retryAttempt === undefined ? 1 : retryAttempt + (replay ? 0 : 1)));
      savePending(null); setStatus("success");
    } catch (reason) {
      if (!current()) return;
      const problem = asApiError(reason); setError(problem); setStatus("error");
      if (action.kind === "plan" && !action.computed) savePending(null);
      else {
        const value = await inspectFailure(action.id, problem, () => loadStatus(action, controller.signal));
        if (current() && pendingRef.current?.id === action.id) setAttemptStatus(value);
      }
    } finally {
      usageUpdated(); if (active.current === controller) active.current = null;
    }
  }
  async function submit(computed = false) {
    if (active.current || sameDraft(pendingRef.current)) return;
    try {
      const request = currentRequest(); validateRouteRequest(request);
      let advanced: AdvancedInput | undefined;
      if (interfaceMode === "advanced") {
        if (!computed) throw new Error("Advanced planning requires an available computed backend.");
        const message = additionalRequirements.trim();
        if (!message || message.length > 1600) throw new Error("Enter 1–1,600 characters of additional requirements.");
        buildAdvancedContext(mode, waypoints, analysisFocus, allowSupportedRevision);
        advanced = { message, focus: [...analysisFocus], allowRevision: allowSupportedRevision };
      }
      await execute(structuredClone({ kind: "plan", id: requestId("plan"), request, computed, ...(advanced ? { advanced } : {}) }));
    } catch (reason) { selectionError(reason instanceof Error ? reason.message : "Invalid planning inputs."); }
  }
  async function retry() {
    const work = pendingRef.current;
    if (work && attemptStatus?.state === "failed" && attemptStatus.retry_allowed && !attemptStatus.retry_after_seconds) await execute(work, attemptStatus.attempt);
  }
  async function recover() {
    if (pendingRef.current && attemptStatus?.state === "succeeded") await execute(pendingRef.current, attemptStatus.attempt, true);
  }

  useEffect(() => {
    const controller = new AbortController(); const epoch = version.current;
    const work = savedWork();
    if (work) {
      savePending(work); setAttemptStatus(localAttempt(work.id, "unknown"));
      loadStatus(work, controller.signal).then(value => {
        if (!controller.signal.aborted && epoch === version.current && pendingRef.current?.id === work.id) setAttemptStatus(value);
      }).catch(() => {});
    }
    const id = typeof window !== "undefined" ? new URL(window.location.href).searchParams.get("route") : null;
    if (id) {
      setStatus("loading");
      getStoredRoute(id, controller.signal).then(stored => {
        if (!controller.signal.aborted && epoch === version.current) { applyResult(stored.result, stored.metadata); setStatus("success"); }
      }).catch(reason => {
        if (!controller.signal.aborted && epoch === version.current) { setError(asApiError(reason)); setStatus("error"); }
      });
    }
    return () => { controller.abort(); cancelFlight(); };
  }, []);

  return { start, goal, waypoints, pickMode, setPickMode, mode, changeMode, loadExample, acceptRevision, status, result, metadata,
    metadataError, error, attemptStatus, selectPoint, addWaypoint, clear, moveWaypoint, removeWaypoint, submit, selectionError,
    interfaceMode, setInterfaceMode, analysisFocus, setAnalysisFocus: (value: AnalysisFocus[]) => { editDraft(); setAnalysisFocus(value); },
    allowSupportedRevision, setAllowSupportedRevision: (value: boolean) => { editDraft(); setAllowSupportedRevision(value); },
    additionalRequirements, setAdditionalRequirements: (value: string) => { editDraft(); setAdditionalRequirements(value); }, pendingKind: pending?.kind ?? null, canSubmit, retry, recover, refreshAttempt,
    advancedReply, chatRefresh, draftVersion, inputError,
    walkingSpeed, setWalkingSpeed: (value: string) => { editDraft(); setWalkingSpeed(value); },
    waypointDwell, setWaypointDwell: (value: string) => { editDraft(); setWaypointDwell(value); },
    exposureDuration, setExposureDuration: (value: string) => { editDraft(); setExposureDuration(value); },
    radiationBudget, setRadiationBudget: (value: string) => { editDraft(); setRadiationBudget(value); },
    requiredAnalyses, setRequiredAnalyses: (value: typeof requiredAnalyses) => { editDraft(); setRequiredAnalyses(value); } };
}
