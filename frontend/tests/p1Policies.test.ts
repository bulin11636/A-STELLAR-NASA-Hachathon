import assert from 'node:assert/strict';
import { readFileSync,readdirSync } from 'node:fs';
import { test } from 'node:test';
import { decodePlanningPolicies } from '../src/services/planningPolicies.ts';
import { decodeStoredRoute } from '../src/services/metadata.ts';
const folder=new URL('../../data/fixtures/p1/',import.meta.url);
const read=(name:string)=>JSON.parse(readFileSync(new URL(name,folder),'utf8'));

test('backend policy discovery is bounded and keeps weights in the backend',()=>{
 const policies=decodePlanningPolicies(read('policies.json'));
 assert.equal(policies.profiles.length,4);assert.equal(policies.resolutions.length,3);
 const invalid=structuredClone(policies);invalid.profiles[1]=invalid.profiles[0];
 assert.throws(()=>decodePlanningPolicies(invalid),/Incomplete/);
 assert.throws(()=>decodePlanningPolicies({...policies,score_scale:'0..1'}),/Unsupported/);
});
test('all shared P1 routes decode, including missing evidence and synthetic alignment',()=>{
 for(const name of readdirSync(folder).filter(n=>n.endsWith('.json')&&n!=='policies.json')){
  const body=read(name),record=decodeStoredRoute(body,body.result.route_id);
  const assessment=record.metadata.assessment!;
  assert.equal(assessment.score_scale,'0..100');assert.equal(assessment.risk_factors.length,6);
  assert.equal(assessment.risk_factors.find(f=>f.agent_id==='A5')?.status,'not_applicable');
  if(assessment.hard_gate_status!=='pass')assert.equal(assessment.risk_score,null);
  assert.notEqual(assessment.assessment_confidence,null);
 }
});
