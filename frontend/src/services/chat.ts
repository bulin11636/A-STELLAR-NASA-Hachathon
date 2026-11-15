import schema from "../types/chat.schema.json";
import type { ChatResponse } from "../types/routeMetadata.ts";
import { apiRequest, ApiError } from "./apiClient.ts";
import { checkSchema, decodeStoredRoute } from "./metadata.ts";
import type { AdvancedContext } from "./advancedContext.ts";

export type { ChatResponse };

export function decodeChat(body: unknown, routeId: string): ChatResponse {
  if (!checkSchema(body, schema, schema)) throw new Error("Invalid route chat response.");
  const message = body as ChatResponse;
  if (message.route_id !== routeId || Boolean(message.result) !== Boolean(message.metadata)) throw new Error("Chat route identity mismatch.");
  if (message.result) {
    const stored = decodeStoredRoute({ result: message.result, metadata: message.metadata }, message.result.route_id);
    if (stored.metadata.parent_route_id !== routeId) throw new Error("Chat revision does not reference the previous route.");
  }
  return message;
}

function validId(id: string) {
  if (!/^route-[a-f0-9]{32}$/.test(id)) throw new ApiError("Invalid route identifier.", "VALIDATION_ERROR");
}

export function sendChat(routeId: string, message: string, requestId: string, signal?: AbortSignal, advancedContext?: AdvancedContext) {
  validId(routeId);
  return apiRequest(`/api/v1/routes/${routeId}/chat`, (body) => decodeChat(body, routeId), {
    method: "POST", body: { message, request_id: requestId, ...(advancedContext ? { advanced_context: advancedContext } : {}) }, signal, timeoutMs: 90_000,
  });
}

export function chatHistory(routeId: string, signal?: AbortSignal): Promise<ChatResponse[]> {
  validId(routeId);
  return apiRequest(`/api/v1/routes/${routeId}/chat`, (body) => {
    if (typeof body !== "object" || body === null || !("messages" in body) || !Array.isArray(body.messages)) throw new Error("Invalid chat history.");
    return body.messages.map((message) => decodeChat(message, message.route_id));
  }, { signal });
}
