import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';

const services=JSON.parse(process.env.UI_NORMAL_SERVICES??'{}');
test.beforeEach(async({browser},info)=>{info.annotations.push({type:'browser-version',description:browser.version()});});

async function downloadJson(page,label){
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:label,exact:true}).click();
  return JSON.parse(await readFile(await (await pending).path(),'utf8'));
}
async function open(page,service,view,job){
  await page.goto(`${service.base}/ui/#${view}${job?`?job=${encodeURIComponent(job)}`:''}`);
  await expect(page.locator('#main')).not.toContainText('Connecting to the evidence workspace');
}
async function json(request,service,path){const r=await request.get(service.base+path);expect(r.ok()).toBeTruthy();return r.json();}
async function pipeline({page,request},info,mode){
  const service=services[mode];expect(service?.demo).toBe(false);expect(service.database).toBe('postgresql');
  const id=`browser-${mode}-${info.project.name}`;
  const config=await json(request,service,'/ui/config');expect(config.demo).toBe(false);
  expect(config.actions.samples).toBe(false);expect(config.actions.reset).toBe(false);
  expect((await request.get(service.base+'/ui/fixtures')).status()).toBe(404);
  expect((await request.post(service.base+'/ui/reset')).status()).toBe(405);
  await open(page,service,'registry');await expect(page.locator('.mode-badge')).toHaveText(config.execution_label.toUpperCase());await expect(page.locator('.sidebar-note')).toContainText(config.execution_label);
  await expect(page.getByRole('button',{name:'Load sample registry'})).toHaveCount(0);
  await page.getByLabel('Import format').selectOption('json');
  await page.getByLabel('Registry content').fill(JSON.stringify([{job_id:id,company:`Authored ${id}`,role:'Engineer',official_url:`${info.project.name==='mobile-chromium'?'http':'https'}://example.com/${mode==='fixture'?'text':'unseen'}`} ]));
  await page.getByRole('button',{name:'Import registry',exact:true}).click();await expect(page.locator('#notice')).toContainText('Imported 1');
  await open(page,service,'workbench',id);await page.getByRole('button',{name:'Try URL acquisition',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('URL source saved');
  const options=await page.getByLabel('Extraction configuration').locator('option').evaluateAll(items=>items.map(x=>x.value));
  expect(options.sort()).toEqual(config.configurations.map(x=>x.id).sort());
  await page.getByLabel('Extraction configuration').selectOption(config.default_configuration);
  await page.getByRole('button',{name:'Extract requirements',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('Extraction saved',{timeout:250000});
  const saved=(await json(request,service,`/jobs/${id}`)).extraction;expect(saved.requirements.length).toBeGreaterThan(0);
  const exported=await downloadJson(page,'Export evidence JSON');expect(exported.extraction.run_id).toBe(saved.run_id);
  for(const r of exported.extraction.requirements)expect(Array.from(exported.snapshot.clean_text).slice(r.evidence.start,r.evidence.end).join('')).toBe(r.evidence.quote);
  await page.getByRole('button',{name:'Highlight source quote',exact:true}).first().click();await expect(page.locator('mark')).not.toBeEmpty();
  await open(page,service,'candidate',id);
  const profile={profile_id:id,evidence:[{skill:'Python',current_capability:'strong',production_evidence:'none',source:'synthetic://persistent-browser-profile',quote:'I can independently build programs with Python.'}]};
  await page.getByLabel('Candidate JSON').fill(JSON.stringify(profile));await page.getByRole('button',{name:'Validate & save profile',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('activated');
  const revision=JSON.parse(await page.evaluate(()=>localStorage.getItem('jobintel-selected-revision')));
  await page.reload();await expect(page.locator('#main')).toContainText(revision.profile_revision_id);
  await page.getByRole('button',{name:'Match selected posting',exact:true}).click();await expect(page.locator('#main')).toContainText('COVERED');
  const matches=await downloadJson(page,'Export matches JSON');expect(matches.profile_revision_id).toBe(revision.profile_revision_id);expect(matches.matches.map(m=>m.requirement_id).sort()).toEqual(exported.rows.map(r=>r.requirement_id).sort());
  await open(page,service,'analytics',id);const analytics=await json(request,service,'/analytics/skills');
  await expect(page.locator('#main')).toContainText(`N = ${analytics.N}`);
  const corpus=await downloadJson(page,'Export corpus JSON');expect(corpus.N).toBe(analytics.N);expect(corpus.selection.profile_revision_id).toBe(revision.profile_revision_id);expect(corpus.jobs.map(j=>j.job_id)).toContain(id);
  return {service,id,saved};
}
async function evaluation(page,request,service,mode){
  await open(page,service,'evaluation');
  const values=await page.locator('input[name="configuration"]').evaluateAll(items=>items.map(x=>x.value));
  expect(values.sort()).toEqual((await json(request,service,'/ui/config')).configurations.map(x=>x.id).sort());
  if(mode==='local'){
    await page.getByLabel('Saved evaluation run ID').fill(service.evaluation_run_id);
    await page.getByRole('button',{name:'Load saved evaluation',exact:true}).click();
  }else{
    await page.getByRole('button',{name:mode==='fixture'?'Run fixture evaluation':'Run contract evaluation',exact:true}).click();
  }
  await expect(page.locator('#main')).toContainText('Evaluation run #');
  const report=await downloadJson(page,'Export evaluation JSON');await page.reload();
  await expect(page.locator('#main')).toContainText(report.evaluation_run_id);
  expect((await json(request,service,`/evaluation-runs/${report.evaluation_run_id}`)).results).toEqual(report.results);
  if(mode==='local')expect(report.dataset_size).toBe(3);
  else expect(report.mode).toContain(mode==='fixture'?'fixture':'emulator');
}

test('UI09 | Normal PostgreSQL fixture pipeline and unsupported-input recovery',async({page,request},info)=>{
  const ctx={page,request};
  const {service,id,saved}=await pipeline(ctx,info,'fixture');
  await open(ctx.page,service,'workbench',id);await ctx.page.getByLabel('Posting source').fill('Python is required.');
  await ctx.page.getByRole('button',{name:'Save immutable snapshot',exact:true}).click();await expect(ctx.page.locator('#notice')).toContainText('saved');
  await ctx.page.getByRole('button',{name:'Extract requirements',exact:true}).click();await expect(ctx.page.locator('#notice')).toContainText('501');
  const history=await json(ctx.request,service,`/jobs/${id}/history`);expect(history.snapshots.flatMap(s=>s.runs).map(r=>r.run_id)).toContain(saved.run_id);
  await evaluation(ctx.page,ctx.request,service,'fixture');
});

test('UI10 | Normal PostgreSQL Responses contract pipeline and provider failure history',async({page,request},info)=>{
  const ctx={page,request};
  const {service,id,saved}=await pipeline(ctx,info,'emulator');
  await open(ctx.page,service,'workbench',id);
  await ctx.page.getByLabel('Posting source').fill('Authored unsaved provider recovery text.');
  for(const scenario of ['refusal','invalid_evidence','malformed_json']){
    expect((await ctx.request.post(service.control_base+'/control',{headers:{Authorization:'Bearer jobintel-contract-only'},data:{scenario}})).ok()).toBeTruthy();
    await ctx.page.getByRole('button',{name:'Extract requirements',exact:true}).click();await expect(ctx.page.locator('#notice')).toContainText(scenario==='malformed_json'?'malformed_json':scenario);
    expect((await json(ctx.request,service,`/jobs/${id}`)).extraction.run_id).toBe(saved.run_id);
    await expect(ctx.page.getByLabel('Posting source')).toHaveValue('Authored unsaved provider recovery text.');
    const diagnostics=await (await ctx.request.get(service.control_base+'/diagnostics')).json();expect(diagnostics.request_count).toBe(scenario==='malformed_json'?2:1);
  }
  await ctx.request.post(service.control_base+'/control',{headers:{Authorization:'Bearer jobintel-contract-only'},data:{scenario:'success'}});
  await evaluation(ctx.page,ctx.request,service,'emulator');
});

test('UI11 | Normal PostgreSQL CPU inference, measured evaluation and readiness recovery',async({page,request},info)=>{
  const ctx={page,request};
  test.setTimeout(360000);
  const {service,id,saved}=await pipeline(ctx,info,'local');
  expect(saved.provenance.execution_mode).toBe('local-inference');expect(saved.provenance.model_weights_sha256).toHaveLength(64);
  await evaluation(ctx.page,ctx.request,service,'local');await open(ctx.page,service,'workbench',id);
  expect(service.project).toMatch(/^jobintel-browser-local-[a-f0-9]{12}$/);
  const container=service.project+'-llama-cpp-1';
  await ctx.page.getByLabel('Posting source').fill('Authored unsaved provider recovery text.');
  try{
    expect(spawnSync('docker',['stop',container],{encoding:'utf8'}).status).toBe(0);
    await ctx.page.getByRole('button',{name:'Extract requirements',exact:true}).click();await expect(ctx.page.locator('#notice')).toContainText('provider_failure');
    await expect(ctx.page.getByRole('button',{name:'Extract requirements',exact:true})).toBeDisabled();
    expect((await json(ctx.request,service,`/jobs/${id}`)).extraction.run_id).toBe(saved.run_id);
    await expect(ctx.page.getByLabel('Posting source')).toHaveValue('Authored unsaved provider recovery text.');
  }finally{expect(spawnSync('docker',['start',container],{encoding:'utf8'}).status).toBe(0);}
  await expect.poll(async()=> (await json(ctx.request,service,'/ui/config')).readiness,{timeout:120000}).toBe('ready');
  await ctx.page.getByRole('button',{name:'Refresh provider status',exact:true}).click();await expect(ctx.page.getByRole('button',{name:'Extract requirements',exact:true})).toBeEnabled();
  await ctx.page.reload();await expect(ctx.page.locator('#main')).toContainText(`Run #${saved.run_id}`);
});
