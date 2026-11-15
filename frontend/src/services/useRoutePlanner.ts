import { useEffect, useRef, useState } from "react";
import { COORDINATE_SYSTEM, type MarsCoordinate, type PlanRouteRequest, type PlanRouteResponse, type RouteMode } from "../types/api.ts";
import { ApiError } from "./apiClient.ts";
import { planRoute, validateRouteRequest } from "./routes.ts";
import { getStoredRoute, requireMatchingResult, type RouteMetadata } from "./metadata.ts";
import { getPlanRequestStatus } from "./attempts.ts";
import type { RequestAttemptStatus } from "../types/attempts.ts";

export type PickMode = "inspect" | "start" | "goal" | "waypoint";
export type PlanningInterfaceMode = "quick" | "advanced";
export type AnalysisFocus = "terrain" | "science" | "operations";

function rememberRoute(id: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("route", id); else url.searchParams.delete("route");
  window.history.replaceState(null, "", url);
}

export function useRoutePlanner() {
  const [start, setStart] = useState<MarsCoordinate | null>(null);
  const [goal, setGoal] = useState<MarsCoordinate | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>("inspect");
  const [mode, setMode] = useState<RouteMode>("safest");
  const [waypoints, setWaypoints] = useState<MarsCoordinate[]>([]);
  const [interfaceMode, setInterfaceMode] = useState<PlanningInterfaceMode>("quick");
  const [analysisFocus, setAnalysisFocus] = useState<AnalysisFocus[]>(["terrain"]);
  const [allowSupportedRevision, setAllowSupportedRevision] = useState(true);
  const [additionalRequirements, setAdditionalRequirements] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [result, setResult] = useState<PlanRouteResponse | null>(null);
  const [metadata, setMetadata] = useState<RouteMetadata | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attemptStatus, setAttemptStatus] = useState<RequestAttemptStatus | null>(null);
  const active = useRef<AbortController | null>(null);
  const planRequestId = useRef<string | null>(null);
  const version = useRef(0);

  useEffect(() => () => {
    version.current += 1;
    active.current?.abort();
    active.current = null;
  }, []);

  function invalidate() {
    rememberRoute(null);
    version.current += 1;
    active.current?.abort();
    active.current = null;
    setResult(null);
    setMetadata(null);
    setMetadataError(null);
    setError(null);
    setAttemptStatus(null);
    setStatus("idle");
  }

  function selectPoint(point: MarsCoordinate) {
    if (pickMode === "inspect") return;
    invalidate();
    if (pickMode === "start") { setStart(point); setPickMode("goal"); }
    else if (pickMode === "goal") { setGoal(point); setPickMode("inspect"); }
    else if (waypoints.length < 16) setWaypoints((items) => [...items, point]);
  }

  function changeMode(value: RouteMode) { invalidate(); setMode(value); }
  function loadExample(request: PlanRouteRequest) {
    validateRouteRequest(request);
    invalidate();
    setStart(request.start); setGoal(request.goal); setMode(request.mode); setPickMode("inspect");
    setWaypoints(request.waypoints ?? []);
  }
  function clear() { invalidate(); setStart(null); setGoal(null); setWaypoints([]); setPickMode("inspect"); }
  function moveWaypoint(index: number, direction: -1 | 1) {
    const target = index + direction; if (target < 0 || target >= waypoints.length) return;
    invalidate(); setWaypoints((items) => { const next = [...items]; [next[index], next[target]] = [next[target], next[index]]; return next; });
  }
  function removeWaypoint(index: number) { invalidate(); setWaypoints((items) => items.filter((_, item) => item !== index)); }
  function acceptRevision(result: PlanRouteResponse, revised: RouteMetadata) {
    invalidate();
    setStart(result.route[0]); setGoal(result.route[result.route.length-1]); setMode(result.mode);
    setWaypoints(revised.request.waypoints); setPickMode("inspect");
    setResult(result); setMetadata(revised); setStatus("success");
    rememberRoute(result.route_id);
  }
  function selectionError(message: string) {
    invalidate();
    setError(new ApiError(message, "VALIDATION_ERROR"));
    setStatus("error");
  }

  async function submit(computed = false) {
    // Ref gate closes synchronously, before React can disable the button.
    if (active.current) return;
    if (!start || !goal) { selectionError("Select both Start and Goal on the map."); return; }
    const controller = new AbortController();
    active.current = controller;
    const requestVersion = ++version.current;
    setAttemptStatus(null);
    setError(null);
    setStatus("loading");
    try {
      const requestId = computed ? (planRequestId.current ?? `plan_${crypto.randomUUID().replaceAll("-", "")}`) : undefined;
      planRequestId.current = requestId ?? null;
      const response = await planRoute({
        region_id: "jezero", coordinate_system: COORDINATE_SYSTEM, start, goal, mode,
        ...(waypoints.length ? { waypoints } : {}),
      }, controller.signal, requestId ? { idempotencyKey: requestId } : {});
      if (requestVersion !== version.current || controller.signal.aborted) return;
      setResult(response);
      setStatus("success");
      if (response.source === "computed") {
        try {
          const stored = await getStoredRoute(response.route_id, controller.signal);
          if (requestVersion !== version.current || controller.signal.aborted) return;
          requireMatchingResult(stored, response);
          setMetadata(stored.metadata);
          rememberRoute(response.route_id);
        } catch (reason) {
          if (requestVersion !== version.current || controller.signal.aborted) return;
          setMetadataError(reason instanceof Error ? reason.message : "Route metadata unavailable.");
        }
      }
    } catch (reason) {
      if (requestVersion !== version.current || controller.signal.aborted) return;
      setError(reason instanceof ApiError ? reason : new ApiError("Route planning failed. Please retry.", "CLIENT_ERROR"));
      setStatus("error");
      if (computed && planRequestId.current) {
        try { setAttemptStatus(await getPlanRequestStatus(planRequestId.current, controller.signal)); }
        catch { /* The original structured error remains actionable. */ }
      }
    } finally {
      if (typeof window !== "undefined") window.dispatchEvent(new Event("a0-usage-updated"));
      if (active.current === controller) active.current = null;
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const id = new URL(window.location.href).searchParams.get("route");
    if (!id) return;
    const controller = new AbortController();
    const restoreVersion = version.current;
    setStatus("loading");
    getStoredRoute(id, controller.signal).then((stored) => {
      if (!controller.signal.aborted && version.current === restoreVersion) acceptRevision(stored.result, stored.metadata);
    }).catch((reason) => {
      if (!controller.signal.aborted && version.current === restoreVersion) {
        setError(reason instanceof ApiError ? reason : new ApiError("Stored route could not be restored.", "INVALID_RESPONSE"));
        setStatus("error");
      }
    });
    return () => controller.abort();
  }, []);

  return { start, goal, waypoints, pickMode, setPickMode, mode, changeMode, loadExample, acceptRevision, status, result, metadata, metadataError, error, attemptStatus, selectPoint, clear, moveWaypoint, removeWaypoint, submit, selectionError, interfaceMode, setInterfaceMode, analysisFocus, setAnalysisFocus, allowSupportedRevision, setAllowSupportedRevision, additionalRequirements, setAdditionalRequirements };
}
