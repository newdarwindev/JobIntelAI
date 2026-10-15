import {test,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';

const panel=page=>page.getByRole('region',{name:'Saved operation status',exact:true});
const click=async(page,name)=>{await page.getByRole('button',{name,exact:true}).click();await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};
const nav=async(page,name)=>{await page.getByRole('navigation').getByRole('link',{name,exact:true}).click();await expect(page.getByRole('heading',{level:1,name,exact:true})).toBeVisible();};
const openJob=async page=>{await page.evaluate(()=>{location.hash='workbench?job=RECOVER';});await expect(page.getByLabel('Selected posting')).toHaveValue('RECOVER');await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};
const get=async(request,path)=>{const response=await request.get(path);expect(response.ok()).toBeTruthy();return response.json();};

async function savedState(request,kind,profileId){
  const job=await get(request,'/jobs/RECOVER'),history=await get(request,'/jobs/RECOVER/history');
  if(kind==='registry')return {count:(await get(request,'/jobs')).jobs.length,id:null};
  if(kind==='snapshot'||kind==='fetch')return {count:history.snapshots.length,id:job.snapshot.id};
  if(kind==='candidate')return {count:(await get(request,`/candidates/${profileId}/revisions`)).revisions.length,id:null};
  if(kind==='extract')return {count:history.snapshots.reduce((n,s)=>n+s.runs.length,0),id:job.extraction?.run_id??null};
  if(kind==='evaluate')return {count:(await get(request,'/evaluation-runs')).evaluation_runs.length,id:null};
  return {count:null,id:null};
}

// The application receives real API outcomes; only their delivery is interrupted.
async function interrupt(page,path,mode){
  let used=false,received;
  const handled=new Promise(resolve=>{received=resolve;});
  const transmissions=[];
  const observe=request=>{if(new URL(request.url()).pathname===path&&request.method()==='POST')transmissions.push(request.headers()['idempotency-key']);};
  page.on('request',observe);
  await page.route(`**${path}`,async route=>{
    if(used){await route.continue();return;}
    used=true;
    if(mode==='after_commit'){
      const response=await route.fetch();received({status:response.status(),result:await response.json()});
    }else received({status:null,result:null});
    await route.abort('connectionclosed');
  });
  return {handled,transmissions,stop:()=>page.off('request',observe)};
}

test('UI13 | Durable mutation identity, lost-response recovery and safe replay',async({page,request,browser},info)=>{
  test.setTimeout(240000);
  info.annotations.push({type:'browser-version',description:browser.version()});
  expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();
  expect((await request.post('/ui/reset')).ok()).toBeTruthy();
  const source=await readFile(new URL('../../data/sample_jobs/SYN-01.txt',import.meta.url),'utf8');
  const profile=JSON.parse(await readFile(new URL('../../data/sample_candidate.json',import.meta.url),'utf8'));
  profile.profile_id='recovery-baseline';
  expect((await request.post('/jobs/import',{data:{jobs:[{job_id:'RECOVER',company:'Authored recovery',role:'Engineer',official_url:'https://example.com/authored-job'}]}})).ok()).toBeTruthy();
  expect((await request.post('/jobs/RECOVER/snapshots',{data:{text:source}})).ok()).toBeTruthy();
  const priorRun=await (await request.post('/jobs/RECOVER/extract',{data:{}})).json();
  const priorProfile=await (await request.post('/candidates/import',{data:profile})).json();
  const priorMatch=await (await request.post('/jobs/RECOVER/match',{data:{profile_id:profile.profile_id,profile_revision_id:priorProfile.profile_revision_id,expected_run_id:priorRun.run_id}})).json();
  const priorEvaluation=await (await request.post('/evaluate',{data:{configurations:['fixture_raw']}})).json();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const rows=[];
  await page.goto('/ui/');await openJob(page);

  for(const mode of ['before_delivery','after_commit']){
    for(const kind of ['registry','snapshot','candidate','extract','match','evaluate','fetch']){
      await test.step(`${kind}: ${mode}`,async()=>{
        let path,button,profileId;
        if(kind==='registry'){
          await nav(page,'Job registry');await page.getByLabel('Import format').selectOption('json');
          await page.getByLabel('Registry content').fill(JSON.stringify([{job_id:`REG-${mode}`,company:`Authored registry ${mode}`,role:'Engineer'}]));path='/jobs/import';button='Import registry';
        }else if(kind==='candidate'){
          await nav(page,'Candidate evidence');profileId=`recovery-${mode}`;
          await page.getByLabel('Candidate JSON',{exact:true}).fill(JSON.stringify({...profile,profile_id:profileId,complete:mode==='after_commit'},null,2));path='/candidates/import';button='Validate & save profile';
        }else if(kind==='match'){
          await nav(page,'Candidate evidence');await page.getByLabel('Selected posting').selectOption('RECOVER');path='/jobs/RECOVER/match';button='Match selected posting';
        }else if(kind==='evaluate'){
          await nav(page,'Evaluation lab');path='/evaluate';button='Run fixture evaluation';
        }else{
          await openJob(page);
          if(kind==='snapshot'){
            // Different raw bytes, known identical clean text: a real immutable new snapshot.
            await page.getByLabel('Source format').selectOption('html');
            await page.getByLabel('Posting source').fill(`<nav>${mode}</nav><main>${source}</main>`);
            path='/jobs/RECOVER/snapshots';button='Save immutable snapshot';
          }else{path=`/jobs/RECOVER/${kind}`;button=kind==='extract'?'Extract requirements':'Try URL acquisition';}
        }
        const before=await savedState(request,kind,profileId);
        const fault=await interrupt(page,path,mode);
        await click(page,button);const delivered=await fault.handled;
        const initialState=mode==='before_delivery'?'not_received':'committed';
        await expect(panel(page)).toHaveAttribute('data-state',initialState);
        if(mode==='before_delivery'){
          await expect(page.getByRole('button',{name:button,exact:true})).toBeDisabled();
          expect((await savedState(request,kind,profileId)).count).toBe(before.count);
          await nav(page,'Overview');await expect(panel(page)).toHaveAttribute('data-state','not_received');
          await click(page,'Retry same operation');
        }
        await expect(panel(page)).toHaveAttribute('data-state','committed');
        const key=fault.transmissions[0],status=await get(request,`/operations/${key}`);
        expect(status.state).toBe('committed');expect(status.execution_count).toBe(1);
        const after=await savedState(request,kind,profileId);
        if(before.count!==null)expect(after.count).toBe(before.count+1);
        expect(new Set(fault.transmissions).size).toBe(1);
        expect(fault.transmissions).toHaveLength(mode==='before_delivery'?2:1);
        if(delivered.result)expect(status.result).toEqual(delivered.result);
        const savedId=status.result.fetch_id??status.result.match_run_id??status.result.evaluation_run_id??status.result.profile_revision_id??status.result.run_id??status.result.snapshot_id??null;
        const rawReplay=await request.post(path,{data:{unexpected:'authored identity mismatch'},headers:{'Idempotency-Key':key}});
        // A different body cannot repurpose the existing identity or add another result.
        expect(rawReplay.status()).toBe(409);
        expect((await get(request,`/operations/${key}`)).result).toEqual(status.result);
        expect((await savedState(request,kind,profileId)).count).toBe(after.count);
        rows.push({project:info.project.name,kind,scenario:mode,operation_id:status.operation_id,initial_state:initialState,final_state:status.state,http_status:status.http_status,browser_post_requests:fault.transmissions.length,api_conflict_probes:1,distinct_request_identities:new Set(fault.transmissions).size,completed_handler_executions:status.execution_count,before_records:before.count,after_records:after.count,saved_id:savedId});
        fault.stop();
      });
    }
  }

  await test.step('A committed result with a failed display read uses lookup instead of POST',async()=>{
    await openJob(page);let used=false,posts=0,key;
    const observe=request=>{if(new URL(request.url()).pathname==='/jobs/RECOVER/extract'&&request.method()==='POST'){posts++;key=request.headers()['idempotency-key'];}};
    page.on('request',observe);
    await page.route('**/v2/jobs',async route=>{if(!used&&route.request().method()==='GET'){used=true;await route.abort('connectionclosed');}else await route.continue();});
    await click(page,'Extract requirements');
    await expect(panel(page)).toContainText('display refresh is pending');
    await expect(page.getByRole('button',{name:'Extract requirements',exact:true})).toBeDisabled();
    const committed=await get(request,`/operations/${key}`);expect(committed.state).toBe('committed');
    await click(page,'Check saved outcome');expect(posts).toBe(1);
    expect((await get(request,'/jobs/RECOVER')).extraction.run_id).toBe(committed.result.run_id);
    rows.push({project:info.project.name,kind:'extract',scenario:'display_read_lost',operation_id:committed.operation_id,initial_state:'committed/display_pending',final_state:'committed',http_status:committed.http_status,browser_post_requests:posts,distinct_request_identities:1,completed_handler_executions:committed.execution_count,before_records:null,after_records:null,saved_id:committed.result.run_id});
    page.off('request',observe);
  });

  await test.step('An unsent request survives reload as an opaque identity and cancellation blocks late delivery',async()=>{
    await page.getByLabel('Posting source').fill('Authored unsent private body marker');
    const fault=await interrupt(page,'/jobs/RECOVER/snapshots','before_delivery');
    await click(page,'Save immutable snapshot');await expect(panel(page)).toHaveAttribute('data-state','not_received');
    const key=fault.transmissions[0];
    const stored=await page.evaluate(()=>JSON.stringify({...localStorage}));
    expect(stored).toContain(key);expect(stored).not.toContain('Authored unsent private body marker');
    await page.reload();await expect(panel(page)).toHaveAttribute('data-state','not_received');
    await expect(page.getByRole('button',{name:'Retry same operation',exact:true})).toHaveCount(0);
    const before=await savedState(request,'snapshot');
    await click(page,'Cancel unsent operation');
    expect((await request.post('/jobs/RECOVER/snapshots',{data:{text:'Authored unsent private body marker'},headers:{'Idempotency-Key':key}})).status()).toBe(409);
    const status=await get(request,`/operations/${key}`);expect(status.execution_count).toBe(0);
    expect((await savedState(request,'snapshot')).count).toBe(before.count);
    rows.push({project:info.project.name,kind:'snapshot',scenario:'unsent_reload_cancel',operation_id:status.operation_id,initial_state:'not_received',final_state:status.state,http_status:status.http_status,browser_post_requests:fault.transmissions.length,api_conflict_probes:1,distinct_request_identities:1,completed_handler_executions:status.execution_count,before_records:before.count,after_records:before.count,saved_id:null});
    fault.stop();
  });

  await test.step('Actual provider work in flight remains uncertain until its saved outcome is read',async()=>{
    expect((await request.post('/responses-fixture/delay?timeout=3')).ok()).toBeTruthy();
    await page.reload();await expect(page.locator('main')).toContainText('Responses contract emulator');
    let used=false,completed,key,posts=0;
    const finished=new Promise(resolve=>{completed=resolve;});
    const observe=request=>{if(new URL(request.url()).pathname==='/jobs/RECOVER/extract'&&request.method()==='POST'){posts++;key=request.headers()['idempotency-key'];}};
    page.on('request',observe);
    await page.route('**/jobs/RECOVER/extract',async route=>{
      if(used){await route.continue();return;}
      used=true;const real=route.fetch();
      await expect.poll(async()=>key?(await get(request,`/operations/${key}`)).state:'not_received').toBe('uncertain');
      await route.abort('connectionclosed');completed(await real);
    });
    await click(page,'Extract requirements');await expect(panel(page)).toHaveAttribute('data-state','uncertain');
    await expect(page.getByRole('button',{name:'Extract requirements',exact:true})).toBeDisabled();
    await expect(page.getByRole('button',{name:'Retry same operation',exact:true})).toHaveCount(0);
    await nav(page,'Candidate evidence');await expect(panel(page)).toHaveAttribute('data-state','uncertain');
    const real=await finished;expect(real.ok()).toBeTruthy();
    await click(page,'Check saved outcome');
    const status=await get(request,`/operations/${key}`);expect(status.state).toBe('committed');expect(posts).toBe(1);
    expect((await get(request,'/responses-fixture-diagnostics')).request_count).toBe(1);
    rows.push({project:info.project.name,kind:'extract',scenario:'provider_in_flight',operation_id:status.operation_id,initial_state:'uncertain',final_state:status.state,http_status:status.http_status,browser_post_requests:posts,distinct_request_identities:1,completed_handler_executions:status.execution_count,before_records:null,after_records:null,saved_id:status.result.run_id});
    page.off('request',observe);
    expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();
    await page.reload();await expect(page.locator('.sidebar-note')).toContainText('Fixture replay');
  });

  await test.step('A lost status read after commit survives reload without private request bodies',async()=>{
    await openJob(page);
    let unread=true;
    await page.route('**/operations/*',async route=>{if(unread&&route.request().method()==='GET'){unread=false;await route.abort('connectionclosed');}else await route.continue();});
    const fault=await interrupt(page,'/jobs/RECOVER/extract','after_commit');
    await click(page,'Extract requirements');await fault.handled;
    await expect(panel(page)).toHaveAttribute('data-state','uncertain');
    const key=fault.transmissions[0],status=await get(request,`/operations/${key}`);
    const before=await savedState(request,'extract');
    await page.reload();await expect(panel(page)).toHaveAttribute('data-state','committed');
    expect((await get(request,'/jobs/RECOVER')).extraction.run_id).toBe(status.result.run_id);
    expect(fault.transmissions).toHaveLength(1);
    rows.push({project:info.project.name,kind:'extract',scenario:'lookup_lost_reload',operation_id:status.operation_id,initial_state:'uncertain',final_state:'committed',http_status:status.http_status,browser_post_requests:fault.transmissions.length,distinct_request_identities:1,completed_handler_executions:status.execution_count,before_records:before.count,after_records:(await savedState(request,'extract')).count,saved_id:status.result.run_id});
    fault.stop();
  });

  await test.step('Definite validation rejection is visible, retains drafts and does not start the handler',async()=>{
    await nav(page,'Candidate evidence');
    const invalid=JSON.stringify({profile_id:'bad-recovery',evidence:[{skill:'Python'}]});
    const keys=[];
    const observe=request=>{if(new URL(request.url()).pathname==='/candidates/import'&&request.method()==='POST')keys.push(request.headers()['idempotency-key']);};page.on('request',observe);
    await page.getByLabel('Candidate JSON',{exact:true}).fill(invalid);
    await click(page,'Validate & save profile');await expect(panel(page)).toHaveAttribute('data-state','rejected');
    await expect(page.locator('#candidate-error')).toContainText('422:');await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(invalid);
    const status=await get(request,`/operations/${keys[0]}`);expect(status.execution_count).toBe(0);
    const count=(await get(request,'/candidates/bad-recovery/revisions')).revisions.length;expect(count).toBe(0);
    rows.push({project:info.project.name,kind:'candidate',scenario:'validation_rejected',operation_id:status.operation_id,initial_state:'rejected',final_state:'rejected',http_status:status.http_status,browser_post_requests:keys.length,distinct_request_identities:new Set(keys).size,completed_handler_executions:status.execution_count,before_records:0,after_records:count,saved_id:null});
    page.off('request',observe);
  });

  const history=await get(request,'/jobs/RECOVER/history');
  expect(history.snapshots.some(s=>s.runs.some(r=>r.run_id===priorRun.run_id))).toBeTruthy();
  expect(await get(request,`/candidates/${profile.profile_id}/revisions/${priorProfile.profile_revision_id}`)).toEqual(priorProfile);
  expect(await get(request,`/match-runs/${priorMatch.match_run_id}`)).toEqual(priorMatch);
  expect(await get(request,`/evaluation-runs/${priorEvaluation.evaluation_run_id}`)).toEqual(priorEvaluation);
  expect(errors).toEqual([]);
  const comparisonPath=info.outputPath('mutation-comparison.json');
  await writeFile(comparisonPath,JSON.stringify({schema_version:1,mode:'authored fixture replay and Responses emulator; actual API/DB operations',rows},null,2));
  await info.attach('mutation-comparison',{path:comparisonPath,contentType:'application/json'});
  await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  await page.screenshot({path:info.outputPath('successful-screen.png'),fullPage:true});
  await page.waitForTimeout(1200);
});
