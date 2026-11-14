"""Allowlisted provider diagnostics; never retain arbitrary response text."""
from datetime import datetime, timezone
import math
import re

KNOWN_CODES = {
    'insufficient_quota','credit_balance_exhausted','organization_usage_limit_exceeded',
    'organization_spend_limit_exceeded','project_spend_limit_exceeded','rate_limit_exceeded','slow_down',
}
KNOWN_TYPES = {'insufficient_quota','rate_limit_error','requests','tokens','invalid_request_error'}


def describe_429(body, headers):
    error = body.get('error') if isinstance(body,dict) else None
    error = error if isinstance(error,dict) else {}
    code,kind = error.get('code'),error.get('type')
    code = code if isinstance(code,str) and code in KNOWN_CODES else None
    kind = kind if isinstance(kind,str) and kind in KNOWN_TYPES else None
    choices = {
        'credit_balance_exhausted': ('credit_balance','A0_CREDIT_BALANCE_EXHAUSTED',
            'The API organization has no prepaid credits remaining. Review API billing for the organization used by this key.'),
        'organization_usage_limit_exceeded': ('organization_usage','A0_API_USAGE_LIMIT',
            'The API organization reached its approved usage limit. Review organization Limits or request a higher approved limit.'),
        'organization_spend_limit_exceeded': ('organization_spend','A0_API_SPEND_LIMIT',
            'The API organization reached its enforced spend limit. Its administrator must review that limit or wait for its reset.'),
        'project_spend_limit_exceeded': ('project_spend','A0_API_SPEND_LIMIT',
            'The API project reached its enforced spend limit. Its administrator must review that project limit or wait for its reset.'),
        'insufficient_quota': ('quota','A0_QUOTA_EXHAUSTED',
            'The API account reports insufficient quota. Review API credit and organization/project limits; subscription usage is separate.'),
        'rate_limit_exceeded': ('rate','A0_RATE_LIMITED',
            'The API request or token rate limit was reached. Wait according to Retry-After, then reduce request bursts or request size.'),
        'slow_down': ('rate','A0_RATE_LIMITED',
            'The API request rate increased too quickly. Wait according to Retry-After and spread requests over time.'),
    }
    # A specific code takes precedence over the broader insufficient_quota type.
    category,public_code,message = choices.get(code,choices['insufficient_quota'] if kind=='insufficient_quota' else
        choices['rate_limit_exceeded'] if kind in ('rate_limit_error','requests','tokens') else
        ('unknown','A0_RATE_OR_QUOTA_LIMIT','The API returned HTTP 429 without a recognized cause. Inspect API limits and billing or contact support with the request ID.'))
    request_id = headers.get('x-request-id','')
    request_id = request_id if re.fullmatch(r'req_[A-Za-z0-9_-]{1,120}',request_id) else None
    try:
        delay = float(headers.get('retry-after',''))
        delay = delay if math.isfinite(delay) and 0 <= delay <= 86400 else None
    except (ValueError,TypeError):
        delay = None
    diagnostic = dict(http_status=429,category=category,error_code=code,error_type=kind,
        request_id=request_id,retry_after_seconds=delay,public_code=public_code,
        recorded_at=datetime.now(timezone.utc).isoformat())
    return diagnostic,message+' No automatic retry was made; the previous route is preserved.'
