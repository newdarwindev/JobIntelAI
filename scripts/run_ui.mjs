import {spawnSync} from 'node:child_process';

const python=process.env.UI_PYTHON || '.venv/bin/python';
const result=spawnSync(python,['-m','scripts.run_ui',...process.argv.slice(2)],{stdio:'inherit'});
if(result.error)console.error(result.error.message);
process.exit(result.status ?? 1);
