#!/usr/bin/env python3
"""Start this checkout's computed backend with explicit portable runtime paths."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def parser():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dataset-dir',type=Path,required=True)
    cli.add_argument('--profile',type=Path,default=ROOT/'data/samples/a0-planning-profile.example.json')
    cli.add_argument('--env-file',type=Path)
    cli.add_argument('--state-dir',type=Path,default=ROOT/'data/processed')
    cli.add_argument('--mode',choices=['agentic','deterministic'],default='agentic')
    cli.add_argument('--host',default='127.0.0.1')
    cli.add_argument('--port',type=int,default=8000)
    cli.add_argument('--check',action='store_true',help='Validate local configuration without starting a server or contacting the provider')
    return cli


def configuration(args):
    dataset=args.dataset_dir.expanduser().resolve()
    profile=args.profile.expanduser().resolve()
    state=args.state_dir.expanduser().resolve()
    if not dataset.is_dir() or not profile.is_file() or not 1 <= args.port <= 65535:
        raise ValueError('Invalid dataset, profile or port')
    env=dict(os.environ)
    if args.env_file:
        runtime=args.env_file.expanduser().resolve()
        if not runtime.is_file(): raise ValueError('Missing explicit runtime file')
        env['A_STELLAR_ENV_FILE']=str(runtime)
    elif (ROOT/'.env').is_file():
        env['A_STELLAR_ENV_FILE']=str(ROOT/'.env')
    env.update(A_STELLAR_ROUTING_MODE='computed',A_STELLAR_A0_MODE=args.mode,
        A_STELLAR_DATASET_DIR=str(dataset),A_STELLAR_PLANNING_PROFILE=str(profile),
        A_STELLAR_ROUTE_STORE=str(state/'routes'),A_STELLAR_A0_USAGE_STORE=str(state/'a0-model-usage'),
        PYTHONPATH=str(ROOT/'backend'))
    # This launcher serves the API; a stale production-UI setting from another
    # terminal must not bind this checkout to another repository's build.
    env['A_STELLAR_STATIC_DIR']=''
    return env


def check_configuration(env):
    from app.coordinator.settings import environment,AgentSettings
    from app.planning.service import PlanningService
    values=environment(env)
    settings=AgentSettings.read(values)
    planning=PlanningService('computed',values['A_STELLAR_PLANNING_PROFILE'],values['A_STELLAR_ROUTE_STORE'],dataset_root=values['A_STELLAR_DATASET_DIR'])
    storage=True
    for directory in [planning.store.root,settings.usage_root]:
        try:
            directory.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b'readiness'); probe.flush(); os.fsync(probe.fileno())
        except OSError:
            storage=False
    checks=dict(planning=planning.ready,storage=storage,model_credentials=not settings.enabled or bool(settings.api_key))
    return dict(ready=all(checks.values()),checks=checks,mode='agentic' if settings.enabled else 'deterministic',
        provider_access_verified=False)


def main():
    cli=parser(); args=cli.parse_args()
    try:
        env=configuration(args)
        result=check_configuration(env)
    except (OSError,ValueError):
        cli.exit(1,'Invalid local runtime configuration. Check input paths, env assignments and model settings; private values were not logged.\n')
    if args.check:
        print(json.dumps(result,indent=2))
    if not result['ready']:
        cli.exit(1,'Local readiness failed. Check the planning profile, source, state-directory permissions and selected mode.\n')
    if args.check:
        return
    print(f'API: http://{args.host}:{args.port}/api/v1/health',flush=True)
    print(f'API docs: http://{args.host}:{args.port}/docs',flush=True)
    print('Development UI: start frontend separately and open the URL printed by Vite.',flush=True)
    print('Local readiness does not verify provider access. Planning/chat can call the provider in agentic mode.',flush=True)
    command=[sys.executable,'-m','uvicorn','app.main:app','--host',args.host,'--port',str(args.port)]
    try:
        raise SystemExit(subprocess.run(command,cwd=ROOT/'backend',env=env,check=False).returncode)
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__=='__main__':
    main()
