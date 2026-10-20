import {batchMarkdown} from './render_ui_evidence.mjs';
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
await writeFile(`${directory}/batch-comparison.md`,batchMarkdown(evidence));
