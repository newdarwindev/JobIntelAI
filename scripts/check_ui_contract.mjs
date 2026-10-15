import {readFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {uiSourceHash} from './ui_source_hash.mjs';

const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
const files=(await readdir('tests/e2e')).filter(file=>file.endsWith('.spec.mjs'));
const tests=(await Promise.all(files.map(file=>readFile(`tests/e2e/${file}`,'utf8')))).join('\n');
const ids=[...tests.matchAll(/test\('(UI\d{2}) \|/g)].map(m=>m[1]).sort();
if(JSON.stringify(ids)!==JSON.stringify(contract.workflows.map(w=>w.id).sort()))throw new Error('UI specification and workflow tests must have identical IDs.');
if(process.argv.includes('--coverage-only')){console.log(`${ids.length} specified workflows have executable journeys.`);process.exit(0);}
const manifest=JSON.parse(await readFile('docs/ui-recordings/manifest.json','utf8'));
if(manifest.failed!==0||manifest.source_hash!==await uiSourceHash())throw new Error('UI evidence is stale or unsuccessful. Run npm run test:ui and npm run record:ui.');
const expected=contract.workflows.flatMap(w=>contract.projects.map(p=>`${w.id}/${p}`)).sort();
if(JSON.stringify(expected)!==JSON.stringify(manifest.records.map(r=>`${r.id}/${r.project}`).sort()))throw new Error('Recording coverage is incomplete.');
const readme=await readFile('README.md','utf8');
for(const record of manifest.records){if(record.status!=='passed')throw new Error('A non-passing attempt was published.');const file=`docs/ui-recordings/${record.file}`;if(record.file!==`${record.id}-${record.project}.webm`)throw new Error('Unexpected recording filename.');const bytes=await readFile(file);if(bytes.length!==record.bytes||createHash('sha256').update(bytes).digest('hex')!==record.sha256)throw new Error(`Corrupt recording: ${file}`);if(!readme.includes(`](${file})`))throw new Error(`README video link missing: ${file}`);}
const evidenceFiles=['docs/issue-evidence/40/mutation-comparison.json','docs/issue-evidence/40/mutation-comparison.md','docs/issue-evidence/41/batch-comparison.json','docs/issue-evidence/41/batch-comparison.md'];
if(JSON.stringify(manifest.issue_evidence?.map(e=>e.file).sort())!==JSON.stringify([...evidenceFiles].sort()))throw new Error('Mutation demonstration artifacts are incomplete.');
for(const record of manifest.issue_evidence){const bytes=await readFile(record.file);if(bytes.length!==record.bytes||createHash('sha256').update(bytes).digest('hex')!==record.sha256)throw new Error('Mutation demonstration artifact is corrupt.');if(!readme.includes(`](${record.file})`))throw new Error('README mutation demonstration link missing.');}
const comparison=JSON.parse(await readFile(evidenceFiles[0],'utf8'));
if(comparison.source_hash!==manifest.source_hash||comparison.git_sha!==manifest.git_sha||comparison.origin!==manifest.origin||comparison.run_url!==manifest.run_url||comparison.rows.length!==38)throw new Error('Mutation demonstration provenance or coverage is stale.');
const batchComparison=JSON.parse(await readFile('docs/issue-evidence/41/batch-comparison.json','utf8'));
if(batchComparison.source_hash!==manifest.source_hash||batchComparison.git_sha!==manifest.git_sha||batchComparison.origin!==manifest.origin||batchComparison.run_url!==manifest.run_url||batchComparison.rows.length!==32)throw new Error('Batch demonstration provenance or coverage is stale.');
console.log(`${manifest.records.length} passing recordings cover all workflows; source hashes and README links are current.`);
