// Real local DEM, production UI/API and mocked NASA tiles/model. No paid calls.
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {readFileSync,mkdirSync,openSync,closeSync,writeFileSync} from 'node:fs';
import {createServer} from 'node:net';
import {once} from 'node:events';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import assert from 'node:assert/strict';
const {values}=parseArgs({options:{'dataset-dir':{type:'string'},python:{type:'string',default:'python'},channel:{type:'string'}}});
assert(values['dataset-dir']);
const root=fileURLToPath(new URL('../../',import.meta.url));
const out=resolve(root,'data/processed/ui-regressions',new Date().toISOString().replaceAll(/[:.]/g,'-'));
mkdirSync(out,{recursive:true});
const probe=createServer(); probe.listen(0,'127.0.0.1'); await once(probe,'listening');
const port=probe.address().port; await new Promise(done=>probe.close(done));
const base=`http://127.0.0.1:${port}`;
const fd=openSync(out+'/server.log','w');
const server=spawn(values.python,[root+'/scripts/ui_test_server.py','--dataset-dir',values['dataset-dir'],'--run-dir',out,'--port',String(port)],{cwd:root,stdio:['ignore',fd,fd]});
let browser;
let page;
const summary={status:'running',live_model_calls:0};
try {
  let ready=false;
  for (let i=0;i<300;i++) {
    try {if ((await fetch(base+'/api/v1/ready')).ok) {ready=true;break;}} catch {}
    if (server.exitCode!==null) break;
    await new Promise(done=>setTimeout(done,100));
  }
  assert(ready,'Test backend failed to start');
  browser=await chromium.launch({headless:true,...(values.channel ? {channel:values.channel} : {})});
  page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const xml=readFileSync(resolve(values['dataset-dir'],'registration/jezero-wmts-capabilities.xml'),'utf8');
  const jezero='NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018';
  await page.route('https://trek.nasa.gov/**',route=>{
    if (route.request().url().endsWith('WMTSCapabilities.xml')) {
      const id=route.request().url().split('/EQ/')[1].split('/')[0];
      return route.fulfill({contentType:'application/xml',body:xml.replaceAll(jezero,id)});
    }
    return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=','base64')});
  });
  await page.goto(base);
  summary.stage='map_controls';
  await page.locator('.ol-zoom').waitFor();
  const zoom=await page.locator('.ol-zoom').boundingBox();
  const fit=await page.getByRole('button',{name:'Fit route',exact:true}).boundingBox();
  const frame=await page.locator('.map-frame').boundingBox();
  assert(zoom.x>frame.x+frame.width/2 && zoom.y>frame.y+frame.height/2);
  assert(zoom.y>fit.y+fit.height);
  await page.getByRole('tab',{name:'Evidence',exact:true}).click();
  summary.stage='layers';
  for (const name of ['Mars Trek basemap','High-resolution Jezero imagery','Jezero DEM coverage','Initial DEM example window','M20 DEM elevation preview','THEMIS daytime visual context','THEMIS nighttime visual context','SIM 3464 geology','Perseverance science POIs','Perseverance traverse','Perseverance stops & Navcam references','Route & mission stops']) {
    const checkbox=page.getByRole('checkbox',{name:'Show '+name,exact:true});
    await checkbox.waitFor();
    await checkbox.setChecked(false);
    assert.equal(await checkbox.isChecked(),false);
    await checkbox.setChecked(true);
    assert.equal(await checkbox.isChecked(),true);
  }
  // Check all three real raster URLs independently, not just enabled checkboxes.
  for (const id of ['dem_surface','thermal','thermal_night']) {
    const r=await page.request.get(base+'/api/v1/map/layers/'+id+'.png');
    assert(r.ok(),id+': '+await r.text());
    assert.equal(r.headers()['content-type'],'image/png');
  }
  const demToggle=page.getByRole('checkbox',{name:'Show M20 DEM elevation preview',exact:true});
  await demToggle.setChecked(false);
  const before=await page.locator('.map').screenshot();
  await demToggle.setChecked(true);
  const after=await page.locator('.map').screenshot();
  assert(!before.equals(after),'DEM visibility must change the rendered map');
  const geology=await page.request.get(base+'/api/v1/map/geology');
  assert(geology.ok());assert((await geology.json()).features.length>0);
  summary.stage='plan';
  await page.getByRole('tab',{name:'Plan',exact:true}).click();
  await page.getByRole('button',{name:'Load in-coverage example endpoints',exact:true}).click();
  await page.getByRole('button',{name:'Plan Route',exact:true}).click();
  await page.locator('.route-preview polyline').waitFor();
  await page.getByRole('tab',{name:'Route',exact:true}).click();
  const technical=page.locator('#route-panel details').first();
  assert.equal(await technical.getAttribute('open'),null);
  assert.equal(await page.locator('#route-panel').getByText('Grid cells',{exact:true}).isVisible(),false);
  assert.equal(await page.locator('#route-panel').getByText('Terrain resolution',{exact:true}).isVisible(),true);
  await technical.locator('summary').click();
  assert.equal(await page.locator('#route-panel').getByText('Grid cells',{exact:true}).isVisible(),true);
  await page.getByRole('tab',{name:'Briefing',exact:true}).click();
  summary.stage='briefing';
  for (const width of [1440,850,600]) {
    await page.setViewportSize({width,height:1000});
    const checks=await page.locator('.briefing-summary').first().evaluate(el=>{
      const dt=el.querySelector('dt'),dd=el.querySelector('dd');
      return {labelWidth:dt.getBoundingClientRect().width,valueWidth:dd.getBoundingClientRect().width,overflow:document.documentElement.scrollWidth>innerWidth};
    });
    assert(checks.labelWidth>180 && checks.valueWidth>180 && !checks.overflow,JSON.stringify(checks));
    await page.screenshot({path:out+`/briefing-${width}.png`,fullPage:true});
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('tab',{name:'A0 Assistant',exact:true}).click();
  summary.stage='budget_recovery';
  const state=await (await fetch(base+'/__test/provider')).json();
  await fetch(base+'/__test/budget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_calls:state.calls})});
  await page.getByLabel('Message A0',{exact:true}).fill('Why this route?');
  await page.getByRole('button',{name:'Send to A0',exact:true}).click();
  await page.getByText('The backend\'s local request or cost limit has been reached.',{exact:false}).waitFor();
  assert.equal((await (await fetch(base+'/__test/provider')).json()).calls,state.calls);
  await fetch(base+'/__test/budget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_calls:200})});
  await page.getByRole('button',{name:'Check chat request status',exact:true}).click();
  await page.getByRole('button',{name:'Retry chat request',exact:true}).click();
  await page.getByText('Chat request: succeeded.',{exact:true}).waitFor();
  assert.equal((await (await fetch(base+'/__test/provider')).json()).calls,state.calls+1);
  assert.deepEqual(errors,[]);
  Object.assign(summary,{status:'passed',checks:['independent_layer_controls','real_DEM_and_day_night_previews','zoom_bottom_right','briefing_1440_850_600','budget_recovery_same_request_no_auto_retry','no_page_errors']});
} catch(error) {summary.status='failed';summary.error=String(error);process.exitCode=1;if(page) await page.screenshot({path:out+'/failure.png',fullPage:true}).catch(()=>{});}
finally {
  if(browser) await browser.close();
  if(server.exitCode===null) {server.kill();await once(server,'exit');}
  closeSync(fd);writeFileSync(out+'/summary.json',JSON.stringify(summary,null,2));console.log(JSON.stringify({...summary,output:out},null,2));
}
