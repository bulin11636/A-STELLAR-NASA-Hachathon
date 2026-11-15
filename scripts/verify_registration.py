#!/usr/bin/env python3
"""Verify independent map feature controls against a locally computed route; no model calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=ROOT/'data/samples/a0-planning-profile.example.json')
    parser.add_argument('--request-file',type=Path,help='PlanRouteRequest JSON; omit to report missing route applicability')
    parser.add_argument('--controls',type=Path,help='Independent feature-control JSON with hashed local measurement and WMTS assets')
    parser.add_argument('--output-root',type=Path,default=ROOT/'data/processed/registration-verification')
    args=parser.parse_args()
    from app.contracts.api import PlanRouteRequest
    from app.planning.service import PlanningService
    from app.planning.registration import registration_for_route, validate_controls
    run=args.output_root.resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);run.mkdir(parents=True)
    planning=PlanningService('computed',args.profile,run/'routes',dataset_root=args.dataset_dir)
    if not planning.ready: raise RuntimeError('The configured source/profile is unavailable.')
    route=[]
    if args.request_file:
        request=PlanRouteRequest.model_validate_json(args.request_file.read_text())
        route=planning.plan(request).route
    report=(validate_controls(planning.grid,args.controls,route) if args.controls else registration_for_route(planning.grid,route,dataset_root=args.dataset_dir))
    summary=dict(live_model_calls=0,registration=report.model_dump(mode='json'))
    (run/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(**summary,run_path=str(run)),indent=2))
    return 0 if report.map_alignment=='verified' else 2


if __name__=='__main__':
    raise SystemExit(main())
