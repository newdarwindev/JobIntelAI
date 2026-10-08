import {readFile,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {uiSourceHash} from './ui_source_hash.mjs';

const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
const tests=await readFile('tests/e2e/workflows.spec.mjs','utf8');
const ids=[...tests.matchAll(/test\('(UI\d{2}) \|/g)].map(m=>m[1]).sort();
if(JSON.stringify(ids)!==JSON.stringify(contract.workflows.map(w=>w.id).sort()))throw new Error('UI specification and workflow tests must have identical IDs.');
if(process.argv.includes('--coverage-only')){console.log(`${ids.length} specified workflows have executable journeys.`);process.exit(0);}
const manifest=JSON.parse(await readFile('docs/ui-recordings/manifest.json','utf8'));
if(manifest.failed!==0||manifest.source_hash!==await uiSourceHash())throw new Error('UI evidence is stale or unsuccessful. Run npm run test:ui and npm run record:ui.');
const expected=contract.workflows.flatMap(w=>contract.projects.map(p=>`${w.id}/${p}`)).sort();
if(JSON.stringify(expected)!==JSON.stringify(manifest.records.map(r=>`${r.id}/${r.project}`).sort()))throw new Error('Recording coverage is incomplete.');
const readme=await readFile('README.md','utf8');
for(const record of manifest.records){if(record.status!=='passed')throw new Error('A non-passing attempt was published.');const file=`docs/ui-recordings/${record.file}`;if(record.file!==`${record.id}-${record.project}.webm`)throw new Error('Unexpected recording filename.');const bytes=await readFile(file);if(bytes.length!==record.bytes||createHash('sha256').update(bytes).digest('hex')!==record.sha256)throw new Error(`Corrupt recording: ${file}`);if(!readme.includes(`](${file})`))throw new Error(`README video link missing: ${file}`);}
console.log(`${manifest.records.length} passing recordings cover all workflows; source hashes and README links are current.`);
