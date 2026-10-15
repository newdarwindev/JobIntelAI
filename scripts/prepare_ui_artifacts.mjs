import {readFile,stat,copyFile,mkdir,rm,appendFile} from 'node:fs/promises';
import {dirname} from 'node:path';
import {partitionFiles} from './ui_artifact_parts.mjs';

const manifest=JSON.parse(await readFile('docs/ui-recordings/manifest.json','utf8'));
const names=['README.md','docs/ui-recordings/manifest.json',...manifest.issue_evidence.map(record=>record.file),...manifest.records.map(record=>`docs/ui-recordings/${record.file}`)];
if(new Set(names).size!==names.length)throw new Error('Duplicate evidence file.');
const files=await Promise.all(names.map(async file=>({file,bytes:(await stat(file)).size})));
const parts=partitionFiles(files);
await rm('work/ui-publication',{recursive:true,force:true});
for(const [index,part] of parts.entries())for(const record of part){const target=`work/ui-publication/part-${index+1}/${record.file}`;await mkdir(dirname(target),{recursive:true});await copyFile(record.file,target);}
if(process.env.GITHUB_OUTPUT)await appendFile(process.env.GITHUB_OUTPUT,`parts=${parts.length}\n`);
console.log(`Prepared ${names.length} verified files in ${parts.length} publication parts, each at most 22 MiB.`);
