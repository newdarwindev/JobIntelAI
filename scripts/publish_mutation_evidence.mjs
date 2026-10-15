import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {resolve,relative,sep} from 'node:path';
import {selectSuccessfulVideos} from './ui_evidence.mjs';
import {uiSourceHash} from './ui_source_hash.mjs';

const report=JSON.parse(await readFile('work/ui-results.json','utf8'));
const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
selectSuccessfulVideos(report,contract);
const cases=[];
function visit(suite){
  for(const spec of suite.specs??[]){
    if(!spec.title.startsWith('UI13 |'))continue;
    for(const test of spec.tests){
      const result=test.results.findLast(r=>r.status==='passed');
      const attachment=result.attachments.find(a=>a.name==='mutation-comparison');
      if(!attachment?.path)throw new Error('UI13 has no successful measured comparison.');
      cases.push({project:test.projectName,path:attachment.path});
    }
  }
  for(const child of suite.suites??[])visit(child);
}
for(const suite of report.suites)visit(suite);
if(JSON.stringify(cases.map(c=>c.project).sort())!==JSON.stringify([...contract.projects].sort()))throw new Error('Measured comparison requires both viewports.');
const rows=[];
const expectedCases=['registry','snapshot','candidate','extract','match','evaluate','fetch'].flatMap(kind=>['before_delivery','after_commit'].map(scenario=>`${kind}/${scenario}`)).concat(['extract/display_read_lost','snapshot/unsent_reload_cancel','extract/provider_in_flight','extract/lookup_lost_reload','candidate/validation_rejected']).sort();
for(const item of cases){
  const path=resolve(item.path),rel=relative(resolve('test-results'),path);
  if(rel.startsWith(`..${sep}`)||rel==='..'||rel.startsWith(sep))throw new Error('Comparison attachment escapes test-results.');
  const measured=JSON.parse(await readFile(path,'utf8'));
  if(measured.schema_version!==1||measured.rows.length!==19)throw new Error('Incomplete measured operation cases.');
  if(JSON.stringify(measured.rows.map(row=>`${row.kind}/${row.scenario}`).sort())!==JSON.stringify(expectedCases))throw new Error('Measured operation boundaries are missing or duplicated.');
  for(const row of measured.rows){
    if(row.project!==item.project||row.distinct_request_identities!==1||![0,1].includes(row.completed_handler_executions)||!Number.isInteger(row.browser_post_requests))throw new Error('Operation identity/execution evidence disagrees.');
    if(row.final_state!=='committed'&&row.final_state!=='rejected')throw new Error('Published evidence has an unresolved outcome.');
    rows.push(row);
  }
}
const github=process.env.GITHUB_ACTIONS==='true';
const runUrl=github?`${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`:null;
const evidence={schema_version:1,origin:github?'github-actions':'local-playwright',run_url:runUrl,git_sha:process.env.GITHUB_SHA??execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),source_hash:await uiSourceHash(),mode:'authored fixture replay and Responses emulator; actual API/DB operations; no paid calls',rows};
const directory='docs/issue-evidence/40';await mkdir(directory,{recursive:true});
await writeFile(`${directory}/mutation-comparison.json`,JSON.stringify(evidence,null,2)+'\n');
const display=value=>value===null||value===undefined?'Not enumerated':String(value);
const rendered=rows.map(row=>`| ${row.project} | ${row.kind} | ${row.scenario} | ${row.initial_state} → ${row.final_state} | ${row.browser_post_requests} | ${row.api_conflict_probes??0} | ${row.completed_handler_executions} | ${display(row.before_records)} → ${display(row.after_records)} | ${row.saved_id??'No new saved result'} |`);
const lines=['# Mutation recovery — measured browser verification','',`Source: ${github?`[GitHub Actions run](${runUrl})`:'local Playwright run'} · tested commit \`${evidence.git_sha}\`.`,`Source content SHA-256: \`${evidence.source_hash}\`. [Machine-readable observations](mutation-comparison.json).`,'',evidence.mode+'.','',
  'Each row comes from the passing UI13 attempt, observed browser requests, saved operation lookup and readable API history/catalogues. Before-delivery loss sends two browser POSTs with one identity; after-commit loss recovers with a read. The conflicting-body probe is a separate test API POST and returns 409. Completed keyed handler executions are recorded by the server; they do not measure model quality or internal provider retries.',
  '', 'Snapshot/extraction/registry/revision/evaluation counts come from their actual API catalogues. Matching has no catalogue, so its row count is explicitly not enumerated; its exact saved match ID and immutable response are verified instead. PostgreSQL/SQLite integration tests additionally count all mutation records directly. Unsent cancellation and validation rejection start zero handlers. Display/status-read recovery adds no POST or saved run.',
  '', '| Viewport | Mutation | Interrupted boundary | Observed outcome | Browser POSTs | Conflicting test POSTs | Completed handler executions | Saved records before → after | Exact saved identity |','| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |',...rendered,'',
  '[Desktop UI13 recording](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13 recording](../../ui-recordings/UI13-mobile-chromium.webm)','',
  'Prior snapshot/extraction, candidate revision, match and evaluation records were read back unchanged. The in-flight case uses the separate authored Responses service with a bounded delayed response. Missing outcomes remain uncertain until lookup confirms them; no duplicate execution is scheduled. Only opaque operation identity is persisted in browser storage.',''];
await writeFile(`${directory}/mutation-comparison.md`,lines.join('\n'));
console.log(`Published ${rows.length} measured mutation-recovery cases from successful desktop/mobile attempts (${evidence.origin}).`);
