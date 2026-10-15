import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {resolve,relative,sep} from 'node:path';
import {uiSourceHash} from './ui_source_hash.mjs';
import {selectSuccessfulVideos} from './ui_evidence.mjs';

const report=JSON.parse(await readFile('work/ui-results.json','utf8'));
const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
selectSuccessfulVideos(report,contract);
const observations=[];
async function visit(suite){
  for(const spec of suite.specs??[])if(spec.title.startsWith('UI15 |'))for(const test of spec.tests){
    const attempt=test.results.findLast(result=>result.status==='passed');
    const attachment=attempt?.attachments.find(a=>a.name==='catalogue-observations');
    if(!attachment?.path)throw new Error('Successful UI15 observation attachment is required.');
    const path=resolve(attachment.path),rel=relative(resolve('test-results'),path);
    if(rel.startsWith(`..${sep}`)||rel==='..'||rel.startsWith(sep))throw new Error('Catalogue attachment escapes test-results.');
    const measured=JSON.parse(await readFile(path,'utf8'));
    if(measured.project!==test.projectName||measured.registry_jobs!==45||['snapshots','runs','revisions','evaluations'].some(k=>measured[k]!==23)||measured.legacy_bulk_reads.length||measured.observed.some(row=>row.count>20))throw new Error('Catalogue demonstration coverage is incomplete.');
    observations.push(measured);
  }
  for(const child of suite.suites??[])await visit(child);
}
for(const suite of report.suites)await visit(suite);
if(JSON.stringify(observations.map(r=>r.project).sort())!==JSON.stringify([...contract.projects].sort()))throw new Error('Both viewport catalogue observations are required.');
const directory='docs/issue-evidence/47',performance=JSON.parse(await readFile(`${directory}/catalogue-performance.json`,'utf8'));
const python=process.env.UI_PYTHON||'.venv/bin/python';
const current=JSON.parse(execFileSync(python,['-c','import json; from jobintel.experiments import code_provenance; print(json.dumps(code_provenance()))'],{encoding:'utf8'}));
if(performance.code_provenance.source_sha256!==current.source_sha256||performance.rows.length!==10||new Set(performance.rows.map(r=>r.database)).size!==2||performance.rows.some(r=>r.bounded.select_statements!==2||r.bounded.selected_source_body_columns||r.bounded.returned_jobs>20))throw new Error('Performance evidence is missing, stale or unsuccessful.');
const github=process.env.GITHUB_ACTIONS==='true';
const runUrl=github?`${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`:null;
const evidence={schema_version:1,origin:github?'github-actions':'local-playwright',run_url:runUrl,git_sha:process.env.GITHUB_SHA??execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),source_hash:await uiSourceHash(),observations};
await mkdir(directory,{recursive:true});await writeFile(`${directory}/catalogue-observations.json`,JSON.stringify(evidence,null,2)+'\n');
console.log('Published verified desktop/mobile catalogue observations and performance provenance.');
