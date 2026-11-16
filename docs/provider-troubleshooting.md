# A0 provider diagnostics

HTTP 429 alone does not establish the cause. The provider can use it for request
or token rate limits, unavailable credits, and enforced usage or spend limits.
Use the specific `error.code` before the broader `error.type`.

| Provider code | Application code | Next step |
| --- | --- | --- |
| `rate_limit_exceeded`, `slow_down` | `A0_RATE_LIMITED` | Follow Retry-After and reduce bursts/request size. |
| `credit_balance_exhausted` | `A0_CREDIT_BALANCE_EXHAUSTED` | Review the API organization's prepaid credits. |
| `organization_usage_limit_exceeded` | `A0_API_USAGE_LIMIT` | Review the approved organization usage limit. |
| `organization_spend_limit_exceeded`, `project_spend_limit_exceeded` | `A0_API_SPEND_LIMIT` | An authorized administrator must review the enforced limit. |
| `insufficient_quota` | `A0_QUOTA_EXHAUSTED` | Review API credits and the key's organization/project limits. |
| Unrecognized or missing details | `A0_RATE_OR_QUOTA_LIMIT` | Inspect API settings or contact support; avoid guessing the cause. |

The backend preserves allowlisted codes/types, numeric Retry-After, an opaque
request ID and a timestamp in private application state. It discards arbitrary
provider error text. `GET /api/v1/a0/status` includes `last_provider_error` when
available. No credential or response body is retained in these diagnostics.
Older records containing only `http_429` cannot recover the missing cause.
There are no automatic generation retries.

For HTTP 200 responses whose proposal fails local validation, the backend also
records a fixed failure stage in `last_provider_error.error_code` and returns it
in the error details. `output_limit` means the model exhausted its output budget;
`completion` means another non-completed response; `tool_call` means a missing or
unexpected proposal call; `arguments` means the proposal schema failed;
`evidence_citations` means a citation was unavailable; `usage` means accounting
was absent or invalid; and `response_json`/`transport` identify response parsing
or receipt failures. These records contain no proposal text, credentials or user
messages. Older generic proposal failures cannot be diagnosed retroactively.
Route proposals now constrain citations to available evidence IDs in the tool
schema as well as in host validation. A failed proposal still preserves the
existing route, accounts for known usage, and never retries automatically.

Known failed chat requests repeat their recorded error on ordinary replay.
After resolving the cause, an explicit versioned retry can be requested when
the status endpoint permits it. Timeouts and abandoned requests remain blocked
under the original key. See the [backend handoff](backend-handoff.md) before
wiring retry controls; do not clear claims or silently create a new request ID.

From the repository root, inspect configuration and recorded errors locally:

```bash
python scripts/diagnose_a0.py
```

To also make one read-only model-list request:

```bash
python scripts/diagnose_a0.py --check-access
```

Both commands accept `--env-file /path/to/private.env`. The script never calls
Responses or generates model tokens, never prints credential values, and does
not create or modify the accounting ledger. A successful model-list request
does not establish generation eligibility, available balance or rate limits.

Review the API platform's [billing settings](https://platform.openai.com/settings/organization/billing/overview)
and [limits](https://platform.openai.com/settings/organization/limits) for the
organization/project used by the key. API access and ChatGPT subscription
allowances are separate. Changing account settings requires the appropriate
account role; this project does not change them automatically.

References: OpenAI's [429 troubleshooting](https://help.openai.com/en/articles/5955604-troubleshooting-api-rate-limits-and-429-errors),
[API error codes](https://developers.openai.com/api/docs/guides/error-codes), and
[billing separation](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform).
