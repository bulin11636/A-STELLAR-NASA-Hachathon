import type { ErrorEnvelope } from "./api.ts";

export const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{16,64}$/;
export type RequestAttemptState = "running" | "succeeded" | "failed" | "unknown";

export interface RequestAttemptStatus {
  request_id: string;
  state: RequestAttemptState;
  attempt: number;
  retry_allowed: boolean;
  retry_after_seconds: number;
  error: ErrorEnvelope["error"] | null;
  updated_at: string | null;
}
