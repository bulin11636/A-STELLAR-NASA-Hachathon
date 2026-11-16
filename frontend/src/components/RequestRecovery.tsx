import { useEffect } from "react";
import type { RequestAttemptStatus } from "../types/attempts.ts";
import {readableText,errorTitle} from '../services/domainNames.ts';

export default function RequestRecovery({ status, busy, label, onRefresh, onRetry, onRecover }: {
  status: RequestAttemptStatus | null; busy: boolean; label: string;
  onRefresh: () => void; onRetry: () => void; onRecover: () => void;
}) {
  useEffect(() => {
    if (!status || busy || !(status.state === "running" || status.retry_after_seconds > 0)) return;
    const timer = setTimeout(onRefresh, 2000);
    return () => clearTimeout(timer);
  }, [status, busy, onRefresh]);
  if (!status) return null;
  return <section className="request-recovery" aria-label={`${label} request recovery`}>
    <p role="status">{label} request: {status.state}. Attempt {status.attempt}.</p>
    {status.state === "unknown" && <p>The outcome is uncertain. No automatic resubmission will be made. Your last successful route remains available.</p>}
    {status.state === "running" && <p>The backend may still be working. Checking status does not start another model request.</p>}
    {status.error && <p>{errorTitle(status.error.code)}: {readableText(status.error.message)}</p>}
    {status.error?.code==='A0_BUDGET_EXHAUSTED' && <p className="notice">The backend's local request or cost limit has been reached. Review the configured API budget, update the backend limit and restart it. Retry only after the limit is available; checking status alone does not replenish it.</p>}
    <p>Recovery uses the original request settings. Status checks do not generate model responses.</p>
    {status.retry_after_seconds > 0 && <p>Wait at least {status.retry_after_seconds} seconds. Status is checked before enabling a manual retry.</p>}
    <button type="button" disabled={busy} onClick={onRefresh}>Check {label.toLowerCase()} request status</button>
    {status.state === "failed" && status.retry_allowed && status.retry_after_seconds === 0 &&
      <button type="button" disabled={busy} onClick={onRetry}>Retry {label.toLowerCase()} request</button>}
    {status.state === "succeeded" && onRecover &&
      <button type="button" disabled={busy} onClick={onRecover}>Recover {label.toLowerCase()} result</button>}
    {status.state === "failed" && !status.retry_allowed && status.retry_after_seconds === 0 && <p>This recorded attempt cannot be retried.</p>}
  </section>;
}
