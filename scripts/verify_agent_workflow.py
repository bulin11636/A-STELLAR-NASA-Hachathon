#!/usr/bin/env python3
"""Verify expanded-ROI planning and route chat. Live API calls require --live-model."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    import httpx
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.api.errors import ApiProblem
    from app.contracts.api import PlanRouteRequest, COORDINATE_SYSTEM
    from app.coordinator.settings import AgentSettings, environment
    from app.coordinator.metered import MeteredProvider
    from app.coordinator.route_agent import RouteAgent
    from app.planning.service import PlanningService
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir',type=Path,default=Path.home()/'nasa/project/dataset')
    parser.add_argument('--profile',type=Path,default=ROOT/'data/samples/a0-planning-profile.example.json')
    parser.add_argument('--output-root',type=Path,default=ROOT/'data/processed/a0-workflow')
    parser.add_argument('--live-model',action='store_true',help='Make at most four real model requests using backend credentials and the shared persistent budget; never retry automatically')
    args=parser.parse_args()
    run=args.output_root.resolve()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(parents=True)
    def save(name,data): (run/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
    summary={'mode':'live' if args.live_model else 'mocked-provider','status':'running','run_path':str(run),'live_model_calls':0}
    provider=None; before=0
    try:
        planning=PlanningService('computed',args.profile,run/'routes',dataset_root=args.dataset_dir)
        if not planning.ready: raise RuntimeError('The configured real DEM/profile is unavailable.')
        g=planning.grid
        start=g.wire(*g.center((20,20))); goal=g.wire(*g.center((200,200)))
        stops=[g.wire(*g.center(cell)) for cell in [(60,60),(100,100),(140,140)]]
        request=PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,start=start,goal=goal,mode='shortest')
        planning.prepare_grid(request.model_copy(update={'waypoints':stops}))
        preflight=planning.plan(request)
        preflight_record=planning.store.get(preflight.route_id)
        assert preflight_record.metadata.grid.width>128 and preflight_record.metadata.grid.height>128
        save('request.json',request.model_dump(mode='json'))
        settings=AgentSettings.read(environment())
        settings.enabled=True
        if args.live_model:
            if not settings.api_key: raise RuntimeError('A backend API key is required for --live-model.')
            provider=MeteredProvider(settings,settings.usage_root)
        else:
            settings.api_key='synthetic-test-key'
            def handler(req):
                data=json.loads(req.content)
                message=json.loads(data['input'][1]['content'])['message']
                answer=message.startswith('Why')
                revision=message.startswith('Add')
                proposal={'action':'answer' if answer else 'replan','message':'Mock provider: inspect the persisted host rationale.','mode':None,
                    'waypoints':[p.model_dump() for p in (reversed(stops) if message.startswith('Reverse') else stops)]
                        if revision or message.startswith('Reverse') else None,'citations':['A1']}
                return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','name':'propose_route_action','arguments':json.dumps(proposal)}],
                    'usage':{'input_tokens':500,'output_tokens':100,'output_tokens_details':{'reasoning_tokens':40}}})
            provider=MeteredProvider(settings,run/'mock-usage',httpx.MockTransport(handler))
        before=provider.totals()['attempts']
        # Keep the shared ledger and any stricter configured cap. Never permit
        # this acceptance invocation to reserve more than four new requests.
        settings.max_calls=min(settings.max_calls,before+4)
        agent=RouteAgent(settings,planning,provider)
        with TestClient(create_app(planning=planning,route_agent=agent)) as client:
            plan_body=request.model_dump(mode='json')
            plan_headers={'Idempotency-Key':uuid4().hex}
            response=client.post('/api/v1/routes/plan',json=plan_body,headers=plan_headers)
            if response.status_code!=200: raise ApiProblem(response.status_code,response.json()['error']['code'],response.json()['error']['message'])
            result=response.json(); route_id=result['route_id']
            assert client.post('/api/v1/routes/plan',json=plan_body,headers=plan_headers).json()==result
            stored=client.get('/api/v1/routes/'+route_id)
            assert stored.status_code==200
            save('planned.json',stored.json())
            question=client.post('/api/v1/routes/'+route_id+'/chat',json={'message':'Why was this route selected? Explain its terrain-only limits.','request_id':uuid4().hex})
            if question.status_code!=200: raise ApiProblem(question.status_code,question.json()['error']['code'],question.json()['error']['message'])
            assert question.json()['result'] is None
            save('question.json',question.json())
            coordinates='; '.join(f'{point.longitude},{point.latitude}' for point in stops)
            message=f'Add these three exact required waypoints in the supplied order: {coordinates}. Retain the start, goal and shortest mode.'
            revision_body={'message':message,'request_id':uuid4().hex}
            revision=client.post('/api/v1/routes/'+route_id+'/chat',json=revision_body)
            if revision.status_code!=200: raise ApiProblem(revision.status_code,revision.json()['error']['code'],revision.json()['error']['message'])
            body=revision.json()
            if body['result'] is None: raise RuntimeError('A0 requested clarification rather than creating the explicit waypoint revision.')
            assert body['metadata']['parent_route_id']==route_id
            assert body['metadata']['request']['waypoints']==[point.model_dump() for point in stops]
            assert client.post('/api/v1/routes/'+route_id+'/chat',json=revision_body).json()==body
            save('revision.json',body)
            child=body['result']['route_id']
            reorder_body={'message':'Reverse all three required waypoint visits. Keep the original start, goal and shortest mode unchanged.','request_id':uuid4().hex}
            reordered=client.post('/api/v1/routes/'+child+'/chat',json=reorder_body)
            if reordered.status_code!=200: raise ApiProblem(reordered.status_code,reordered.json()['error']['code'],reordered.json()['error']['message'])
            ordered=reordered.json()
            if ordered['result'] is None: raise RuntimeError('A0 did not create the explicit waypoint-order revision.')
            assert ordered['metadata']['parent_route_id']==child
            assert ordered['metadata']['request']['waypoints']==[point.model_dump() for point in reversed(stops)]
            assert client.post('/api/v1/routes/'+child+'/chat',json=reorder_body).json()==ordered
            save('reordered.json',ordered)
            final=ordered['result']['route_id']
        fresh=RouteAgent(settings,planning,provider)
        with TestClient(create_app(planning=planning,route_agent=fresh)) as client:
            assert len(client.get('/api/v1/routes/'+final+'/chat').json()['messages'])==3
            assert client.get('/api/v1/routes/'+final).status_code==200
        assert provider.totals()['attempts']-before==4
        summary.update(status='passed',route_id=route_id,revision_id=child,reordered_route_id=final,
            initial_window=[g.metadata.width,g.metadata.height],expanded_window=[preflight_record.metadata.grid.width,preflight_record.metadata.grid.height],
            usage=provider.totals(),checks=['dynamic_crop_outside_initial_window','a0_before_astar','grounded_rationale',
                'question_without_route_change','explicit_three_waypoint_addition','reverse_three_visits',
                'idempotent_plan_and_revision_replay','fresh_app_history_and_route_retrieval','four_provider_requests_only'])
    except ApiProblem as error:
        summary.update(status='failed',error_code=error.code,message=error.message)
    except Exception as error:
        # No private provider exceptions/credentials appear in the report.
        summary.update(status='failed',error_type=type(error).__name__,message=str(error) if isinstance(error,(AssertionError,RuntimeError)) else 'Local verification failed; inspect offline checks.')
    finally:
        if provider is not None:
            total=provider.totals()
            summary['request_attempts_this_run']=total['attempts']-before
            summary['live_model_calls']=total['attempts']-before if args.live_model else 0
            summary['usage']=total
        save('summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if summary['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
