#!/usr/bin/env python3
"""Inspect A0 configuration and recorded errors; optional access check uses GET only."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def diagnose(settings, *, check_access=False, transport=None):
    from app.coordinator.metered import MeteredProvider
    report=dict(mode='agentic' if settings.enabled else 'deterministic',model=settings.model,
        credential_present=bool(settings.api_key),generation_requests=0,
        last_provider_error=MeteredProvider(settings,settings.usage_root).last_failure())
    if not check_access:
        return report
    if not settings.api_key:
        report['access_check']={'status':'missing_credentials'}
        return report
    import httpx
    from app.coordinator.provider_errors import describe_429
    try:
        with httpx.Client(transport=transport,timeout=15,follow_redirects=False) as client:
            response=client.get('https://api.openai.com/v1/models',headers={'Authorization':'Bearer '+settings.api_key})
        access=dict(http_status=response.status_code)
        try: body=response.json()
        except ValueError: body=None
        if response.status_code==200 and isinstance(body,dict) and isinstance(body.get('data'),list):
            access['configured_model_listed']=any(isinstance(row,dict) and row.get('id')==settings.model for row in body['data'])
        elif response.status_code==429:
            access['provider_error']=describe_429(body,response.headers)[0]
        report['access_check']=access
        report['access_check_scope']='Model listing does not verify generation access, account balance or request/token limits.'
    except httpx.HTTPError as error:
        report['access_check']={'status':'network_error','error_type':type(error).__name__}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,help='Private runtime file; contents are never printed')
    parser.add_argument('--check-access',action='store_true',help='Make one GET /v1/models; never call Responses or generate tokens')
    args=parser.parse_args()
    if args.env_file:
        os.environ['A_STELLAR_ENV_FILE']=str(args.env_file.expanduser().resolve())
    from app.coordinator.settings import environment,AgentSettings
    try:
        report=diagnose(AgentSettings.read(environment()),check_access=args.check_access)
    except (OSError,ValueError):
        parser.exit(1,'Local configuration or recorded diagnostics are invalid. Private input values were not logged.\n')
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
