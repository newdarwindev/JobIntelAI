// Selection is separate from publication so failure/retry cases can be regression-tested.
export function selectSuccessfulVideos(report,contract){
  if(report.stats.unexpected||report.stats.skipped||report.errors?.length)throw new Error('Only a complete successful UI suite may publish recordings.');
  const entries=[];
  function walk(suites){for(const suite of suites??[]){for(const spec of suite.specs??[]){const id=spec.title.match(/^(UI\d{2}) \|/)?.[1];if(!id)throw new Error(`Unmapped UI test: ${spec.title}`);for(const test of spec.tests){if(test.expectedStatus!=='passed'||!['expected','flaky'].includes(test.status))throw new Error(`Unsuccessful test: ${id} / ${test.projectName}`);const attempt=test.results.findLast(r=>r.status==='passed');const video=attempt?.attachments.find(a=>a.name==='video'&&a.contentType==='video/webm');if(!video?.path)throw new Error(`Missing successful video: ${id} / ${test.projectName}`);entries.push({id,project:test.projectName,title:spec.title,attempt:attempt.retry??0,path:video.path,browser_version:test.annotations?.find(a=>a.type==='browser-version')?.description??null});}}walk(suite.suites);}}
  walk(report.suites);
  const expected=contract.workflows.flatMap(w=>contract.projects.map(p=>`${w.id}/${p}`)).sort();
  const actual=entries.map(e=>`${e.id}/${e.project}`).sort();
  if(JSON.stringify(expected)!==JSON.stringify(actual))throw new Error('The recording set must cover every workflow on every contracted browser project.');
  return entries;
}
