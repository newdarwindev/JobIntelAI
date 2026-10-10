import {createHash} from 'node:crypto';
import {readFile,readdir} from 'node:fs/promises';
import {join} from 'node:path';

// This deliberately excludes generated videos, README, caches and local databases.
export async function uiSourceHash(){
  const directories=['src/jobintel','tests/e2e','data','alembic','scripts/acquisition_fixtures','scripts/responses_emulator'];
  const inputs=[...directories,'alembic.ini','pyproject.toml','requirements.lock.txt','Dockerfile','Dockerfile.offline','docker-compose.yml','docker-compose.offline.yml','docker-compose.demo.yml','docker-compose.openai.yml','docker-compose.proxy.yml','Dockerfile.acquisition','docker-compose.acquisition.yml','docker-compose.acquisition-api.yml','scripts/acquisition_environment.py','scripts/acquisition_smoke.py','scripts/acquisition_public_smoke.py','scripts/serve_acquisition_api.py','docker-compose.local.yml','docker-compose.local-offline.yml','docker-compose.local-proxy.yml','scripts/local_model.py','scripts/local_evaluation.py','scripts/local_smoke.py','.github/workflows/local-inference.yml','docker-compose.responses.yml','docker-compose.responses-proxy.yml','scripts/responses_environment.py','scripts/responses_smoke.py','scripts/responses_ui.py','scripts/run_ui.py','scripts/run_ui.mjs','scripts/__init__.py','scripts/runtime.py','scripts/runtime_smoke.py','scripts/serve_ui.py','scripts/ui_source_hash.mjs','scripts/ui_evidence.mjs','scripts/publish_ui_recordings.mjs','scripts/check_ui_contract.mjs','tests/unit/ui_recordings.test.mjs','docs/web_ui_workflows.json','docs/web_ui_spec.md','playwright.config.mjs','package.json','package-lock.json','.github/workflows/web-ui.yml'];
  const files=[];
  async function walk(path){const entries=await readdir(path,{withFileTypes:true});for(const entry of entries){if(entry.name==='__pycache__')continue;const file=join(path,entry.name);if(entry.isDirectory())await walk(file);else if(entry.isFile())files.push(file);}}
  for(const path of inputs){if(directories.includes(path))await walk(path);else files.push(path);}
  const hash=createHash('sha256');for(const file of files.sort()){hash.update(file);hash.update('\0');hash.update(await readFile(file));hash.update('\0');}return hash.digest('hex');
}
