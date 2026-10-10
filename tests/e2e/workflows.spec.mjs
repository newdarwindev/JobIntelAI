import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
const data = async path => readFile(new URL(`../../data/${path}`,import.meta.url),'utf8');
const source = id => data(`sample_jobs/${id}.txt`);
const candidate = async () => JSON.parse(await data('sample_candidate.json'));
const notice = page => page.getByRole('status');
const click = async (page,name) => {await page.getByRole('button',{name,exact:true}).click();await expect(page.locator('main')).toHaveAttribute('aria-busy','false');};
const nav = async (page,view) => {await page.getByRole('navigation').getByRole('link',{name:view,exact:true}).click();await expect(page.getByRole('heading',{level:1,name:view,exact:true})).toBeVisible();};
const inspect = async (page,id) => {await nav(page,'Source & extraction');await page.getByLabel('Selected posting').selectOption(id);await expect(page.getByLabel('Selected posting')).toHaveValue(id);};
async function importSample(page){await nav(page,'Job registry');await click(page,'Load sample registry');await click(page,'Import registry');await expect(notice(page)).toContainText('Imported 20');}
async function capture(page,id,extract=true){await inspect(page,id);await click(page,'Load synthetic source');await click(page,'Save immutable snapshot');if(extract){await click(page,'Extract requirements');await expect(page.getByText('No current extraction',{exact:true})).toHaveCount(0);}}
async function saveProfile(page,profile){await nav(page,'Candidate evidence');await page.getByLabel('Candidate JSON',{exact:true}).fill(JSON.stringify(profile,null,2));await page.getByLabel('This profile explicitly declares complete skill coverage').setChecked(profile.complete);await click(page,'Validate & save profile');await expect(notice(page)).toContainText('validated and activated');}
async function download(page,name){const event=page.waitForEvent('download');await click(page,name);const file=await event;return readFile(await file.path(),'utf8');}
test.beforeEach(async({page,request,browser},info)=>{
  info.annotations.push({type:'browser-version',description:browser.version()});
  expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();
  expect((await request.post('/ui/reset')).ok()).toBeTruthy();
  await page.goto('/ui/');
  await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
});
test.afterEach(async({page},info)=>{if(info.status===info.expectedStatus){await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await page.screenshot({path:info.outputPath('successful-screen.png'),fullPage:true});await page.waitForTimeout(1200);}});

test('UI01 | Atomic registry import and discovery',async({page,request})=>{
  await importSample(page);
  await click(page,'Load sample registry');await click(page,'Import registry');await expect(notice(page)).toContainText('20 duplicate(s)');
  await page.getByLabel('Search postings').fill('SYN-02');await expect(page.locator('#registry-table tbody tr')).toHaveCount(1);
  await page.getByLabel('Pipeline state').selectOption('Extracted');await expect(page.getByText('No matching postings',{exact:true})).toBeVisible();
  await page.getByLabel('Pipeline state').selectOption('all');await page.getByLabel('Search postings').fill('');
  await page.getByLabel('Import format').selectOption('json');
  const rows=[{job_id:'UI-NEW',company:'Authored Company',role:'Analyst',applied:false},{job_id:'SYN-01',company:'Conflict',role:'Different'}];
  await page.getByLabel('Registry content').fill(JSON.stringify(rows));await click(page,'Import registry');await expect(notice(page)).toContainText('409:');
  expect((await request.get('/jobs/UI-NEW')).status()).toBe(404);
  await page.getByLabel('Registry content').fill(JSON.stringify(rows.slice(0,1)));await click(page,'Import registry');await expect(notice(page)).toContainText('Imported 1');
  await page.getByLabel('Search postings').fill('UI-NEW');await expect(page.locator('#registry-table')).toContainText('No');
  await page.getByLabel('Import format').selectOption('csv');await page.getByLabel('Registry content').fill('job_id,company,role,applied\nBAD,Synthetic,Engineer,maybe\n');await click(page,'Import registry');await expect(notice(page)).toContainText('422:');
  await click(page,'Load sample registry');await click(page,'Import registry');await expect(notice(page)).toContainText('20 duplicate(s)');
  await page.getByLabel('Import format').selectOption('json');
  const urlJob={job_id:'UI-CANONICAL',company:'Authored URL identity',role:'Analyst',official_url:'https://example.com/jobs/canonical'};
  await page.getByLabel('Registry content').fill(JSON.stringify([urlJob]));await click(page,'Import registry');await expect(notice(page)).toContainText('Imported 1');
  const conflictBatch=[{job_id:'UI-URL-PARTIAL',company:'Authored partial URL batch',role:'Engineer'},{job_id:'UI-URL-CONFLICT',company:'Authored distinct opening',role:'Engineer',official_url:'HTTPS://EXAMPLE.COM:443/jobs/canonical#fragment'}];
  await page.getByLabel('Import format').selectOption('json');
  await page.getByLabel('Registry content').fill(JSON.stringify(conflictBatch));await click(page,'Import registry');await expect(notice(page)).toContainText('409:');
  for(const row of conflictBatch)expect((await request.get(`/jobs/${row.job_id}`)).status()).toBe(404);
  await page.reload();expect((await request.get('/jobs/UI-CANONICAL')).ok()).toBeTruthy();
});

test('UI02 | Source capture, URL fallback and immutable history',async({page,request})=>{
  await importSample(page);await inspect(page,'SYN-01');
  await click(page,'Extract requirements');await expect(notice(page)).toContainText('409:');
  await page.getByLabel('Source format').selectOption('html');
  const text=await source('SYN-01');
  await page.getByLabel('Posting source').fill(`<nav>Ignore navigation</nav><main>${text}</main><script>window.__executed=true</script>`);
  await click(page,'Save immutable snapshot');let job=(await request.get('/jobs/SYN-01')).json();job=await job;
  expect(job.snapshot.clean_text).not.toContain('Ignore navigation');expect(job.snapshot.clean_text).not.toContain('window.__executed');
  await click(page,'Extract requirements');await expect(page.getByRole('heading',{name:'PostgreSQL',exact:true})).toBeVisible();
  await click(page,'Load synthetic source');await click(page,'Save immutable snapshot');await click(page,'Save immutable snapshot');
  const before=await (await request.get('/jobs/SYN-01')).json();
  await page.getByLabel('Posting source').fill('Authored changed posting with no known fixture.');await click(page,'Save immutable snapshot');
  await expect(page.getByText('No current extraction',{exact:true})).toBeVisible();
  const after=await (await request.get('/jobs/SYN-01')).json();expect(after.snapshot.id).not.toBe(before.snapshot.id);expect(after.extraction).toBeNull();
  await page.getByText(/Snapshot & extraction history/).click();await expect(page.locator('#history')).toContainText('Run #');
  await click(page,'Try URL acquisition');await expect(notice(page)).toContainText('manual source editor');
  await click(page,'Load synthetic source');await click(page,'Save immutable snapshot');await click(page,'Extract requirements');
  await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>window.__executed)).toBeUndefined();
  await page.reload();await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  await nav(page,'Job registry');await page.getByLabel('Import format').selectOption('json');await page.getByLabel('Registry content').fill(JSON.stringify([{job_id:'UI-URL',company:'Authored URL fallback',role:'Engineer',official_url:'https://example.com/authored-job'}]));await click(page,'Import registry');
  await inspect(page,'UI-URL');await click(page,'Try URL acquisition');await expect(notice(page)).toContainText('URL source saved');
  const fetched=await (await request.get('/jobs/UI-URL')).json();expect(fetched.snapshot.fetch_status).toBe('http');expect(fetched.snapshot.clean_text).toBe(text.trim());
  const attempts=(await (await request.get('/jobs/UI-URL/history')).json()).acquisition_attempts;
  expect(attempts).toHaveLength(2);expect(attempts.find(a=>a.status==='success').snapshot_id).toBe(fetched.snapshot.id);expect(attempts.find(a=>a.status==='redirect').http_status).toBe(302);
  const diagnostics=await (await request.get('/acquisition-fixture-diagnostics')).json();
  expect(diagnostics.origin.events.some(e=>e.kind==='tls'&&e.hostname==='example.com')).toBeTruthy();
  expect(diagnostics.origin.events.some(e=>e.scenario==='/authored-final'&&e.tls&&e.authority==='example.com')).toBeTruthy();
  expect(diagnostics.proxy.events.some(e=>e.method==='CONNECT'&&e.pin==='93.184.216.34'&&e.disposition==='forwarded')).toBeTruthy();
  expect(await page.evaluate(()=>window.__fetched)).toBeUndefined();
  await click(page,'Extract requirements');await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  for(const [id,path] of [['UI-DENIED','authored-denied'],['UI-JS','authored-js']]){
    await nav(page,'Job registry');await page.getByLabel('Import format').selectOption('json');await page.getByLabel('Registry content').fill(JSON.stringify([{job_id:id,company:`Authored ${id}`,role:'Acquisition recovery',official_url:`https://example.com/${path}`} ]));await click(page,'Import registry');
    await inspect(page,id);await page.getByLabel('Posting source').fill(text);await click(page,'Save immutable snapshot');await click(page,'Extract requirements');
    const prior=await (await request.get(`/jobs/${id}`)).json();
    await page.getByLabel('Posting source').fill('Authored unsaved manual recovery text.');
    await click(page,'Try URL acquisition');await expect(notice(page)).toContainText(id==='UI-DENIED'?'403:':'422:');await expect(notice(page)).toContainText('manual source editor');
    await expect(page.getByLabel('Posting source')).toHaveValue('Authored unsaved manual recovery text.');
    expect((await (await request.get(`/jobs/${id}`)).json()).extraction.run_id).toBe(prior.extraction.run_id);
    await page.getByText(/URL acquisition history/).click();await expect(page.locator('#acquisition-history')).toContainText(id==='UI-DENIED'?'access_denied':'js_only');
    expect((await request.patch(`/jobs/${id}/history`,{data:{snapshots:[]}})).status()).toBe(405);
    await page.reload();await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
    await page.getByText(/URL acquisition history/).click();await expect(page.locator('#acquisition-history')).toContainText('failed');
    await page.getByLabel('Posting source').fill(text);await click(page,'Save immutable snapshot');await click(page,'Extract requirements');await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  }
});

test('UI03 | Grounded extraction, aliases and operators',async({page,request})=>{
  await importSample(page);await capture(page,'SYN-01');
  await expect(page.locator('.requirement').filter({hasText:'PostgreSQL'})).toContainText('PREFERRED');
  await page.getByRole('button',{name:'Highlight source quote',exact:true}).first().click();await expect(page.locator('mark')).toHaveText('Python is required.');
  const exported=JSON.parse(await download(page,'Export evidence JSON'));
  expect(exported).toEqual(await (await request.post('/exports',{data:{kind:'evidence',job_ids:['SYN-01']}})).json());
  expect(exported.rows[0].requirement_id).toBeTruthy();
  expect(exported.extraction.provenance).toMatchObject({provider:'fixture',configuration:'fixture_normalized',schema_version:2,model:null,usage:null,prompt_version:null});
  expect(exported.extraction.provenance.source_sha256).toBe(exported.snapshot.content_hash);
  expect(exported.extraction.provenance.taxonomy_sha256).toHaveLength(64);
  for(const r of exported.extraction.requirements)expect(Array.from(exported.snapshot.clean_text).slice(r.evidence.start,r.evidence.end).join('')).toBe(r.evidence.quote);
  await page.getByLabel('Extraction configuration').selectOption('fixture_raw');await click(page,'Extract requirements');await expect(page.getByRole('heading',{name:'Postgres',exact:true})).toBeVisible();
  await capture(page,'SYN-02');await expect(page.locator('.requirement')).toContainText('ANY');await expect(page.getByRole('heading',{name:'AWS OR Azure',exact:true})).toBeVisible();
  await capture(page,'SYN-03');await expect(page.locator('.requirement')).toContainText('ALL');await expect(page.getByRole('heading',{name:'Python AND SQL',exact:true})).toBeVisible();
  // Every bundled posting is replayed through the browser-driven corpus action.
  await nav(page,'Overview');await click(page,'Load synthetic corpus');
  await inspect(page,'SYN-10');
  await expect(page.locator('.metadata-facts')).toContainText('Geography: Georgia');
  await expect(page.locator('.metadata-facts')).toContainText('Work mode: remote');
  await click(page,'Highlight Geography quote');await expect(page.locator('mark')).toHaveText('Remote work within Georgia only.');
  const metadataExport=JSON.parse(await download(page,'Export evidence JSON'));
  expect(metadataExport.extraction.schema_version).toBe(2);
  for(const f of [metadataExport.extraction.geography,metadataExport.extraction.work_mode])
    expect(Array.from(metadataExport.snapshot.clean_text).slice(f.evidence.start,f.evidence.end).join('')).toBe(f.evidence.quote);
  await inspect(page,'SYN-12');await expect(page.locator('.metadata-facts')).toContainText('EU work authorization');
  const filterExport=JSON.parse(await download(page,'Export evidence JSON'));
  expect(filterExport.extraction.filters[0].kind).toBe('work_authorization');
  await inspect(page,'SYN-14');await expect(page.locator('.requirement').filter({hasText:'Production experience'})).toContainText('Production: Preferred');
  await expect(page.locator('.requirement').filter({hasText:'Production experience'})).toContainText('Experience obligation: PREFERRED');
  await inspect(page,'SYN-15');await expect(page.locator('.requirement')).toContainText('Go 1.23+');
  const versionExport=JSON.parse(await download(page,'Export evidence JSON'));
  expect(versionExport.extraction.requirements[0].version_constraints[0]).toMatchObject({product:'Go',comparator:'GTE',version:'1.23',raw_text:'Golang 1.23+'});
  await inspect(page,'SYN-18');await expect(page.getByText('No candidate requirements',{exact:true})).toBeVisible();
  await inspect(page,'SYN-20');
  const unicodeExport=JSON.parse(await download(page,'Export evidence JSON'));
  expect(unicodeExport.extraction.requirements).toHaveLength(1);expect(unicodeExport.snapshot.clean_text).toContain('café');
  for(const r of unicodeExport.extraction.requirements)expect(Array.from(unicodeExport.snapshot.clean_text).slice(r.evidence.start,r.evidence.end).join('')).toBe(r.evidence.quote);
  // Inject an authored API read fixture with a non-BMP prefix to catch UTF-16 slicing.
  const unicodeText='🧪 Authored source\nPython is required.';
  const start=Array.from(unicodeText).length-Array.from('Python is required.').length;
  const synthetic={...unicodeExport,job_id:'UI-UNICODE',snapshot:{...unicodeExport.snapshot,clean_text:unicodeText},extraction:{...unicodeExport.extraction,requirements:[{...unicodeExport.extraction.requirements[0],evidence:{start,end:Array.from(unicodeText).length,quote:'Python is required.'}}]}};
  await page.route('**/jobs',route=>route.fulfill({json:{jobs:[synthetic]}}));await page.route('**/jobs/UI-UNICODE/history',route=>route.fulfill({json:{job_id:'UI-UNICODE',snapshots:[]}}));
  await page.goto('/ui/?read-fixture=unicode#workbench?job=UI-UNICODE');await expect(page.getByLabel('Selected posting')).toHaveValue('UI-UNICODE');await click(page,'Highlight source quote');await expect(page.locator('mark')).toHaveText('Python is required.');
});

test('UI04 | Candidate evidence and four matching states',async({page,request})=>{
  await nav(page,'Overview');await click(page,'Load synthetic corpus');
  await saveProfile(page,await candidate());await page.getByLabel('Selected posting').selectOption('SYN-01');await click(page,'Match selected posting');
  await expect(page.locator('.status-totals')).toContainText('COVERED 1');await expect(page.locator('.status-totals')).toContainText('UNKNOWN 1');
  await expect(page.locator('main')).toContainText('Authored and operated a Python service.');
  await page.getByLabel('Selected posting').selectOption('SYN-04');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('PARTIAL 1');await expect(page.locator('main')).toContainText('production limited');
  await page.getByLabel('Selected posting').selectOption('SYN-05');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('UNKNOWN 1');
  await page.getByLabel('Selected posting').selectOption('SYN-15');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('UNKNOWN 1');
  await page.getByLabel('Selected posting').selectOption('SYN-02');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('PARTIAL 1');
  const complete={...(await candidate()),complete:true};await saveProfile(page,complete);await page.getByLabel('Selected posting').selectOption('SYN-03');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('MISSING 1');
  const any={profile_id:'authored-any',complete:true,evidence:[{skill:'Azure',current_capability:'strong',production_evidence:'none',source:'synthetic://azure',quote:'Explicit strong Azure capability in this authored example.'}]};
  await saveProfile(page,any);await page.getByLabel('Selected posting').selectOption('SYN-02');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('COVERED 1');
  const conflicting={...(await candidate()),evidence:[...(await candidate()).evidence,{skill:'Python',current_capability:'none',production_evidence:'none',source:'synthetic://contradiction',quote:'Contradictory synthetic record.'}]};
  await saveProfile(page,conflicting);await page.getByLabel('Selected posting').selectOption('SYN-01');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('UNKNOWN 2');
  await page.getByLabel('Candidate JSON',{exact:true}).fill('{"profile_id":"bad","evidence":[{"skill":"Python"}]}');await click(page,'Validate & save profile');await expect(notice(page)).toContainText('422:');
  await saveProfile(page,await candidate());await click(page,'Match extracted corpus');await expect(notice(page)).toContainText('Matched 20');
  const matched=JSON.parse(await download(page,'Export matches JSON'));expect(matched.snapshot_id).toBeTruthy();expect(matched.run_id).toBeTruthy();expect(matched.matches[0].requirement_id).toBeTruthy();
  expect(matched.match_run_id).toBeTruthy();expect(matched.profile_revision_id).toBeTruthy();
  const matchCsv=await download(page,'Export matches CSV');
  expect(matchCsv).toEqual(await (await request.post('/exports',{data:{kind:'matches',format:'csv',job_ids:['SYN-01'],profile_id:matched.profile_id,profile_revision_id:matched.profile_revision_id}})).text());
  expect(matchCsv).toContain(matched.match_run_id);expect(matchCsv).toContain('"UNKNOWN"');
  const originalRevision=matched.profile_revision_id;
  const dated={...(await candidate()),tenure_complete:true,tenure:[{skill:'Python',start:'2020-01-01',end:'2024-01-01',source:'synthetic://dated-ui',quote:'Authored Python experience from 2020 to 2024.'}],eligibility:[{kind:'location',value:'Georgia',status:'confirmed',observed_on:'2020-01-01',source:'synthetic://location-ui',quote:'Authored current Georgia location statement.'}]};
  await saveProfile(page,dated);await page.getByLabel('Selected posting').selectOption('SYN-05');await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('COVERED 1');
  const datedMatch=JSON.parse(await download(page,'Export matches JSON'));expect(datedMatch.profile_revision_id).not.toBe(originalRevision);
  await page.reload();await expect(page.getByLabel('Saved revision')).toHaveValue(datedMatch.profile_revision_id);await expect(page.getByLabel('Candidate JSON',{exact:true})).toContainText('synthetic://dated-ui');
  await page.getByLabel('Selected posting').selectOption('SYN-05');await click(page,'Match selected posting');const reloaded=JSON.parse(await download(page,'Export matches JSON'));expect(reloaded.profile_revision_id).toBe(datedMatch.profile_revision_id);expect(reloaded.match_run_id).not.toBe(datedMatch.match_run_id);expect(reloaded.matches).toEqual(datedMatch.matches);
  expect(await (await request.get(`/match-runs/${datedMatch.match_run_id}`)).json()).toMatchObject({profile_revision_id:datedMatch.profile_revision_id,snapshot_id:datedMatch.snapshot_id});
  await page.getByLabel('Saved revision').selectOption(originalRevision);await expect(notice(page)).toContainText('Saved revision selected');await expect(page.getByText('No current match',{exact:true})).toBeVisible();await click(page,'Match selected posting');await expect(page.locator('.status-totals')).toContainText('UNKNOWN 1');
  await page.getByLabel('Saved revision').selectOption(datedMatch.profile_revision_id);await expect(notice(page)).toContainText('Saved revision selected');await page.getByLabel('Selected posting').selectOption('SYN-10');await click(page,'Match selected posting');await expect(page.getByRole('heading',{name:'Location & eligibility'})).toBeVisible();await expect(page.locator('main')).toContainText('Authored current Georgia location statement.');
  const located=JSON.parse(await download(page,'Export matches JSON'));expect(located.eligibility[0].status).toBe('COVERED');

});

test('UI05 | Corpus slices, gaps and safe provenance exports',async({page,request})=>{
  await nav(page,'Corpus analytics');await expect(page.getByText('N = 0',{exact:true}).first()).toBeVisible();
  await nav(page,'Overview');await click(page,'Load synthetic corpus');await saveProfile(page,await candidate());await click(page,'Match extracted corpus');
  await nav(page,'Corpus analytics');await expect(page.locator('main')).toContainText('5/20');
  const report=JSON.parse(await download(page,'Export corpus JSON'));expect(report.N).toBe(20);expect(report.skills.find(s=>s.skill==='Python').n).toBe(5);expect(report.gaps.N).toBe(20);expect(report.clusters.N).toBe(20);
  const selected={profile_id:report.selection.profile_id,profile_revision_id:report.selection.profile_revision_id};
  expect(report).toEqual(await (await request.get(`/analytics/skills?${new URLSearchParams(selected)}`)).json());
  const savedExport=await (await request.post('/exports',{data:{kind:'skills',...selected}})).json();for(const key of ['skills','clusters','gaps'])expect(report[key]).toEqual(savedExport[key]);
  expect(Object.values(report.coverage.buckets).reduce((a,b)=>a+b,0)).toBe(20);expect(report.coverage.buckets.successfully_empty).toBeGreaterThan(0);
  expect(report.alternatives.find(g=>g.skills.join(' OR ')==='AWS OR Azure')).toBeTruthy();
  expect(report.skills.find(s=>s.skill==='Azure')).toBeUndefined();
  const csv=await download(page,'Export skills CSV');expect(csv).toContain('"Python","20","5","3","1","1","0"');
  expect(csv).toEqual(await (await request.post('/exports',{data:{kind:'skills',format:'csv',...selected}})).text());
  expect(csv).toContain(selected.profile_revision_id);expect(csv).toContain('"run_ids"');
  await page.reload();
  const restored=JSON.parse(await download(page,'Export corpus JSON'));expect(restored).toEqual(report);await expect(page.locator('main')).toContainText('Saved match runs · denominator = 20');
  await page.getByLabel('Work mode slice').selectOption('yes');const remote=JSON.parse(await download(page,'Export corpus JSON'));expect(remote.N).toBe(1);expect(remote.jobs[0].job_id).toBe('SYN-10');expect(remote.gaps.N).toBe(1);expect(remote.selection.remote).toBe(true);
  expect(remote).toEqual(await (await request.get(`/analytics/skills?remote=true&${new URLSearchParams(selected)}`)).json());expect(await download(page,'Export skills CSV')).toEqual(await (await request.post('/exports',{data:{kind:'skills',format:'csv',remote:true,...selected}})).text());
  await page.getByLabel('Work mode slice').selectOption('no');const nonremote=JSON.parse(await download(page,'Export corpus JSON'));expect(nonremote.N).toBe(1);expect(nonremote.jobs[0].job_id).toBe('SYN-11');expect(nonremote.jobs[0].extraction.work_mode.value).toBe('onsite');expect(nonremote.gaps.N).toBe(1);expect(nonremote.coverage.excluded).toBe(19);expect(nonremote.coverage.success_fraction).toBe(1);
  expect(nonremote).toEqual(await (await request.get(`/analytics/skills?remote=false&${new URLSearchParams(selected)}`)).json());
  await nav(page,'Candidate evidence');await click(page,'Match selected posting');const individual=JSON.parse(await download(page,'Export matches JSON'));expect(individual.N).toBe(1);expect(individual.jobs[0].job_id).toBe('SYN-01');expect(individual.selection.remote).toBeNull();
  expect(await download(page,'Export matches CSV')).toEqual(await (await request.post('/exports',{data:{kind:'matches',format:'csv',job_ids:['SYN-01'],...selected}})).text());await nav(page,'Corpus analytics');
  await page.getByLabel('Work mode slice').selectOption('all');
  await saveProfile(page,{...await candidate(),complete:true});await click(page,'Match selected posting');await nav(page,'Corpus analytics');expect(JSON.parse(await download(page,'Export corpus JSON')).gaps.N).toBe(1);
  await nav(page,'Candidate evidence');await page.getByLabel('Saved revision').selectOption(selected.profile_revision_id);await expect(notice(page)).toContainText('Saved revision selected');await nav(page,'Corpus analytics');expect(JSON.parse(await download(page,'Export corpus JSON')).gaps.N).toBe(20);
  expect((await request.post('/jobs/import',{data:{jobs:[{job_id:'UI-ACQ-FAIL',company:'Authored denied source',role:'Recovery',official_url:'https://example.com/authored-denied'},{job_id:'UI-EXT-FAIL',company:'Authored failed extraction',role:'Recovery'},{job_id:'UI-PENDING',company:'Authored waiting source',role:'Recovery'}]}})).ok()).toBeTruthy();
  expect((await request.post('/jobs/UI-ACQ-FAIL/fetch')).status()).toBe(403);expect((await request.post('/jobs/UI-EXT-FAIL/snapshots',{data:{text:'Authored source with no replay extraction.'}})).ok()).toBeTruthy();expect((await request.post('/jobs/UI-EXT-FAIL/extract',{data:{}})).status()).toBe(501);
  await page.reload();const mixed=JSON.parse(await download(page,'Export corpus JSON'));expect(mixed.coverage.registered_selected).toBe(23);expect(mixed.coverage.failed).toBe(2);expect(mixed.coverage.pending).toBe(1);expect(mixed.N).toBe(20);await expect(page.locator('#coverage-accounting')).toContainText('acquisition failed 1');await expect(page.locator('#coverage-accounting')).toContainText('extraction failed 1');
  await page.getByLabel('Application slice').selectOption('yes');await expect(page.getByText('N = 0',{exact:true}).first()).toBeVisible();
  await page.getByLabel('Application slice').selectOption('all');await expect(page.locator('main')).toContainText('5/20');
  // User-controlled cells retain source IDs while spreadsheet prefixes are neutralized.
  expect((await request.post('/jobs/import',{data:{jobs:[{job_id:'UI-FORMULA',company:'=HYPERLINK("https://example.com")',role:'Authored export case',applied:true}]}})).ok()).toBeTruthy();
  expect((await request.post('/jobs/UI-FORMULA/snapshots',{data:{text:await source('SYN-01')}})).ok()).toBeTruthy();
  expect((await request.post('/jobs/UI-FORMULA/extract',{data:{}})).ok()).toBeTruthy();
  await page.reload();await expect(page.getByRole('heading',{name:'Corpus analytics',exact:true})).toBeVisible();await page.getByLabel('Application slice').selectOption('yes');
  const rows=await download(page,'Export requirements CSV');expect(rows).toContain("\"'=HYPERLINK");expect(rows).toContain('"UI-FORMULA"');expect(rows).toContain('"snapshot_id"');expect(rows).toContain('"evidence_start"');
  expect(rows).toEqual(await (await request.post('/exports',{data:{kind:'requirements',format:'csv',applied:true,...selected}})).text());
  const sliced=JSON.parse(await download(page,'Export corpus JSON'));expect(sliced.N).toBe(1);expect(sliced.jobs).toHaveLength(1);
  expect(sliced.matched_jobs_N).toBe(0);expect(sliced.selection.applied).toBe(true);
  const oldRun=sliced.jobs[0].extraction.run_id;
  expect((await request.post('/jobs/UI-FORMULA/snapshots',{data:{text:'Authored changed source for explicit export history.'}})).ok()).toBeTruthy();
  const current=JSON.parse(await download(page,'Export corpus JSON'));expect(current.N).toBe(0);expect(current.jobs[0].extraction).toBeNull();expect(current.coverage.stale).toBe(1);expect(current.coverage.excluded).toBe(23);
  await page.reload();await page.getByLabel('Application slice').selectOption('yes');await expect(page.locator('#coverage-accounting')).toContainText('stale 1');
  const historical=await (await request.post('/exports',{data:{kind:'requirements',historical:true,run_ids:[oldRun],applied:true,...selected}})).json();
  expect(historical.N).toBe(1);expect(historical.rows).toHaveLength(2);expect(historical.rows[0].run_id).toBe(oldRun);
});

test('UI06 | Fixture evaluation and honest unavailable metrics',async({page})=>{
  await nav(page,'Evaluation lab');await page.getByRole('checkbox',{name:'Raw aliases',exact:true}).uncheck();await page.getByRole('checkbox',{name:'Deterministic normalization',exact:true}).uncheck();await click(page,'Run fixture evaluation');await expect(notice(page)).toContainText('Select at least one');
  await page.getByRole('checkbox',{name:'Raw aliases',exact:true}).check();await page.getByRole('checkbox',{name:'Deterministic normalization',exact:true}).check();await click(page,'Run fixture evaluation');
  await expect(page.locator('main')).toContainText('18/22');await expect(page.locator('main')).toContainText('22/22');await expect(page.locator('main')).toContainText('Tokens: Unavailable');
  const report=JSON.parse(await download(page,'Export evaluation JSON'));expect(report.dataset_size).toBe(20);expect(report.results).toHaveLength(2);expect(report.mode).toContain('not live LLM quality');
  for(const r of report.results){expect(r.tokens).toBeNull();expect(r.estimated_cost).toBeNull();expect(r.metrics.semantic_hallucination_rate).toBeNull();expect(r.metrics.abstention_quality).toBeNull();}
  await page.getByRole('checkbox',{name:'Raw aliases',exact:true}).uncheck();await click(page,'Run fixture evaluation');const single=JSON.parse(await download(page,'Export evaluation JSON'));expect(single.results).toHaveLength(1);expect(single.results[0].configuration).toBe('fixture_normalized');
  await page.getByLabel('Evaluation dataset').selectOption('reviewed');await page.getByRole('checkbox',{name:'Raw aliases',exact:true}).uncheck();await click(page,'Run fixture evaluation');
  await expect(page.locator('main')).toContainText('20 succeeded · 5 failed');await expect(page.locator('#evaluation-diagnostics')).toContainText('REV-21: failed · provider_unavailable');
  const reviewed=JSON.parse(await download(page,'Export evaluation JSON'));expect(reviewed.dataset_size).toBe(25);expect(reviewed.review.independent).toBe(true);expect(reviewed.results[0].metrics.reviewed_metrics.matching_agreement.denominator).toBe(28);expect(reviewed.results[0].per_case).toHaveLength(25);
  await page.reload();await expect(page.getByLabel('Saved evaluation run ID')).toHaveValue(reviewed.evaluation_run_id);await expect(page.locator('main')).toContainText('20 succeeded · 5 failed');
  await page.getByLabel('Saved evaluation run ID').fill(report.evaluation_run_id);await click(page,'Load saved evaluation');await expect(page.locator('main')).toContainText('18/22');const restored=JSON.parse(await download(page,'Export evaluation JSON'));expect(restored).toEqual(report);
});

test('UI07 | Provider and connection failure recovery',async({page,request})=>{
  await importSample(page);await capture(page,'SYN-01');
  const original=await (await request.get('/jobs/SYN-01')).json();
  await page.getByLabel('Posting source').fill('An authored unsupported input with no replay hash.');await click(page,'Save immutable snapshot');await click(page,'Extract requirements');await expect(notice(page)).toContainText('501:');await expect(page.getByText('No current extraction',{exact:true})).toBeVisible();
  await nav(page,'Candidate evidence');await click(page,'Load synthetic candidate');await click(page,'Validate & save profile');await click(page,'Match selected posting');await expect(notice(page)).toContainText('409:');
  await inspect(page,'SYN-01');await click(page,'Load synthetic source');await click(page,'Save immutable snapshot');
  expect((await request.post('/responses-fixture/success')).ok()).toBeTruthy();await page.reload();
  await expect(page.locator('main')).toContainText('Responses contract emulator');
  await click(page,'Extract requirements');await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
  const emulated=await (await request.get('/jobs/SYN-01')).json();expect(emulated.extraction.provenance.execution_mode).toBe('emulator');expect(emulated.extraction.provenance.usage).toBeNull();
  await page.route('**/jobs/SYN-01/extract',route=>route.abort('connectionrefused'));await click(page,'Extract requirements');await expect(notice(page)).toContainText('Connection unavailable');await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();await page.unroute('**/jobs/SYN-01/extract');
  const latestSaved=await (await request.get('/jobs/SYN-01')).json();
  // The real API and adapter call the separately running authored HTTP emulator.
  for(const [scenario,httpStatus,code,retryable,count] of [['delay',504,'timeout',true,1],['quota',502,'quota',false,1],['refusal',422,'refusal',false,1],['server_error',502,'provider_failure',true,1],['invalid_evidence',422,'invalid_evidence',false,1],['malformed_json',502,'malformed_json',false,2],['connection_close',502,'provider_failure',true,1]]){
    expect((await request.post(`/responses-fixture/${scenario}`)).ok()).toBeTruthy();
    await click(page,'Extract requirements');await expect(notice(page)).toContainText(`${httpStatus}: extraction provider: ${code}`);
    await expect(notice(page)).toContainText(retryable?'Retry is available':'Review the failure before retrying');
    await expect(page.getByRole('heading',{name:'Python',exact:true})).toBeVisible();
    expect((await (await request.get('/jobs/SYN-01')).json()).extraction.run_id).toBe(latestSaved.extraction.run_id);
    const diagnostics=await (await request.get('/responses-fixture-diagnostics')).json();expect(diagnostics.request_count).toBe(count);expect(diagnostics.requests.every(r=>r.auth_valid&&r.schema_valid&&r.model_valid&&r.parameters_valid&&r.input_valid)).toBeTruthy();
  }
  expect((await request.post('/responses-fixture/success')).ok()).toBeTruthy();
  const history=await (await request.get('/jobs/SYN-01/history')).json();expect(history.snapshots.some(s=>s.runs.some(r=>r.run_id===original.extraction.run_id))).toBeTruthy();
  await click(page,'Extract requirements');await expect(notice(page)).toContainText('Extraction saved');
});

test('UI08 | Keyboard navigation, responsive layout and inert input',async({page,request},info)=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'Skip to content',exact:true})).toBeFocused();await page.keyboard.press('Enter');await expect(page.locator('main')).toBeFocused();
  await nav(page,'Job registry');const hostile='<img src=x onerror="window.__injected=true">';
  await page.getByLabel('Import format').selectOption('json');await page.getByLabel('Registry content').fill(JSON.stringify([{job_id:'UI-INERT',company:hostile,role:'Authored inert input'}]));await click(page,'Import registry');
  await expect(page.locator('#registry-table')).toContainText(hostile);expect(await page.evaluate(()=>window.__injected)).toBeUndefined();expect(await page.locator('#registry-table img').count()).toBe(0);
  await page.goto('/ui/#workbench?job=UI-INERT');await expect(page.getByLabel('Selected posting')).toHaveValue('UI-INERT');await page.getByLabel('Posting source').fill('Authored source <script>window.__injected=true</script>');await click(page,'Save immutable snapshot');
  await page.getByText(/Snapshot & extraction history/).click();await expect(page.locator('#history')).toContainText('<script>');expect(await page.locator('main script').count()).toBe(0);
  await page.reload();await expect(page.getByLabel('Selected posting')).toHaveValue('UI-INERT');
  expect(await (await request.get('/ui/config')).json()).toMatchObject({contract_version:1,demo:true,provider:'fixture',execution_mode:'fixture',live_llm:false,acquisition_mode:'fixture-policy-proxy',actions:{samples:true,reset:true,extract:true,evaluate:true}});
  const readiness=await (await request.get('/health')).json();expect(readiness.provider).toBe('fixture');expect(readiness.configuration).toBe('fixture_normalized');expect(readiness.live_llm).toBe(false);expect(readiness.acquisition).toMatchObject({ready:true,mode:'policy-proxy',local_destination_dns:false});
  for(const view of ['Overview','Job registry','Source & extraction','Candidate evidence','Corpus analytics','Evaluation lab']){await nav(page,view);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();await expect(page.getByRole('navigation').getByRole('link',{name:view,exact:true})).toHaveAttribute('aria-current','page');await page.getByRole('link',{name:'Skip to content',exact:true}).focus();await page.keyboard.press('Enter');await expect(page.locator('main')).toBeFocused();await expect(page.getByRole('heading',{name:view,level:1,exact:true})).toBeVisible();}
  expect(errors).toEqual([]);
  await page.screenshot({path:info.outputPath('responsive-layout.png'),fullPage:true});
});
