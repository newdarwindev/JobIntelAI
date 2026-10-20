import {test,expect} from '@playwright/test';
import {writeFile} from 'node:fs/promises';

const article=(page,kind)=>page.locator(`#batch-status [data-batch-kind="${kind}"]`).first();
const row=(page,kind,id)=>article(page,kind).locator(`[data-batch-job="${id}"]`);
const click=async(page,name)=>{await page.getByRole('button',{name,exact:true}).click();await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};
const nav=async(page,name)=>{await page.getByRole('navigation').getByRole('link',{name,exact:true}).click();await expect(page.getByRole('heading',{level:1,name,exact:true})).toBeVisible();};
const get=async(request,path)=>{const r=await request.get(path);expect(r.ok()).toBeTruthy();return r.json();};
const journal=async(page,kind)=>page.evaluate(kind=>JSON.parse(sessionStorage.getItem('jobintel-corpus-batches')).find(batch=>batch.kind===kind),kind);
const totals=batch=>Object.fromEntries(['completed','failed','unattempted','uncertain'].map(state=>[state,batch.items.filter(item=>item.state===state).length]));

async function serverState(request,ids,batch){
  const histories={};for(const id of ids){const h=await get(request,`/jobs/${id}/history`);for(const snapshot of h.snapshots)expect(snapshot.id).toMatch(/^[a-f0-9]{32}$/);histories[id]={snapshots:h.snapshots.map(s=>s.id),extractions:h.snapshots.flatMap(s=>s.runs.map(r=>r.run_id))};}
  const jobs=(await get(request,'/jobs')).jobs;
  const outcomes=[];
  for(const item of batch?.items??[])for(const attempt of item.attempts){const saved=await get(request,`/operations/${attempt.operation_id}`);outcomes.push({job_id:item.jobId,stage:attempt.stage,operation_id:saved.operation_id,state:saved.state,http_status:saved.http_status,execution_count:saved.execution_count,result_id:saved.result?.match_run_id??saved.result?.run_id??saved.result?.snapshot_id??null});}
  return {registered:jobs.length,current_extracted:jobs.filter(job=>job.extraction).length,histories,outcomes};
}

test('UI14 | Partial corpus batches, retained outcomes and bounded continuation',async({page,request,browser},info)=>{
  test.setTimeout(240000);info.annotations.push({type:'browser-version',description:browser.version()});
  const fixture=await get(request,'/ui/fixtures'),jobs=fixture.jobs.slice(0,3),ids=jobs.map(job=>job.job_id),rows=[],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  let badSource=null,posts=[];
  const observe=request=>{const url=new URL(request.url()),key=request.headers()['idempotency-key'];if(request.method()==='POST'&&key&&/\/jobs\/[^/]+\/(snapshots|extract|match)$/.test(url.pathname))posts.push({path:url.pathname,operation_id:key});};page.on('request',observe);

  async function setup(kind,{badJob=null,empty=false}={}){
    await page.unrouteAll({behavior:'wait'});posts=[];badSource=badJob;
    expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();expect((await request.post('/ui/reset')).ok()).toBeTruthy();
    if(page.url()!=='about:blank')await page.evaluate(()=>{localStorage.clear();sessionStorage.clear();});
    // Authored fixture-selection read only. Domain writes/outcomes are always real API calls.
    await page.route('**/ui/fixtures',async route=>{const real=await route.fetch(),data=await real.json();await route.fulfill({response:real,json:{...data,jobs:empty?[]:jobs,sources:{...data.sources,...(badSource?{[badSource]:'Authored unsupported batch source; no replay exists.'}:{})}}});});
    if(kind==='matching'&&!empty){
      expect((await request.post('/jobs/import',{data:{jobs}})).ok()).toBeTruthy();
      for(const id of ids){expect((await request.post(`/jobs/${id}/snapshots`,{data:{text:fixture.sources[id]}})).ok()).toBeTruthy();expect((await request.post(`/jobs/${id}/extract`,{data:{}})).ok()).toBeTruthy();}
    }
    await page.goto('/ui/');await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
    if(kind==='matching'){
      await nav(page,'Candidate evidence');
      if(!empty){await click(page,'Load synthetic candidate');await click(page,'Validate & save profile');}
    }
  }
  const start=kind=>click(page,kind==='extraction'?'Load synthetic corpus':'Match extracted corpus');
  async function visibleCounts(kind,counts){const text=article(page,kind).locator('.batch-counts');for(const [state,count] of Object.entries(counts))await expect(text).toContainText(`${count} ${state}`);}
  async function retainCompleted(kind,partial){
    const final=await journal(page,kind);
    expect(totals(final)).toEqual({completed:3,failed:0,unattempted:0,uncertain:0});
    for(const item of partial.items.filter(item=>item.state==='completed')){
      const saved=final.items.find(other=>other.jobId===item.jobId);
      expect(saved.resultId).toBe(item.resultId);expect(saved.attempts).toEqual(item.attempts);
      const writes=posts.filter(p=>p.path===`/jobs/${item.jobId}/${kind==='matching'?'match':'extract'}`);
      expect(writes).toHaveLength(1);
    }
    for(const item of final.items){
      const succeeded=item.attempts.filter(a=>a.stage===(kind==='matching'?'match':'extract')&&a.state==='committed');expect(succeeded).toHaveLength(1);
      if(kind==='matching'){const saved=await get(request,`/match-runs/${item.resultId}`);expect(saved.profile_revision_id).toBe(final.selection.profile_revision_id);expect(saved.run_id).toBe(item.expectedRunId);}
    }
    await visibleCounts(kind,totals(final));return final;
  }
  async function record(kind,scenario,before,partial,partialServer,final,extra={}){
    const after=await serverState(request,ids,final);
    expect(after.registered).toBe(3);expect(after.current_extracted).toBe(3);
    for(const id of ids)for(const run of before.histories?.[id]?.extractions??[])expect(after.histories[id].extractions).toContain(run);
    rows.push({project:info.project.name,kind,scenario,before,partial:{counts:totals(partial),items:partial.items,server:partialServer},resumed:{counts:totals(final),items:final.items,server:after},browser_mutation_posts:[...posts],...extra});
  }
  async function counters(extracted){await nav(page,'Overview');await expect(page.locator('.metric').filter({hasText:'Registered postings'}).locator('.value')).toHaveText('3');await expect(page.locator('.metric').filter({hasText:'Successfully extracted'}).locator('.value')).toHaveText(String(extracted));}

  for(const kind of ['extraction','matching'])for(const index of [0,1,2]){
    await test.step(`${kind}: failure at ${['first','middle','last'][index]} item`,async()=>{
      const target=ids[index];await setup(kind,{badJob:kind==='extraction'?target:null});
      const before=kind==='matching'?await serverState(request,ids):{registered:0,current_extracted:0,histories:{}};
      if(kind==='matching'){
        let used=false;await page.route(`**/jobs/${target}/match`,async route=>{if(!used){used=true;expect((await request.post(`/jobs/${target}/extract`,{data:{}})).ok()).toBeTruthy();}await route.continue();});
      }
      await start(kind);const partial=await journal(page,kind);
      expect(totals(partial)).toEqual({completed:index,failed:1,unattempted:2-index,uncertain:0});
      await visibleCounts(kind,totals(partial));await expect(row(page,kind,target)).toContainText(kind==='extraction'?'501':'409');
      const failure=partial.items[index].attempts.at(-1),saved=await get(request,`/operations/${failure.operation_id}`);expect(saved.state).toBe('rejected');
      const partialServer=await serverState(request,ids,partial);await counters(kind==='extraction'?index:3);
      if(index===1){
        await article(page,kind).scrollIntoViewIfNeeded();await page.waitForTimeout(800);
        if(info.project.name==='mobile-chromium'){
          await article(page,kind).locator('.table-wrap').evaluate(element=>{element.scrollLeft=element.scrollWidth;});await page.waitForTimeout(800);
          await article(page,kind).locator('.table-wrap').evaluate(element=>{element.scrollLeft=0;});
        }
      }
      if(kind==='extraction')expect((await request.post(`/jobs/${target}/snapshots`,{data:{text:fixture.sources[target]}})).ok()).toBeTruthy();
      await click(page,`Use current sources for remaining ${kind}`);await click(page,`Continue remaining ${kind}`);
      const final=await retainCompleted(kind,partial);
      expect(final.items[index].attempts.some(a=>a.operation_id===failure.operation_id&&a.state==='rejected')).toBeTruthy();
      await record(kind,`failure_${['first','middle','last'][index]}`,before,partial,partialServer,final);
    });
  }

  for(const kind of ['extraction','matching'])for(const mode of ['before_delivery','after_commit_lookup_lost_reload']){
    await test.step(`${kind}: ${mode}`,async()=>{
      await setup(kind);const before=kind==='matching'?await serverState(request,ids):{registered:0,current_extracted:0,histories:{}};
      const path=`/jobs/${ids[1]}/${kind==='matching'?'match':'extract'}`;let used=false,blockRefresh=false;
      if(mode==='after_commit_lookup_lost_reload'){
        let failed=false,refreshFailed=false;
        await page.route('**/operations/*',async route=>{if(!failed&&route.request().method()==='GET'){failed=true;await route.abort('connectionclosed');}else await route.continue();});
        await page.route('**/v2/jobs',async route=>{if(blockRefresh&&!refreshFailed&&route.request().method()==='GET'){refreshFailed=true;await route.abort('connectionclosed');}else await route.continue();});
      }
      await page.route(`**${path}`,async route=>{if(used){await route.continue();return;}used=true;if(mode.startsWith('after_commit')){expect((await route.fetch()).ok()).toBeTruthy();blockRefresh=true;}await route.abort('connectionclosed');});
      await start(kind);const partial=await journal(page,kind);
      expect(totals(partial)).toEqual({completed:1,failed:0,unattempted:1,uncertain:1});
      if(mode.startsWith('after_commit'))await expect(article(page,kind)).toContainText('Authoritative counters unavailable');
      await visibleCounts(kind,totals(partial));await expect(page.getByRole('button',{name:`Continue remaining ${kind}`,exact:true})).toBeDisabled();
      const partialServer=await serverState(request,ids,partial),key=partial.items[1].attempts.at(-1).operation_id;
      await nav(page,'Job registry');await nav(page,'Overview');await visibleCounts(kind,totals(partial));
      if(mode==='before_delivery')await click(page,'Retry same operation');
      else{
        await page.reload();await expect(page.locator('#operation-status')).toHaveAttribute('data-state','committed');await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
        expect((await journal(page,kind)).items[1].state).toBe('completed');
        const stored=await page.evaluate(()=>JSON.stringify({...sessionStorage}));expect(stored).not.toContain(fixture.sources[ids[1]]);expect(stored).not.toContain('production_evidence');
      }
      await click(page,`Continue remaining ${kind}`);const final=await retainCompleted(kind,partial);
      const writes=posts.filter(p=>p.path===path);expect(writes).toHaveLength(mode==='before_delivery'?2:1);expect(new Set(writes.map(p=>p.operation_id)).size).toBe(1);
      expect((await get(request,`/operations/${key}`)).execution_count).toBe(1);
      await record(kind,mode,before,partial,partialServer,final);
    });
  }

  for(const kind of ['extraction','matching'])await test.step(`${kind}: navigation during a real in-flight response`,async()=>{
    await setup(kind);const before=kind==='matching'?await serverState(request,ids):{registered:0,current_extracted:0,histories:{}};
    const path=`/jobs/${ids[1]}/${kind==='matching'?'match':'extract'}`;let used=false,release,arrived;
    const held=new Promise(resolve=>{release=resolve;}),ready=new Promise(resolve=>{arrived=resolve;});
    await page.route(`**${path}`,async route=>{if(used){await route.continue();return;}used=true;const real=await route.fetch();arrived();await held;await route.fulfill({response:real});});
    await page.getByRole('button',{name:kind==='extraction'?'Load synthetic corpus':'Match extracted corpus',exact:true}).click();await ready;
    const partial=await journal(page,kind),partialServer=await serverState(request,ids,partial);expect(partial.items[0].state).toBe('completed');expect(partial.items[1].state).toBe('uncertain');expect(partial.items[2].state).toBe('unattempted');
    await nav(page,'Job registry');await nav(page,'Overview');await expect(article(page,kind).locator('.batch-counts')).toContainText('1 running');release();
    await expect(article(page,kind).locator('.batch-counts')).toContainText('3 completed');await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
    const final=await retainCompleted(kind,partial);await record(kind,'navigation_in_flight',before,partial,partialServer,final);
  });

  await test.step('Stale source is rejected before extraction and explicitly replanned without repeating completed jobs',async()=>{
    const kind='extraction';await setup(kind);const before={registered:0,current_extracted:0,histories:{}};let used=false;
    await page.route(`**/jobs/${ids[1]}/extract`,async route=>{if(!used){used=true;expect((await request.post(`/jobs/${ids[1]}/snapshots`,{data:{text:`<main>${fixture.sources[ids[1]]}</main>`,format:'html'}})).ok()).toBeTruthy();}await route.continue();});
    await start(kind);const partial=await journal(page,kind);expect(totals(partial)).toEqual({completed:1,failed:1,unattempted:1,uncertain:0});await expect(row(page,kind,ids[1])).toContainText('source selection is stale');
    const partialServer=await serverState(request,ids,partial);expect(partialServer.histories[ids[1]].extractions).toHaveLength(0);
    await click(page,'Use current sources for remaining extraction');await click(page,'Continue remaining extraction');const final=await retainCompleted(kind,partial);await record(kind,'stale_source',before,partial,partialServer,final);
  });

  await test.step('Changed candidate selection blocks continuation until the captured revision is restored',async()=>{
    const kind='matching';await setup(kind);const before=await serverState(request,ids);let used=false;
    await page.route(`**/jobs/${ids[1]}/match`,async route=>{if(!used){used=true;expect((await request.post(`/jobs/${ids[1]}/extract`,{data:{}})).ok()).toBeTruthy();}await route.continue();});
    await start(kind);const partial=await journal(page,kind),partialServer=await serverState(request,ids,partial);
    await click(page,'Use current sources for remaining matching');
    await page.getByLabel('Candidate JSON',{exact:true}).fill(JSON.stringify({...fixture.candidate,complete:!fixture.candidate.complete}));await click(page,'Validate & save profile');
    const changedRevision=await page.getByLabel('Saved revision').inputValue();expect(changedRevision).not.toBe(partial.selection.profile_revision_id);
    const attempts=posts.length;await click(page,'Continue remaining matching');expect(posts).toHaveLength(attempts);await expect(article(page,kind)).toContainText('Candidate selection changed');
    await click(page,'Restore batch candidate revision');await expect(page.getByLabel('Saved revision')).toHaveValue(partial.selection.profile_revision_id);
    await click(page,'Continue remaining matching');const final=await retainCompleted(kind,partial);await record(kind,'stale_revision',before,partial,partialServer,final,{rejected_revision:changedRevision});
  });

  await test.step('Empty extraction and matching plans send no domain mutation',async()=>{
    for(const kind of ['extraction','matching']){
      await setup(kind,{empty:true});await start(kind);const batch=await journal(page,kind);expect(batch.items).toHaveLength(0);expect(posts).toHaveLength(0);
      await expect(article(page,kind)).toContainText('No eligible items');expect((await get(request,'/jobs')).jobs).toHaveLength(0);
      rows.push({project:info.project.name,kind,scenario:'empty',before:{registered:0,current_extracted:0},partial:{counts:totals(batch),items:[]},resumed:{counts:totals(batch),items:[],server:{registered:0,current_extracted:0}},browser_mutation_posts:[]});
    }
  });
  expect(rows).toHaveLength(16);expect(errors).toEqual([]);
  const path=info.outputPath('batch-comparison.json');await writeFile(path,JSON.stringify({schema_version:1,mode:'authored fixture replay; actual API/database operations and transport interruptions',rows},null,2));await info.attach('batch-comparison',{path,contentType:'application/json'});
  await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await page.screenshot({path:info.outputPath('successful-screen.png'),fullPage:true});await page.waitForTimeout(1200);
});
