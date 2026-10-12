import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {resolve,relative,sep} from 'node:path';
import {selectSuccessfulVideos} from './ui_evidence.mjs';
import {uiSourceHash} from './ui_source_hash.mjs';

const report=JSON.parse(await readFile('work/ui-results.json','utf8'));
const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
selectSuccessfulVideos(report,contract);
const observations=[];
function visit(suite){
  for(const spec of suite.specs??[])if(spec.title.startsWith('UI14 |'))for(const test of spec.tests){
    const result=test.results.findLast(result=>result.status==='passed');
    const attachment=result.attachments.find(a=>a.name==='batch-comparison');
    if(!attachment?.path)throw new Error('Successful UI14 comparison is missing.');
    observations.push({project:test.projectName,path:attachment.path});
  }
  for(const child of suite.suites??[])visit(child);
}
for(const suite of report.suites)visit(suite);
if(JSON.stringify(observations.map(o=>o.project).sort())!==JSON.stringify([...contract.projects].sort()))throw new Error('Both viewport observations are required.');
const expected=['extraction','matching'].flatMap(kind=>['failure_first','failure_middle','failure_last','before_delivery','after_commit_lookup_lost_reload','navigation_in_flight','empty'].map(scenario=>`${kind}/${scenario}`)).concat(['extraction/stale_source','matching/stale_revision']).sort();
const rows=[];
for(const observation of observations){
  const path=resolve(observation.path),rel=relative(resolve('test-results'),path);
  if(rel==='..'||rel.startsWith(`..${sep}`)||rel.startsWith(sep))throw new Error('Comparison path escapes test-results.');
  const measured=JSON.parse(await readFile(path,'utf8'));
  if(measured.schema_version!==1||JSON.stringify(measured.rows.map(row=>`${row.kind}/${row.scenario}`).sort())!==JSON.stringify(expected))throw new Error('Batch boundary coverage is incomplete.');
  for(const row of measured.rows){
    if(row.project!==observation.project)throw new Error('Comparison viewport disagrees.');
    if(row.resumed.counts.failed||row.resumed.counts.uncertain||row.resumed.counts.unattempted)throw new Error('Published batch outcome is unresolved.');
    for(const completed of row.partial.items.filter(item=>item.state==='completed')){
      const final=row.resumed.items.find(item=>item.jobId===completed.jobId);
      if(final?.resultId!==completed.resultId||JSON.stringify(final.attempts)!==JSON.stringify(completed.attempts))throw new Error('Completed item was repeated or changed.');
    }
    rows.push(row);
  }
}
const github=process.env.GITHUB_ACTIONS==='true';
const runUrl=github?`${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`:null;
const evidence={schema_version:1,origin:github?'github-actions':'local-playwright',run_url:runUrl,git_sha:process.env.GITHUB_SHA??execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),source_hash:await uiSourceHash(),mode:'authored fixture replay; actual API/database operations; no paid calls',rows};
const directory='docs/issue-evidence/41';await mkdir(directory,{recursive:true});
await writeFile(`${directory}/batch-comparison.json`,JSON.stringify(evidence,null,2)+'\n');
const counts=value=>`${value.completed} completed / ${value.failed} failed / ${value.unattempted} unattempted / ${value.uncertain} uncertain`;
const table=rows.map(row=>`| ${row.project} | ${row.kind} | ${row.scenario} | ${row.before.registered}/${row.before.current_extracted} | ${counts(row.partial.counts)} | ${row.partial.server?`${row.partial.server.registered}/${row.partial.server.current_extracted}`:'0/0'} | ${counts(row.resumed.counts)} | ${row.resumed.server.registered}/${row.resumed.server.current_extracted} | ${row.browser_mutation_posts.length} | ${row.partial.items.filter(item=>item.state==='completed').map(item=>`${item.jobId}: ${item.resultId}`).join('<br>')||'No item completed before interruption'} |`);
const lines=['# Corpus batches — measured before, partial and resumed outcomes','',`Source: ${github?`[GitHub Actions run](${runUrl})`:'local Playwright'} · tested commit \`${evidence.git_sha}\`.`,`Source content SHA-256: \`${evidence.source_hash}\`. [Observation JSON, request/result identities and history](batch-comparison.json).`,'',evidence.mode+'.','',
  'UI14 selects three authored fixture jobs through a labelled fixture-metadata read, then uses actual domain APIs for every snapshot, extraction and match. Extraction failures are unsupported authored fixture inputs. Matching failures advance the real saved extraction before a captured stale request; the API rejects it. No successful domain response is substituted. UI03/UI05 additionally process the complete 20-posting corpus; the unit gate verifies the 20-item continuation bound with 45 items.',
  '', 'Each completed item retains its exact result and operation attempts across continuation. The journey asserts one successful extraction/match per item and no repeat POST for any previously completed item. Before-delivery retry retains one operation identity; post-commit lookup/reload adds no second mutation. Explicit source replan touches only unfinished items. A changed candidate selection sends no matching request until the captured revision is restored. Empty batches send no mutations.',
  '', 'Counts below describe the captured batch and actual server state, not model quality. Journal state recorded during in-flight navigation is uncertain until delivery resolves, even if the server already committed. Browser POST counts cover keyed job snapshot/extraction/matching attempts; registry preparation, reads, profile saves and independent API fault-injection requests are excluded. Matching has no catalogue: exact saved match responses and operation IDs are verified. Original extraction history is retained.',
  '', '| Viewport | Batch | Boundary | Before registered/extracted | Partial batch outcomes | Partial server registered/extracted | Resumed batch outcomes | Resumed server registered/extracted | Browser job POST attempts | Previously completed saved IDs retained |','| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |',...table,'',
  '[Desktop UI14 recording](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14 recording](../../ui-recordings/UI14-mobile-chromium.webm)','',
  'The rendered batch panel keeps completed/failed/unattempted/uncertain job identities and prior rejected operation IDs visible across navigation and reload. Session storage contains only IDs, configuration/selection references and outcome states; posting/profile bodies and error messages are fetched into memory. Unknown operation outcomes block continuation. All exits attempt an authoritative refresh; a failed refresh is labelled unavailable.',''];
await writeFile(`${directory}/batch-comparison.md`,lines.join('\n'));
console.log(`Published ${rows.length} measured batch cases from successful desktop/mobile attempts (${evidence.origin}).`);
