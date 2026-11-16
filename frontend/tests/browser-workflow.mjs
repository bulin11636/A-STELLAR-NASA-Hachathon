// Real production UI/API/DEM integration; the fixture server mocks every model call.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, openSync, closeSync } from 'node:fs';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import assert from 'node:assert/strict';

const { values } = parseArgs({ options: { 'dataset-dir': { type: 'string' }, python: { type: 'string', default: 'python' },
  'output-root': { type: 'string' }, channel: { type:'string' } } });
if (!values['dataset-dir']) throw new Error('Pass --dataset-dir with the real local CTX dataset root.');
const root = fileURLToPath(new URL('../../',import.meta.url));
const run = resolve(values['output-root'] ?? root+'/data/processed/ui-verification','run-'+new Date().toISOString().replaceAll(/[:.]/g,'-'));
mkdirSync(run,{recursive:true});
const probe = createServer(); probe.listen(0,'127.0.0.1'); await once(probe,'listening');
const port = probe.address().port; await new Promise((done) => probe.close(done));
const base = `http://127.0.0.1:${port}`;
const log = openSync(run+'/server.log','w');
const backend = spawn(values.python,[root+'/scripts/ui_test_server.py','--dataset-dir',resolve(values['dataset-dir']),'--run-dir',run,'--port',String(port)],
  { cwd: root, env: { ...process.env, A_STELLAR_A0_MODE: 'deterministic' }, stdio: ['ignore',log,log] });
let browser;
let page;
let startupError;
backend.on('error',(error) => { startupError = error; });
const summary = { status:'running',live_model_calls:0,run_path:run };
try {
  let ready = false;
  for (let i=0;i<100;i++) {
    try { if ((await fetch(base+'/api/v1/ready')).ok) { ready = true; break; } } catch {}
    if (backend.exitCode !== null || startupError) break;
    await new Promise((done) => setTimeout(done,100));
  }
  assert(ready,'Test backend did not start; inspect server.log.');
  browser = await chromium.launch({headless:true,args:['--no-sandbox'],...(values.channel ? {channel:values.channel} : {})});
  page = await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(90_000);
  const errors = []; page.on('pageerror',(e) => errors.push(e.message));
  let blockedExternal = 0;
  await page.route('**/*',(route) => {
    if(new URL(route.request().url()).pathname.startsWith('/api/v1/map/nasa/')) { blockedExternal++; return route.abort(); }
    if (new URL(route.request().url()).hostname === '127.0.0.1') return route.continue();
    blockedExternal++; return route.abort();
  });
  await page.goto(base);
  await page.getByRole('button',{name:'Load in-coverage example endpoints',exact:true}).click();
  async function plan() {
    await page.getByRole('tab',{name:'Plan',exact:true}).click();
    const response = page.waitForResponse((r) => r.url().endsWith('/api/v1/routes/plan') && r.request().method()==='POST');
    await page.getByRole('button',{name:'Plan Route',exact:true}).click();
    const body = await (await response).json(); assert(body.route_id,JSON.stringify(body));
    await page.locator('.route-preview polyline').waitFor();
    return body;
  }
  async function chat(message) {
    await page.getByRole('tab',{name:'Mission Planner',exact:true}).click();
    const response = page.waitForResponse((r) => r.url().endsWith('/chat') && r.request().method()==='POST');
    await page.getByLabel('Message planning assistant',{exact:true}).fill(message);
    await page.getByRole('button',{name:'Send message',exact:true}).click();
    const body = await (await response).json(); assert(body.message_id,JSON.stringify(body));
    if (body.result) await page.waitForURL('**route='+body.result.route_id);
    await page.getByRole('tab',{name:'Plan',exact:true}).click();
    return body;
  }
  const initial = await plan();
  await page.getByRole('heading',{name:'Planning rationale',exact:true}).waitFor();
  const { stops } = await (await fetch(base+'/__test/scenario')).json();
  const coordinates = (points) => points.map((p) => `${p.longitude},${p.latitude}`).join('; ');
  const two = await chat('Add required points: '+coordinates(stops.slice(0,2)));
  assert.deepEqual(two.metadata.request.waypoints,stops.slice(0,2));
  const eight = await chat('Add required points: '+coordinates(stops.slice(2)));
  assert.deepEqual(eight.metadata.request.waypoints,stops);
  const reordered = await chat('Reverse all waypoint visits, keeping the same start and goal.');
  assert.deepEqual(reordered.metadata.request.waypoints,[...stops].reverse());
  assert.equal(reordered.metadata.parent_route_id,eight.result.route_id);
  await page.getByRole('heading',{name:'Changes from previous route',exact:true}).waitFor();
  const answer = await chat('Why was this order selected?'); assert.equal(answer.result,null);
  await page.reload();
  await page.getByRole('tab',{name:'Mission Planner',exact:true}).click();
  await page.locator('.chat-transcript').getByText('Reverse all waypoint visits',{exact:false}).waitFor();
  await page.getByRole('tab',{name:'Plan',exact:true}).click();
  await page.locator('.route-preview polyline').waitFor();
  const svg = page.locator('.route-preview svg');
  const before = (await svg.getAttribute('viewBox')).split(' ').map(Number);
  await page.getByRole('button',{name:'Focus W1',exact:true}).click();
  const focused = (await svg.getAttribute('viewBox')).split(' ').map(Number);
  assert(focused[2] < before[2],'Nearby stops must support a tighter view than the complete route.');
  await page.getByRole('button',{name:'Zoom in DEM preview',exact:true}).click();
  const zoomed = (await svg.getAttribute('viewBox')).split(' ').map(Number);
  assert(zoomed[2] < focused[2]);
  const box = await svg.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.mouse.down();
  await page.mouse.move(box.x+box.width/2+35,box.y+box.height/2+20); await page.mouse.up();
  assert.notEqual((await svg.getAttribute('viewBox')).split(' ')[0],String(zoomed[0]));
  await page.locator('.route-preview').getByRole('button',{name:'Fit route',exact:true}).click();
  summary.stage = 'expand_preview';
  await page.getByRole('button',{name:'Expand preview',exact:true}).click();
  await page.waitForFunction(() => document.fullscreenElement?.classList.contains('route-preview'),null,{timeout:5000});
  summary.stage = 'close_expanded_preview';
  await page.getByRole('button',{name:'Close expanded preview',exact:true}).click();
  await page.waitForFunction(() => !document.fullscreenElement,null,{timeout:5000});
  summary.stage = 'regional_route';
  await page.locator('.route-preview').screenshot({path:run+'/eight-stops.png'});
  await page.getByRole('button',{name:'Load crater-scale example endpoints',exact:true}).click();
  const regional = await plan();
  assert(regional.metrics.distance_m > 40_000);
  const stored = await (await fetch(base+'/api/v1/routes/'+regional.route_id)).json();
  assert(stored.metadata.grid.planning_resolution_m[0] > stored.metadata.grid.source_resolution[0]);
  await page.locator('.route-preview').screenshot({path:run+'/regional-route.png'});
  await page.screenshot({path:run+'/ui.png',fullPage:true});
  assert.deepEqual(errors,[]); assert(blockedExternal>0);
  Object.assign(summary,{status:'passed',stage:'complete',initial_route_id:initial.route_id,regional_route_id:regional.route_id,
    distance_m:regional.metrics.distance_m,blocked_external_requests:blockedExternal,
    checks:['production_assets_and_same_origin_api','offline_NASA','plan_and_rationale','chat_add_two_then_six_points',
      'chat_reverse_eight_stops','stored_parent_comparison','answer_without_replan','reload_route_and_history',
      'focus_nearby_stops','zoom_and_pan','expanded_preview','crater_scale_route_preview','no_page_errors']});
} catch (error) { Object.assign(summary,{status:'failed',message:String(error)}); if (page) await page.screenshot({path:run+'/failure.png',fullPage:true}).catch(() => {}); }
finally {
  if (browser) await browser.close();
  if (backend.pid && backend.exitCode === null) { backend.kill('SIGTERM'); await once(backend,'exit'); }
  closeSync(log);
  writeFileSync(run+'/summary.json',JSON.stringify(summary,null,2)+'\n');
  console.log(JSON.stringify(summary,null,2));
}
if (summary.status!=='passed') process.exitCode = 1;
