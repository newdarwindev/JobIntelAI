import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const click = async(page,name) => {
  await page.getByRole('button',{name,exact:true}).click();
  await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
};
const nav = async(page,name) => {
  await page.getByRole('navigation').getByRole('link',{name,exact:true}).click();
  await expect(page.getByRole('heading',{level:1,name,exact:true})).toBeVisible();
};
const openJob = async(page,id,wait=true) => {
  await page.evaluate(id=>{location.hash=`workbench?job=${encodeURIComponent(id)}`;},id);
  await expect(page.getByRole('heading',{level:1,name:'Source & extraction',exact:true})).toBeVisible();
  await expect(page.getByLabel('Selected posting')).toHaveValue(id);
  if(wait)await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
};
const sourceFields = async(page,draft) => {
  await expect(page.getByLabel('Posting source')).toHaveValue(draft.text);
  await expect(page.getByLabel('Source format')).toHaveValue(draft.format);
  await expect(page.getByLabel('Source URL (optional)')).toHaveValue(draft.url);
};
const writeSource = async(page,draft) => {
  await page.getByLabel('Posting source').fill(draft.text);
  await page.getByLabel('Source format').selectOption(draft.format);
  await page.getByLabel('Source URL (optional)').fill(draft.url);
};

// Delay delivery of an actual API response; the underlying mutation still runs.
async function holdResponse(page,path,method='POST') {
  let release,received,held=false;
  const gate=new Promise(resolve=>{release=resolve;});
  const ready=new Promise(resolve=>{received=resolve;});
  // Keep interception registered while later requests start after fulfillment.
  await page.route(`**${path}`,async route=>{
    if(held||route.request().method()!==method){await route.continue();return;}
    held=true;
    const response=await route.fetch();received(response.status());
    await gate;await route.fulfill({response});
  });
  return {ready,release};
}

test('UI12 | Scoped editor drafts, explicit discard and pending navigation',async({page,request,browser},info)=>{
  test.setTimeout(180000);
  info.annotations.push({type:'browser-version',description:browser.version()});
  expect((await request.post('/responses-fixture/fixture')).ok()).toBeTruthy();
  expect((await request.post('/ui/reset')).ok()).toBeTruthy();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const known=await readFile(new URL('../../data/sample_jobs/SYN-01.txt',import.meta.url),'utf8');
  const profile=JSON.parse(await readFile(new URL('../../data/sample_candidate.json',import.meta.url),'utf8'));
  const jobs=[
    {job_id:'DRAFT-A',company:'Authored A',role:'Engineer',official_url:'https://example.com/authored-job'},
    {job_id:'DRAFT-B',company:'Authored B',role:'Engineer'},
    {job_id:'DRAFT-DENIED',company:'Authored denied',role:'Engineer',official_url:'https://example.com/authored-denied'},
  ];
  expect((await request.post('/jobs/import',{data:{jobs}})).ok()).toBeTruthy();
  expect((await request.post('/jobs/DRAFT-A/snapshots',{data:{text:known}})).ok()).toBeTruthy();
  await page.goto('/ui/');await nav(page,'Job registry');

  await test.step('Registry failures, refresh, navigation, discard and successful import',async()=>{
    const conflict=JSON.stringify([{...jobs[0],company:'Authored registry draft marker'}]);
    await page.getByLabel('Import format').selectOption('json');
    await page.getByLabel('Registry content').fill(conflict);await click(page,'Import registry');
    await expect(page.getByRole('status')).toContainText('409:');
    await click(page,'Refresh');await nav(page,'Overview');await nav(page,'Job registry');
    await expect(page.getByLabel('Registry content')).toHaveValue(conflict);
    await expect(page.getByLabel('Import format')).toHaveValue('json');
    await expect(page.locator('[data-draft-note]')).toContainText('before reloading');
    await click(page,'Discard registry draft');
    await expect(page.getByLabel('Registry content')).toHaveValue('');
    await expect(page.getByLabel('Import format')).toHaveValue('csv');
    await expect(page.getByRole('button',{name:'Discard registry draft',exact:true})).toBeDisabled();
    await page.getByLabel('Registry content').fill('job_id,company,role\nDRAFT-NEW,Authored new,Engineer\n');
    await click(page,'Import registry');await expect(page.getByRole('status')).toContainText('Imported 1');
    await expect(page.getByLabel('Registry content')).toHaveValue('');
  });

  const a={text:'<main>Authored unsaved source marker A</main>',format:'html',url:'https://example.com/manual-a'};
  const b={text:'Authored unsaved source marker B',format:'text',url:'https://example.com/manual-b'};
  await openJob(page,'DRAFT-A');await writeSource(page,a);
  await openJob(page,'DRAFT-B');await writeSource(page,b);
  await nav(page,'Candidate evidence');
  profile.profile_id='draft-profile';profile.complete=false;
  await page.getByLabel('Candidate JSON',{exact:true}).fill(JSON.stringify(profile,null,2));
  await page.getByLabel('Saved profile ID').fill('authored-unsaved-lookup-marker');
  await page.getByLabel('This profile explicitly declares complete skill coverage').check();
  const candidateDraft=await page.getByLabel('Candidate JSON',{exact:true}).inputValue();
  await openJob(page,'DRAFT-A');await sourceFields(page,a);
  await click(page,'Refresh provider status');await sourceFields(page,a);
  await click(page,'Extract requirements');await sourceFields(page,a);
  await openJob(page,'DRAFT-B');await sourceFields(page,b);
  await nav(page,'Candidate evidence');
  await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(candidateDraft);
  await expect(page.getByLabel('Saved profile ID')).toHaveValue('authored-unsaved-lookup-marker');
  await expect(page.getByLabel('This profile explicitly declares complete skill coverage')).toBeChecked();
  await click(page,'Validate & save profile');
  await expect(page.getByRole('button',{name:'Discard candidate draft',exact:true})).toBeDisabled();
  const first=(await (await request.get('/candidates/draft-profile/revisions')).json()).revisions[0];

  await test.step('Candidate drafts follow saved revision scopes and survive matching',async()=>{
    const firstDraft=JSON.stringify({...first.profile,complete:false},null,2);
    await page.getByLabel('Candidate JSON',{exact:true}).fill(firstDraft);
    await page.getByLabel('Saved profile ID').fill('authored-first-revision-lookup');
    await page.getByLabel('Selected posting').selectOption('DRAFT-A');
    await expect(page).toHaveURL(/candidate\?job=DRAFT-A/);
    await click(page,'Match selected posting');
    await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(firstDraft);
    const second=await (await request.post('/candidates/import',{data:{...first.profile,complete:false}})).json();
    await page.getByLabel('Saved profile ID').fill('draft-profile');await click(page,'Load saved revisions');
    await page.getByLabel('Saved revision',{exact:true}).selectOption(second.profile_revision_id);
    await expect(page.getByRole('button',{name:'Discard candidate draft',exact:true})).toBeDisabled();
    const secondDraft=JSON.stringify({...second.profile,complete:true},null,2);
    await page.getByLabel('Candidate JSON',{exact:true}).fill(secondDraft);
    await page.getByLabel('Saved revision',{exact:true}).selectOption(first.profile_revision_id);
    await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(firstDraft);
    await expect(page.getByLabel('This profile explicitly declares complete skill coverage')).not.toBeChecked();
    await click(page,'Discard candidate draft');
    expect(JSON.parse(await page.getByLabel('Candidate JSON',{exact:true}).inputValue())).toEqual(first.profile);
    await page.getByLabel('Saved revision',{exact:true}).selectOption(second.profile_revision_id);
    await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(secondDraft);
    await click(page,'Discard candidate draft');
    expect(JSON.parse(await page.getByLabel('Candidate JSON',{exact:true}).inputValue())).toEqual(second.profile);
  });

  let pendingCandidateDraft;
  await test.step('A delayed candidate validation error cannot touch a source editor',async()=>{
    const invalid=JSON.stringify({profile_id:'authored-invalid',evidence:[{skill:'Python'}]});
    await page.getByLabel('Candidate JSON',{exact:true}).fill(invalid);
    const pending=await holdResponse(page,'/candidates/import');
    await page.getByRole('button',{name:'Validate & save profile',exact:true}).click();
    expect(await pending.ready).toBe(422);
    await openJob(page,'DRAFT-B',false);await sourceFields(page,b);pending.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');await sourceFields(page,b);
    await nav(page,'Candidate evidence');
    await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(invalid);
    await expect(page.locator('#candidate-error')).toContainText('422:');
    await click(page,'Discard candidate draft');await expect(page.locator('#candidate-error')).toBeHidden();
    const pendingProfile=JSON.parse(await page.getByLabel('Candidate JSON',{exact:true}).inputValue());
    pendingProfile.complete=true;pendingProfile.evidence[0].quote+=' Authored unsaved candidate body marker';
    pendingCandidateDraft=JSON.stringify(pendingProfile,null,2);
    await page.getByLabel('Candidate JSON',{exact:true}).fill(pendingCandidateDraft);
    await page.getByLabel('Saved profile ID').fill('authored-pending-candidate-lookup');
  });

  await test.step('Delayed acquisition failures and successes preserve the current route and posting',async()=>{
    await openJob(page,'DRAFT-DENIED');await writeSource(page,{...a,text:'Authored denied manual draft'});
    const failed=await holdResponse(page,'/jobs/DRAFT-DENIED/fetch');
    await page.getByRole('button',{name:'Try URL acquisition',exact:true}).click();expect(await failed.ready).toBe(403);
    await openJob(page,'DRAFT-B',false);await sourceFields(page,b);failed.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');await sourceFields(page,b);
    await openJob(page,'DRAFT-DENIED');await sourceFields(page,{...a,text:'Authored denied manual draft'});
    await openJob(page,'DRAFT-A');
    const success=await holdResponse(page,'/jobs/DRAFT-A/fetch');
    await page.getByRole('button',{name:'Try URL acquisition',exact:true}).click();expect(await success.ready).toBe(201);
    await nav(page,'Candidate evidence');success.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
    await expect(page.getByRole('heading',{level:1,name:'Candidate evidence',exact:true})).toBeVisible();
    await expect(page.getByLabel('Candidate JSON',{exact:true})).toHaveValue(pendingCandidateDraft);
    await expect(page.getByLabel('Saved profile ID')).toHaveValue('authored-pending-candidate-lookup');
    await expect(page.getByLabel('This profile explicitly declares complete skill coverage')).toBeChecked();
    const candidateSave=await holdResponse(page,'/candidates/import');
    await page.getByRole('button',{name:'Validate & save profile',exact:true}).click();expect(await candidateSave.ready).toBe(201);
    await openJob(page,'DRAFT-B',false);await sourceFields(page,b);candidateSave.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');await sourceFields(page,b);
    await nav(page,'Candidate evidence');
    expect(JSON.parse(await page.getByLabel('Candidate JSON',{exact:true}).inputValue())).toEqual(JSON.parse(pendingCandidateDraft));
    await expect(page.getByRole('button',{name:'Discard candidate draft',exact:true})).toBeDisabled();
    await openJob(page,'DRAFT-A');await sourceFields(page,a);
    await click(page,'Discard source draft');
    const acquired=(await (await request.get('/jobs/DRAFT-A')).json()).snapshot;
    await sourceFields(page,{text:acquired.clean_text,format:'text',url:acquired.source_url});
  });

  await test.step('Delayed extraction and source save update only their originating posting',async()=>{
    await writeSource(page,a);
    const extracted=await holdResponse(page,'/jobs/DRAFT-A/extract');
    await page.getByRole('button',{name:'Extract requirements',exact:true}).click();expect(await extracted.ready).toBe(200);
    await openJob(page,'DRAFT-B',false);await sourceFields(page,b);extracted.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');await sourceFields(page,b);
    await openJob(page,'DRAFT-A');await sourceFields(page,a);
    expect((await (await request.get('/jobs/DRAFT-A')).json()).extraction.requirements.length).toBeGreaterThan(0);
    const saved=await holdResponse(page,'/jobs/DRAFT-A/snapshots');
    await page.getByRole('button',{name:'Save immutable snapshot',exact:true}).click();expect(await saved.ready).toBe(201);
    await openJob(page,'DRAFT-B',false);await sourceFields(page,b);saved.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');await sourceFields(page,b);
    await openJob(page,'DRAFT-A');
    const snapshot=(await (await request.get('/jobs/DRAFT-A')).json()).snapshot;
    await sourceFields(page,{text:snapshot.clean_text,format:'text',url:a.url});
    await expect(page.getByRole('button',{name:'Discard source draft',exact:true})).toBeDisabled();
    await writeSource(page,a);
    const failed=await holdResponse(page,'/jobs/DRAFT-A/extract');
    await page.getByRole('button',{name:'Extract requirements',exact:true}).click();expect(await failed.ready).toBe(501);
    await nav(page,'Job registry');failed.release();
    await expect(page.locator('main')).toHaveAttribute('aria-busy','false');
    await expect(page.getByRole('heading',{level:1,name:'Job registry',exact:true})).toBeVisible();
    await openJob(page,'DRAFT-A');await sourceFields(page,a);
  });

  await test.step('Late history reads and browser connection failures preserve scoped drafts',async()=>{
    await openJob(page,'DRAFT-B');
    const history=await holdResponse(page,'/jobs/DRAFT-A/history','GET');
    await page.getByLabel('Selected posting').selectOption('DRAFT-A');expect(await history.ready).toBe(200);
    await nav(page,'Job registry');await openJob(page,'DRAFT-B');history.release();
    await sourceFields(page,b);await expect(page.getByLabel('Selected posting')).toHaveValue('DRAFT-B');
    await page.route('**/jobs/DRAFT-B/snapshots',route=>route.abort('connectionrefused'),{times:1});
    await click(page,'Save immutable snapshot');await expect(page.getByRole('status')).toContainText('Connection unavailable');
    await sourceFields(page,b);await nav(page,'Overview');await openJob(page,'DRAFT-B');await sourceFields(page,b);
    const storage=await page.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}));
    for(const marker of ['Authored unsaved source marker','Authored registry draft marker','authored-unsaved-lookup-marker','Authored denied manual draft','authored-invalid','Authored unsaved candidate body marker'])expect(storage).not.toContain(marker);
    await click(page,'Cancel unsent operation');
    await click(page,'Discard source draft');
    await sourceFields(page,{text:'',format:'text',url:''});
    await openJob(page,'DRAFT-A');await sourceFields(page,a);
    await page.reload();
    await expect(page.getByLabel('Posting source')).toHaveValue((await (await request.get('/jobs/DRAFT-A')).json()).snapshot.clean_text);
    await expect(page.getByRole('button',{name:'Discard source draft',exact:true})).toBeDisabled();
  });
  expect(errors).toEqual([]);
  await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  await page.screenshot({path:info.outputPath('successful-screen.png'),fullPage:true});
  await page.waitForTimeout(1200);
});
