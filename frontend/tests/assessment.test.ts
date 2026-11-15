import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RouteAssessment from '../src/components/RouteAssessment.tsx';
import SpecialistTrace from '../src/components/SpecialistTrace.tsx';
import { decodeStoredRoute } from '../src/services/metadata.ts';
import { fixture } from './helpers/p0.ts';
import type { RouteAssessment as Assessment, SpecialistTrace as Trace } from '../src/types/routeMetadata.ts';

const assessment: Assessment={schema_version:"2",formula_version:"relative-terrain-scenario-v2",score_scale:"0..100",gate_reasons:[],time:{mode:'walking',model:'constant_projected_speed_v1',speed_m_s:1,travel_min:10,stop_min:6,total_min:16,assumptions:['Explicit synthetic speed.']},radiation_duration_min:16,radiation_duration_basis:'route_estimate',dose_estimate_usv:null,dose_uncertainty_usv:null,radiation_constraint_status:'unknown',required_unassessed:['A3'],required_failed:[],mission_profile:null,hard_gate_status:'unassessed',risk_score:null,assessment_confidence:null,risk_factors:[],limitations:['Combined risk is unknown.']};
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
test('assessment presents profile, gate, confidence, and factor provenance',()=>{
 const html=renderToStaticMarkup(createElement(RouteAssessment,{assessment:{...assessment,
   mission_profile:{schema_version:'1',profile_id:'safest',version:'mission-profile-v1',risk_weights:{A1:0.5,A2:0,A3:0.5,A4:0,A5:0,A6:0},confidence_weights:{A1:1,A2:0,A3:0,A4:0,A5:0,A6:0}},
   hard_gate_status:'blocked',risk_score:null,assessment_confidence:75,
   risk_factors:[{agent_id:'A1',kind:'risk',status:'assessed',risk_score:0.4,public_name:"Surface Traversability and Terrain Hazard Agent",model_version:null,evidence:null,component_reasons:{},confidence_contribution:50,risk_contribution:20,evidence_quality:{availability:1,route_coverage:1,temporal_applicability:0.5,validation_provenance:0.5},evidence_ids:['dem'],message:'Terrain evidence is available.'}]
 }}));
 assert.match(html,/Mission gate/);assert.match(html,/Blocked/);assert.match(html,/Assessment confidence/);assert.match(html,/75%/);assert.match(html,/Terrain evidence is available/);assert.match(html,/Profile weight: 50%/);
});
test('stored time must match the walking assessment',()=>{
 const stored=structuredClone(fixture);stored.metadata.assessment=assessment;stored.result.metrics.distance_m=600;stored.metadata.request.waypoints=[stored.result.route[3],stored.result.route[7]];stored.metadata.request.mission={mode:'walking',speed_m_s:1,stop_minutes_per_waypoint:3,exposure_duration_min:null,radiation_budget_usv:null,required_analyses:[]};stored.result.metrics.estimated_time_min=16;
 assert(decodeStoredRoute(stored,stored.result.route_id));
 stored.result.metrics.estimated_time_min=15;
 assert.throws(()=>decodeStoredRoute(stored,stored.result.route_id),/Walking assessment/);
});

test('P1 percentages and factor quality come directly from backend fixture fields',async()=>{
 const {readFileSync}=await import('node:fs');
 const record=JSON.parse(readFileSync(new URL('../../data/fixtures/p1/low-risk-low-confidence.json',import.meta.url),'utf8'));
 const html=renderToStaticMarkup(createElement(RouteAssessment,{assessment:record.metadata.assessment}));
 assert(html.includes('49.5%'));assert(!html.includes('4950%'));
 assert(html.includes('confidence contribution:'));assert(html.includes('time applicability: 0%'));
 assert(html.includes('Surface Traversability and Terrain Hazard Agent'));
 assert(!html.includes('evidence quality:'));
});
