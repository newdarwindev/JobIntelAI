import {readFile,writeFile,mkdir,copyFile,stat} from 'node:fs/promises';
import {resolve,relative,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {uiSourceHash} from './ui_source_hash.mjs';
import {selectSuccessfulVideos} from './ui_evidence.mjs';

const contract=JSON.parse(await readFile('docs/web_ui_workflows.json','utf8'));
const report=JSON.parse(await readFile('work/ui-results.json','utf8'));
const entries=selectSuccessfulVideos(report,contract);
const expectedCount=contract.workflows.length*contract.projects.length;
const directory='docs/ui-recordings';await mkdir(directory,{recursive:true});
const records=[];
for(const entry of entries){const source=resolve(entry.path);const rel=relative(resolve('test-results'),source);if(rel.startsWith(`..${sep}`)||rel==='..'||rel.startsWith(sep))throw new Error('Video attachment escapes test-results.');const bytes=await readFile(source);if(bytes.length<1000)throw new Error('Video is missing or empty.');const name=`${entry.id}-${entry.project}.webm`;await copyFile(source,`${directory}/${name}`);records.push({id:entry.id,project:entry.project,title:entry.title,file:name,status:'passed',successful_attempt:entry.attempt,browser_version:entry.browser_version,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});}
const github=process.env.GITHUB_ACTIONS==='true';
const issueEvidence=[];
for(const file of ['docs/issue-evidence/40/mutation-comparison.json','docs/issue-evidence/40/mutation-comparison.md','docs/issue-evidence/41/batch-comparison.json','docs/issue-evidence/41/batch-comparison.md','docs/issue-evidence/47/catalogue-performance.json','docs/issue-evidence/47/catalogue-performance.md','docs/issue-evidence/47/catalogue-observations.json']){const bytes=await readFile(file);issueEvidence.push({file,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});}
const runUrl=github?`${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`:null;
const manifest={schema_version:1,origin:github?'github-actions':'local-playwright',recorded_at:new Date().toISOString(),source_hash:await uiSourceHash(),git_sha:process.env.GITHUB_SHA??execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),run_url:runUrl,command:'npm run test:ui',expected:report.stats.expected,flaky:report.stats.flaky,failed:report.stats.unexpected,records,issue_evidence:issueEvidence};
await writeFile(`${directory}/manifest.json`,JSON.stringify(manifest,null,2)+'\n');
const start='<!-- UI-RECORDINGS:START -->',end='<!-- UI-RECORDINGS:END -->';
const rows=contract.workflows.map(w=>`| ${w.id} · ${w.title} | [Смотреть](docs/ui-recordings/${w.id}-desktop-chromium.webm) | [Смотреть](docs/ui-recordings/${w.id}-mobile-chromium.webm) |`);
const block=[start,'',`Успешные браузерные попытки: **${entries.length}/${expectedCount}**, записано ${manifest.recorded_at.slice(0,10)}.`,github?`Источник: [Запуск GitHub Actions](${runUrl}) · коммит \`${manifest.git_sha}\`.`:'Источник: локальный Playwright с sandbox и обычными PostgreSQL API. Эти записи не подтверждают удалённый GitHub Actions run.','UI01–UI08 и UI12–UI15: синтетический sandbox; UI12 проверяет drafts при задержке реальных ответов, UI13 — durable mutation recovery, UI14 — частичные batches и безопасное продолжение, UI15 — поиск и постраничная история. UI09–UI11: PostgreSQL API, fixture, Responses emulator и реальная CPU inference. Ввод авторский; emulator подтверждает только контракт.',`SHA-256 исходного содержимого: \`${manifest.source_hash}\`. [Машинные данные происхождения](docs/ui-recordings/manifest.json).`,'','[Измеренные исходы batches](docs/issue-evidence/41/batch-comparison.md) · [JSON наблюдений batches](docs/issue-evidence/41/batch-comparison.json).','','[Измеренное восстановление mutations](docs/issue-evidence/40/mutation-comparison.md) · [JSON наблюдений](docs/issue-evidence/40/mutation-comparison.json).','','[Измерения каталогов](docs/issue-evidence/47/catalogue-performance.md) · [JSON измерений](docs/issue-evidence/47/catalogue-performance.json) · [JSON наблюдений UI15](docs/issue-evidence/47/catalogue-observations.json).','','| Полный сценарий | Desktop Chromium | Mobile Chromium |','| --- | --- | --- |',...rows,'',end].join('\n');
const readme=await readFile('README.md','utf8');const first=readme.indexOf(start),last=readme.indexOf(end);
if(first<0||last<first)throw new Error('README recording markers are missing.');
await writeFile('README.md',readme.slice(0,first)+block+readme.slice(last+end.length));
console.log(`Published ${records.length} successful attempt videos and README provenance (${manifest.origin}).`);
