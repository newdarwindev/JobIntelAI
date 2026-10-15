import {test,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';

const get=async(request,path)=>{const response=await request.get(path);expect(response.ok()).toBeTruthy();return response.json();};
const click=async(page,name)=>{await page.getByRole('button',{name,exact:true}).click();await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};
const nav=async(page,name)=>{await page.getByRole('navigation').getByRole('link',{name,exact:true}).click();await expect(page.getByRole('heading',{level:1,name,exact:true})).toBeVisible();await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};

test('UI15 | Bounded registry discovery and saved-history pagination',async({page,request,browser},info)=>{
  test.setTimeout(240000);info.annotations.push({type:'browser-version',description:browser.version()});
  expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();expect((await request.post('/ui/reset')).ok()).toBeTruthy();
  const source=await readFile(new URL('../../data/sample_jobs/SYN-01.txt',import.meta.url),'utf8');
  const empty=await readFile(new URL('../../data/sample_jobs/SYN-18.txt',import.meta.url),'utf8');
  const jobs=Array.from({length:45},(_,i)=>({job_id:`CAT-${String(i).padStart(2,'0')}`,company:`Authored catalogue ${i}`,role:'Engineer',official_url:i===44?'https://example.com/authored-denied':null}));
  expect((await request.post('/jobs/import',{data:{jobs}})).ok()).toBeTruthy();
  const snapshots=[],runs=[],revisions=[],evaluations=[];
  for(let i=0;i<23;i++){
    const saved=await request.post('/jobs/CAT-44/snapshots',{data:{text:i===22?source:`Authored inert historical text ${i} <script>window.__catalogueExecuted=true</script>`}});expect(saved.status()).toBe(201);snapshots.push((await saved.json()).snapshot_id);
    const profile={profile_id:'catalogue-profile',evidence:[{skill:'Python',current_capability:'strong',production_evidence:'none',source:'synthetic://catalogue-profile',quote:`Authored capability statement ${i}.`}]};
    const revision=await request.post('/candidates/import',{data:profile});expect(revision.status()).toBe(201);revisions.push((await revision.json()).profile_revision_id);
    const evaluation=await request.post('/evaluate',{data:{configurations:['fixture_normalized']}});expect(evaluation.ok()).toBeTruthy();evaluations.push((await evaluation.json()).evaluation_run_id);
    const denied=await request.post('/jobs/CAT-44/fetch',{data:{}});expect(denied.status()).toBe(403);
  }
  for(let i=0;i<23;i++){const result=await request.post('/jobs/CAT-44/extract',{data:{}});expect(result.ok()).toBeTruthy();runs.push((await result.json()).run_id);}
  expect((await request.post('/jobs/CAT-43/snapshots',{data:{text:empty}})).status()).toBe(201);expect((await request.post('/jobs/CAT-43/extract',{data:{}})).ok()).toBeTruthy();
  const observed=[],pending=[],errors=[],legacy=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{const path=new URL(r.url()).pathname;if(r.method()==='GET'&&(path==='/jobs'||/^\/jobs\/[^/]+\/history$/.test(path)||/^\/candidates\/[^/]+\/revisions$/.test(path)||path==='/evaluation-runs'))legacy.push(path);});
  page.on('response',response=>{const url=new URL(response.url());if(!url.pathname.startsWith('/v2/')||!response.ok())return;pending.push(response.json().then(body=>{if(!body.page)return;const items=body.items??body.jobs;expect(items.length).toBeLessThanOrEqual(20);expect(JSON.stringify(items)).not.toMatch(/clean_text|raw_text|"requirements"|"profile"|"predictions"/);observed.push({path:url.pathname,count:items.length,has_more:body.page.has_more});}));});
  await page.goto('/ui/');await expect(page.locator('.metrics')).toContainText('45');
  await nav(page,'Job registry');await expect(page.locator('#registry-table tbody tr')).toHaveCount(20);
  await page.getByLabel('Registry content').fill('unsaved authored registry draft');
  await click(page,'Next postings');await expect(page.locator('#registry-table')).toContainText('CAT-20');await expect(page.getByLabel('Registry content')).toHaveValue('unsaved authored registry draft');
  await click(page,'Next postings');await expect(page.locator('#registry-table tbody tr')).toHaveCount(5);await expect(page.locator('#registry-table')).toContainText('CAT-44');
  const lastRoute=page.url();await page.reload();await expect(page.locator('#registry-table tbody tr')).toHaveCount(5);expect(page.url()).toBe(lastRoute);
  await click(page,'Previous postings');await expect(page.locator('#registry-table')).toContainText('CAT-20');await click(page,'First postings');await expect(page.locator('#registry-table')).toContainText('CAT-00');
  await page.getByLabel('Search postings').fill('CAT-44');await expect(page.locator('#registry-table tbody tr')).toHaveCount(1);await page.reload();await expect(page.getByLabel('Search postings')).toHaveValue('CAT-44');
  await page.getByLabel('Pipeline state').selectOption('Source ready');await expect(page.getByText('No matching postings',{exact:true})).toBeVisible();await page.getByLabel('Pipeline state').selectOption('Extracted');await expect(page.locator('#registry-table tbody tr')).toHaveCount(1);
  await page.locator('#registry-table').getByRole('link',{name:'Inspect →'}).click();await expect(page.getByLabel('Selected posting')).toHaveValue('CAT-44');await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  await page.getByLabel('Posting source').fill('unsaved source draft retained during history reads');
  await page.getByText(/Snapshot & extraction history/).click();await click(page,'Next snapshots');await expect(page.locator('#history .history-item')).toHaveCount(3);await expect(page.getByLabel('Posting source')).toHaveValue('unsaved source draft retained during history reads');
  await click(page,'Inspect snapshot #'+snapshots[0]);await expect(page.locator('#selected-snapshot')).toContainText('Authored inert historical text 0');expect(await page.evaluate(()=>window.__catalogueExecuted)).toBeUndefined();
  await click(page,'First snapshots');await click(page,'Inspect snapshot #'+snapshots.at(-1));await expect(page.locator('#selected-snapshot')).toContainText('Run #'+runs.at(-1));await click(page,'Next extraction runs');await expect(page.locator('#selected-snapshot')).toContainText('Run #'+runs[0]);await expect(page.locator('#selected-snapshot')).not.toContainText('Run #'+runs.at(-1));await click(page,'First extraction runs');
  await page.getByText(/URL acquisition history/).click();await click(page,'Next acquisition attempts');await expect(page.locator('#acquisition-history .history-item')).toHaveCount(3);await expect(page.locator('#acquisition-history')).toContainText('access_denied');await click(page,'First acquisition attempts');
  await nav(page,'Candidate evidence');await page.getByLabel('Saved profile ID').fill('catalogue-profile');await click(page,'Load saved revisions');await click(page,'Next revisions');await expect(page.getByLabel('Saved revision').locator('option')).toHaveCount(4);await page.getByLabel('Saved revision').selectOption(revisions[0]);await expect(page.getByLabel('Candidate JSON')).toHaveValue(/Authored capability statement 0\./);
  await nav(page,'Evaluation lab');await expect(page.locator('#evaluation-catalogue .history-item')).toHaveCount(20);await click(page,'Next evaluations');await click(page,'Inspect evaluation #'+evaluations[0]);await expect(page.getByLabel('Saved evaluation run ID')).toHaveValue(evaluations[0]);await click(page,'First evaluations');
  // An actual read failure retains the visible source draft; explicit retry recovers.
  await page.evaluate(()=>{location.hash='workbench?job=CAT-44';});await expect(page.getByLabel('Posting source')).toHaveValue('unsaved source draft retained during history reads');
  let failed=false;await page.route('**/v2/jobs/CAT-44/snapshots?*',async route=>{if(!failed){failed=true;await route.abort('connectionclosed');}else await route.continue();});
  await page.getByText(/Snapshot & extraction history/).click();await click(page,'Next snapshots');await expect(page.locator('#notice')).toContainText('Connection unavailable');await expect(page.getByLabel('Posting source')).toHaveValue('unsaved source draft retained during history reads');await click(page,'Next snapshots');await expect(page.locator('#history .history-item')).toHaveCount(3);await page.unrouteAll({behavior:'wait'});
  await nav(page,'Candidate evidence');await click(page,'Match extracted corpus');await expect(page.locator('#notice')).toContainText('Matched 2 current extracted jobs');
  const batch=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('jobintel-corpus-batches')).find(b=>b.kind==='matching'));expect(batch.items.map(i=>i.jobId)).toEqual(['CAT-43','CAT-44']);expect(batch.items.every(i=>i.state==='completed')).toBeTruthy();
  await page.evaluate(()=>{location.hash='workbench?job=CAT-44';});await expect(page.getByLabel('Posting source')).toHaveValue('unsaved source draft retained during history reads');await click(page,'Save immutable snapshot');await expect(page.getByText('No current extraction',{exact:true})).toBeVisible();const changed=await get(request,'/v2/jobs?q=CAT-44');expect(changed.jobs[0].extraction).toBeNull();expect(changed.jobs[0].snapshot.id).not.toBe(snapshots.at(-1));
  await Promise.all(pending);expect(errors).toEqual([]);expect(legacy).toEqual([]);expect(observed.length).toBeGreaterThan(10);
  const evidence={project:info.project.name,registry_jobs:45,snapshots:snapshots.length,runs:runs.length,revisions:revisions.length,evaluations:evaluations.length,legacy_bulk_reads:legacy,observed};
  const file=info.outputPath('catalogue-observations.json');await writeFile(file,JSON.stringify(evidence,null,2)+'\n');await info.attach('catalogue-observations',{path:file,contentType:'application/json'});await page.waitForTimeout(1200);
});
