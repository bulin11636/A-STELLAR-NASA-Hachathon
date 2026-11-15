import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RouteAssessment from '../src/components/RouteAssessment.tsx';
import SpecialistTrace from '../src/components/SpecialistTrace.tsx';
import { decodeStoredRoute } from '../src/services/metadata.ts';
import { fixture } from './helpers/p0.ts';
import type { RouteAssessment as Assessment, SpecialistTrace as Trace } from '../src/types/routeMetadata.ts';

const assessment: Assessment={time:{mode:'walking',model:'constant_projected_speed_v1',speed_m_s:1,travel_min:10,stop_min:6,total_min:16,assumptions:['Explicit synthetic speed.']},radiation_duration_min:16,radiation_duration_basis:'route_estimate',dose_estimate_usv:null,dose_uncertainty_usv:null,radiation_constraint_status:'unknown',required_unassessed:['A3'],required_failed:[],mission_profile:null,hard_gate_status:'unassessed',risk_score:null,assessment_confidence:null,risk_factors:[],limitations:['Combined risk is unknown.']};
test('walking estimates expose assumptions and unassessed required constraints',()=>{
 const html=renderToStaticMarkup(createElement(RouteAssessment,{assessment}));
 for(const text of ['1 m/s','total: 16.0 min','Explicit synthetic speed.','Required analyses remain unassessed','Not assessed','unknown'])assert(html.includes(text),text);
 const unknown=renderToStaticMarkup(createElement(RouteAssessment,{assessment:{...assessment,time:null}}));
 assert(unknown.includes('Supply an assumed walking speed'));
});
test('specialist display separates selection, execution and evidence application',()=>{
 const trace:Trace={agent_id:'A3',public_name:'Radiation Exposure and Mission Dose Assessment Agent',configured:false,selected:true,required:true,selection_source:'user_requirement',selection_reason:'Required by the user.',execution_state:'unavailable',data_kind:'unavailable',result_status:null,application:'none',constraint_status:'unknown',limitations:['No compatible scenario.'],dataset_ids:[],artifact_id:null};
 const html=renderToStaticMarkup(createElement(SpecialistTrace,{traces:[trace]}));
 for(const text of [trace.public_name,'Required','Selected','execution: unavailable','No evidence applied',trace.selection_reason])assert(html.includes(text),text);
});
test('stored time must match the walking assessment',()=>{
 const stored=structuredClone(fixture);stored.metadata.assessment=assessment;stored.result.metrics.distance_m=600;stored.metadata.request.waypoints=[stored.result.route[3],stored.result.route[7]];stored.metadata.request.mission={mode:'walking',speed_m_s:1,stop_minutes_per_waypoint:3,exposure_duration_min:null,radiation_budget_usv:null,required_analyses:[]};stored.result.metrics.estimated_time_min=16;
 assert(decodeStoredRoute(stored,stored.result.route_id));
 stored.result.metrics.estimated_time_min=15;
 assert.throws(()=>decodeStoredRoute(stored,stored.result.route_id),/Walking assessment/);
});
