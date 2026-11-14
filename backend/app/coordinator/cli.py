"""Run an internal A0 mission; /api/v1 stays unchanged."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from app.agents.registry import WorkerRegistry
from app.coordinator.agent import MissionAgent
from app.coordinator.contracts import AgentLimits, MissionRequest
from app.coordinator.profiles import load_profile, read_local
from app.coordinator.providers import OpenAIProvider, ScriptedProvider
from app.coordinator.tools import ToolBox


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--profile',type=Path,help='Trusted local source bindings; relative inputs resolve beside this file')
    parser.add_argument('--provider',choices=['deterministic','scripted','openai'],default='deterministic')
    parser.add_argument('--script',type=Path,help='Offline proposal sequence; not a live LLM')
    parser.add_argument('--model',default=os.environ.get('A_STELLAR_A0_MODEL'))
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[3]/'data/processed/a0')
    parser.add_argument('--max-tool-calls',type=int,default=8)
    parser.add_argument('--max-replans',type=int,default=2)
    parser.add_argument('--deadline-s',type=float,default=120.0)
    args=parser.parse_args()
    if args.provider=='scripted' and args.script is None:
        parser.error('--provider scripted requires --script.')
    if args.provider!='scripted' and args.script is not None:
        parser.error('--script is only accepted with --provider scripted.')
    try:
        request=MissionRequest.model_validate_json(read_local(args.request,1_000_000))
        toolbox=load_profile(args.profile) if args.profile else ToolBox(WorkerRegistry(),request.context)
        provider=None
        if args.provider=='scripted':
            proposals=json.loads(read_local(args.script,1_000_000))
            if not isinstance(proposals,list) or len(proposals)>8:
                raise ValueError('Script must be a bounded proposal list.')
            provider=ScriptedProvider(proposals)
        elif args.provider=='openai':
            provider=OpenAIProvider(args.model)
        limits=AgentLimits(max_tool_calls=args.max_tool_calls,max_replans=args.max_replans,mission_timeout_s=args.deadline_s)
        report=asyncio.run(MissionAgent(toolbox,provider,limits).run(request,args.output_dir))
        print(json.dumps({'status':report.status,'provider':report.requested_provider,'fallback_used':report.fallback_used,
                          'route_status':report.route_status,'tool_calls':report.tool_calls,'model_calls':report.model_calls,
                          'decision_calls':report.decision_calls,'replans':report.replans,
                          'evidence':[e.model_dump() for e in report.evidence],
                          'unmet_requirements':report.unmet_requirements,
                          'report_ref':str(args.output_dir.resolve()/report.run_id/'report.json')},indent=2))
    except (OSError,ValueError,KeyError,ImportError) as error:
        parser.exit(1,f'A0 input/configuration error ({type(error).__name__}); check local paths, schemas, dependencies and profile scope.\n')


if __name__=='__main__':
    main()
