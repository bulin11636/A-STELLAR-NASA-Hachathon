import assert from 'node:assert/strict';
import test from 'node:test';
import {coverageError,planningBounds} from '../src/map/planningCoverage.ts';
import {COORDINATE_SYSTEM,type PlanningRegion,type PlanRouteRequest} from '../src/types/api.ts';
const region:PlanningRegion={id:'jezero',coordinate_system:COORDINATE_SYSTEM,routing_mode:'computed',routing_available:true,planning:{
  roi_id:'test',bounds:{west:77.42,east:77.47,south:18.42,north:18.47},source_bounds:{west:76.997793,east:78.582208,south:17.580857,north:19.28985},dynamic_windowing:true,resolution_m:[20,20],example_request:null}};
const request:PlanRouteRequest={region_id:'jezero',coordinate_system:COORDINATE_SYSTEM,mode:'shortest',start:{longitude:77.432446,latitude:17.556871},goal:{longitude:77.58186,latitude:17.765791}};
test('the reported southern start is rejected while regional stops outside the small example are accepted',()=>{
  assert.match(coverageError(region,request)!,/^Start/);
  const supported={...request,start:{...request.start,latitude:17.65}};
  assert.equal(coverageError(region,supported),null);
  assert.match(coverageError(region,{...supported,waypoints:[request.start]})!,/^Waypoint 1/);
  assert.match(coverageError(region,{...supported,goal:request.start})!,/^Goal/);
  assert.deepEqual(planningBounds(region),region.planning!.source_bounds);
});
test('static windows enforce their actual bounds and unknown coverage is never guessed',()=>{
  const staticRegion={...region,planning:{...region.planning!,dynamic_windowing:false}};
  assert.match(coverageError(staticRegion,{...request,start:{longitude:77.44,latitude:18.44}})!,/^Goal/);
  assert.equal(coverageError(null,request),null);
});
