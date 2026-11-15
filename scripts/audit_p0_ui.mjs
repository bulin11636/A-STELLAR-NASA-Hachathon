// P0 production UI/API/real DEM acceptance. All provider responses are mocked.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { closeSync, mkdirSync, openSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const { chromium }=createRequire(root+'/frontend/package.json')('playwright');
const { values }=parseArgs({options:{'dataset-dir':{type:'string'},python:{type:'string',default:'python'},'output-root':{type:'string'}}});
if(!values['dataset-dir'])throw new Error('Pass --dataset-dir with the local CTX dataset root.');
const run=resolve(values['output-root']??root+'/data/processed/p0-ui-audit','run-'+new Date().toISOString().replaceAll(/[:.]/g,'-'));
mkdirSync(run,{recursive:true});
const probe=createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');
const port=probe.address().port;await new Promise(done=>probe.close(done));
const base=`http://127.0.0.1:${port}`;const log=openSync(run+'/server.log','w');
let server, browser, page, startupError;
const summary={status:'running',live_model_calls:0,run_path:run,checks:[]};
function start(){
 server=spawn(values.python,[root+'/scripts/ui_test_server.py','--dataset-dir',resolve(values['dataset-dir']),'--run-dir',run,'--port',String(port)],
  {cwd:root,env:{...process.env,A_STELLAR_A0_MODE:'deterministic'},stdio:['ignore',log,log]});
 startupError=null;server.on('error',e=>{startupError=e;});
}
async function ready(){
 for(let i=0;i<150;i++){
  try{if((await fetch(base+'/api/v1/ready')).ok)return;}catch{}
  if(startupError||server.exitCode!==null)break;
  await new Promise(done=>setTimeout(done,100));
 }
 throw new Error('Acceptance backend did not start; inspect server.log.');
}
async function open(){
 const current=await browser.newPage({viewport:{width:1440,height:1000}});
 current.setDefaultTimeout(20000);
 await current.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await current.goto(base);await current.getByRole('button',{name:'Load in-coverage example endpoints',exact:true}).waitFor();return current;
}
async function endpoints(){await page.getByRole('button',{name:'Load in-coverage example endpoints',exact:true}).click();}
async function plan(advanced=false){
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/routes/plan')&&r.request().method()==='POST');
 await page.getByRole('button',{name:advanced?'Plan and Ask A0':'Plan Route',exact:true}).click();
 const response=await pending;
 return {http_status:response.status(),body:await response.json(),key:response.request().headers()['idempotency-key']};
}
async function control(next,target='any'){
 const response=await fetch(base+'/__test/provider',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({next,target})});assert(response.ok);
}
async function chat(message,button='Send to A0'){
 if(message!==null)await page.getByLabel('Message A0',{exact:true}).fill(message);
 const pending=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');
 await page.getByRole('button',{name:button,exact:true}).click();
 const response=await pending;return {status:response.status(),body:await response.json(),request:response.request().postDataJSON(),headers:response.request().headers()};
}
const count=async()=> (await (await fetch(base+'/api/v1/a0/status')).json()).budget.attempts;
try{
 start();await ready();browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 summary.stage='new_plans_without_reload';page=await open();await endpoints();
 const first=await plan();assert.equal(first.http_status,200);await page.locator('.route-preview polyline').waitFor();
 await page.getByRole('button',{name:'Load crater-scale example endpoints',exact:true}).click();
 assert(await page.locator('.route-preview polyline').isVisible(),'Draft edits must preserve the last route.');
 const regional=await plan();assert.equal(regional.http_status,200,JSON.stringify(regional.body));assert.notEqual(first.key,regional.key);
 assert(regional.body.metrics.distance_m>40000);await page.locator('.route-preview polyline').waitFor();
 assert.equal(await page.getByRole('region',{name:'Required waypoints',exact:true}).count(),0);
 await page.locator('.route-preview').screenshot({path:run+'/regional-route.png'});
 summary.checks.push('different_plan_keys_without_reload','preserved_successful_result','quick_hides_advanced_controls','regional_route');await page.close();

 summary.stage='advanced_plan_then_chat';page=await open();await endpoints();
 await page.getByRole('tab',{name:'Advanced',exact:true}).click();
 const advanced=page.getByRole('button',{name:'Plan and Ask A0',exact:true});assert(await advanced.isDisabled());
 const {stops}=await (await fetch(base+'/__test/scenario')).json();
 for(const point of stops.slice(0,2)){
  await page.getByLabel('Waypoint longitude',{exact:true}).fill(String(point.longitude));
  await page.getByLabel('Waypoint latitude',{exact:true}).fill(String(point.latitude));await page.getByRole('button',{name:'Add waypoint',exact:true}).click();
 }
 await page.getByRole('button',{name:'Move W2 up',exact:true}).click();
 await page.getByLabel('Walking speed (m/s)',{exact:true}).fill('1');
 await page.getByLabel('Dwell per intermediate visit (min)',{exact:true}).fill('3');
 await page.getByRole('checkbox',{name:'Thermal Environment and Exposure Context',exact:true}).check();
 await page.getByLabel('Additional requirements',{exact:true}).fill('Explain the required stop order and terrain limitations.');
 await page.getByRole('checkbox',{name:'terrain',exact:true}).uncheck();assert(await advanced.isDisabled());
 await page.getByRole('checkbox',{name:'terrain',exact:true}).check();
 await page.getByRole('checkbox',{name:'Allow A0 to propose a supported route revision',exact:true}).uncheck();
 const messages=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/chat'))messages.push(r.postDataJSON());});
 const response=await plan(true);assert.equal(response.http_status,200);
 await page.getByRole('region',{name:'Advanced A0 response',exact:true}).waitFor();
 assert.equal(response.body.metrics.estimated_time_min,response.body.metrics.distance_m/60+6);
 const walking=await (await fetch(base+'/api/v1/routes/'+response.body.route_id)).json();
 assert.deepEqual(walking.metadata.assessment.required_unassessed,['A2']);
 assert(walking.metadata.specialist_trace.find(t=>t.agent_id==='A4').selected);
 assert(walking.metadata.specialist_trace.find(t=>t.agent_id==='A1').required);
 assert(await page.getByRole('region',{name:'Walking time and exposure assessment',exact:true}).isVisible());
 summary.checks.push('walking_time_with_explicit_speed_and_dwell','required_unavailable_analysis_is_provisional','auditable_specialist_selection');
 assert.equal(messages.length,1);assert.equal(messages[0].message,'Explain the required stop order and terrain limitations.');
 assert.deepEqual(messages[0].advanced_context.required_waypoints,[stops[1],stops[0]]);assert.equal(messages[0].advanced_context.allow_supported_revision,false);
 assert(new URL(page.url()).searchParams.get('route')===response.body.route_id);
 await page.getByRole('button',{name:'Focus W1',exact:true}).click();
 await page.getByRole('button',{name:'Zoom in DEM preview',exact:true}).click();
 await page.locator('.route-preview').screenshot({path:run+'/advanced-stops.png'});
 // A draft objective must not rewrite the parent context used for discussion.
 await page.locator('.route-planner select').selectOption('safest');
 const explanation=await chat('Why this terrain-only route?');assert.equal(explanation.status,200,JSON.stringify(explanation.body));
 assert.equal(explanation.request.advanced_context.route_objective,'shortest');assert.equal(explanation.body.result,null);
 await page.getByRole('checkbox',{name:'Allow A0 to propose a supported route revision',exact:true}).check();
 const revision=await chat('Reverse all waypoint visits, keeping start and goal.');assert.equal(revision.status,200,JSON.stringify(revision.body));
 assert.deepEqual(revision.body.metadata.request.waypoints,[stops[0],stops[1]]);
 assert.equal(revision.body.metadata.request.mission.speed_m_s,1);
 assert.equal(revision.body.result.metrics.estimated_time_min,revision.body.result.metrics.distance_m/60+6);
 await page.waitForURL('**route='+revision.body.result.route_id);
 await page.reload();await page.locator('.route-preview polyline').waitFor();
 await page.locator('.chat-transcript').getByText('Reverse all waypoint visits',{exact:false}).waitFor();
 summary.checks.push('advanced_control_validation','ordered_waypoint_creation_reordering','base_plan_metadata_before_chat','bounded_requirements_and_context',
  'explanation_only_permission','chat_context_from_displayed_parent','valid_revision_applied','route_history_reload','nearby_stop_focus_zoom');await page.close();

 summary.stage='plan_manual_retry';page=await open();await endpoints();await control('rate_limit_once','plan');
 const rejected=await plan();assert.equal(rejected.http_status,503);
 const retry=page.getByRole('button',{name:'Retry planning request',exact:true});await retry.waitFor();
 const beforeRetry=await count();await page.waitForTimeout(300);assert.equal(await count(),beforeRetry);
 const again=page.waitForResponse(r=>r.url().endsWith('/api/v1/routes/plan')&&r.request().method()==='POST');await retry.click();
 const recovered=await again;assert.equal(recovered.status(),200);assert.equal(recovered.request().headers()['idempotency-key'],rejected.key);
 assert.equal(recovered.request().headers()['x-a-stellar-retry-attempt'],'1');await page.locator('.route-preview polyline').waitFor();
 summary.checks.push('real_backend_plan_failure_status','explicit_versioned_plan_retry','no_automatic_plan_retry');await page.close();

 summary.stage='chat_manual_retry';page=await open();await endpoints();assert.equal((await plan()).http_status,200);await page.locator('.route-preview polyline').waitFor();
 await control('rate_limit_once','chat');const chatFailure=await chat('Explain this route.');assert.equal(chatFailure.status,503);
 const chatRetry=page.getByRole('button',{name:'Retry chat request',exact:true});await chatRetry.waitFor();
 assert(await page.locator('.route-preview polyline').isVisible());
 const chatRecovered=await chat(null,'Retry chat request');assert.equal(chatRecovered.status,200,JSON.stringify(chatRecovered.body));
 assert.deepEqual(chatRecovered.request,chatFailure.request);assert.equal(chatRecovered.headers['x-a-stellar-retry-attempt'],'1');
 summary.checks.push('real_backend_chat_failure_status','explicit_versioned_chat_retry','chat_failure_preserves_base');await page.close();

 summary.stage='recover_saved_plan_response';page=await open();await endpoints();
 const planCallsBefore=await count();let savedPlan,dropPlan=true;
 await page.route('**/api/v1/routes/plan',async route=>{
  if(dropPlan){dropPlan=false;const response=await route.fetch();assert.equal(response.status(),200);savedPlan=await response.json();return route.abort();}
  return route.continue();
 });
 await page.getByRole('button',{name:'Plan Route',exact:true}).click();
 const recoverPlan=page.getByRole('button',{name:'Recover planning result',exact:true});await recoverPlan.waitFor();
 assert.equal(await count(),planCallsBefore+2);
 const planReplay=page.waitForResponse(r=>r.url().endsWith('/api/v1/routes/plan')&&r.request().method()==='POST');await recoverPlan.click();
 const replayedPlan=await planReplay;assert.equal(replayedPlan.status(),200);assert.equal(replayedPlan.request().headers()['x-a-stellar-retry-attempt'],'1');
 assert.equal((await replayedPlan.json()).route_id,savedPlan.route_id);await page.locator('.route-preview polyline').waitFor();
 assert.equal(await count(),planCallsBefore+2);summary.checks.push('explicit_plan_result_recovery_without_generation');await page.close();

 summary.stage='recover_saved_chat_response';page=await open();await endpoints();assert.equal((await plan()).http_status,200);await page.locator('.route-preview polyline').waitFor();
 const chatCallsBefore=await count();let savedChat,dropChat=true;
 await page.route('**/api/v1/routes/*/chat',async route=>{
  if(route.request().method()==='POST'&&dropChat){dropChat=false;const response=await route.fetch();assert.equal(response.status(),200);savedChat=await response.json();return route.abort();}
  return route.continue();
 });
 await page.getByLabel('Message A0',{exact:true}).fill('Explain this route.');await page.getByRole('button',{name:'Send to A0',exact:true}).click();
 const recoverChat=page.getByRole('button',{name:'Recover chat result',exact:true});await recoverChat.waitFor();
 assert.equal(await count(),chatCallsBefore+2);
 const chatReplay=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');await recoverChat.click();
 const replayedChat=await chatReplay;assert.equal(replayedChat.status(),200);assert.equal(replayedChat.request().headers()['x-a-stellar-retry-attempt'],'1');
 assert.equal((await replayedChat.json()).message_id,savedChat.message_id);assert.equal(await count(),chatCallsBefore+2);
 summary.checks.push('explicit_chat_result_recovery_without_generation');await page.close();

 summary.stage='unknown_and_backend_restart';page=await open();await endpoints();assert.equal((await plan()).http_status,200);await page.locator('.route-preview polyline').waitFor();
 await page.locator('.route-planner select').selectOption('safest');await control('timeout_once','plan');
 const timed=await plan();assert.equal(timed.http_status,503);
 await page.getByRole('status').filter({hasText:'Planning request: unknown.'}).waitFor();
 assert.equal(await page.getByRole('button',{name:/^Retry planning/}).count(),0);assert(await page.locator('.route-preview polyline').isVisible());
 const attemptsBeforeRestart=await count();
 server.kill('SIGTERM');await once(server,'exit');start();await ready();
 await page.reload();await page.locator('.route-preview polyline').waitFor();
 await page.getByRole('status').filter({hasText:'Planning request: unknown.'}).waitFor();
 assert.equal(await count(),attemptsBeforeRestart);assert.equal(await page.getByRole('button',{name:/^Retry planning/}).count(),0);
 await page.screenshot({path:run+'/unknown-recovered.png',fullPage:true});
 summary.checks.push('unknown_blocks_execution','unknown_and_last_route_survive_reload_restart','no_generation_on_restore');await page.close();

 summary.stage='running_request';page=await open();await endpoints();await control('hold_once','plan');
 const sent=page.waitForRequest(r=>r.url().endsWith('/api/v1/routes/plan')&&r.method()==='POST');
 const completed=page.waitForResponse(r=>r.url().endsWith('/api/v1/routes/plan')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Plan Route',exact:true}).click();const running=await sent;
 const key=running.headers()['idempotency-key'];let observed=false;
 for(let i=0;i<30;i++){
  const status=await fetch(base+'/api/v1/routes/requests/'+key);
  if(status.ok&&(await status.json()).state==='running'){observed=true;break;}
  await new Promise(done=>setTimeout(done,100));
 }
 assert(observed);assert(await page.getByRole('button',{name:'Working…',exact:true}).isDisabled());
 await control('normal');assert.equal((await completed).status(),200);await page.locator('.route-preview polyline').waitFor();
 await page.getByText('Computed geometry is withheld from the map: NASA map/wire/DEM registration is unverified.',{exact:true}).waitFor();
 summary.checks.push('running_state_and_single_flight','NASA_overlay_still_gated');
 summary.status='passed';summary.stage='complete';summary.regional_distance_m=regional.body.metrics.distance_m;
}catch(error){summary.status='failed';summary.error=String(error);if(page&&!page.isClosed())await page.screenshot({path:run+'/failure.png',fullPage:true}).catch(()=>{});}
finally{
 await browser?.close();if(server?.pid&&server.exitCode===null){server.kill('SIGTERM');await once(server,'exit');}
 closeSync(log);writeFileSync(run+'/summary.json',JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify(summary,null,2));
}
if(summary.status!=='passed')process.exitCode=1;
