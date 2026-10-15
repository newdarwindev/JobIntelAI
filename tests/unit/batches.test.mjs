import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CorpusBatches,batchLimit} from '../../src/jobintel/web/batches.js';
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),values};};
const jobs=count=>Array.from({length:count},(_,i)=>({jobId:`JOB-${i+1}`,stage:'match',snapshotId:`source-${i+1}`,expectedRunId:`run-${i+1}`}));
function harness(count=3){let id=0;const store=storage(),batches=new CorpusBatches({storage:store,identity:()=>`batch-${++id}`});batches.start('matching',jobs(count),{profile_id:'authored',profile_revision_id:'revision-1'});return {batches,store};}
function outcome(batches,item,status=200,stage='match'){
  const context=batches.context('matching',item.jobId,stage),id=`operation-${item.jobId}-${item.attempts.length}`;
  batches.observe(context,{operation_id:id,state:status<400?'committed':'rejected',http_status:status,result:status<400?{match_run_id:`saved-${id}`}:{detail:'Authored failure'}},r=>r.detail);
}

for(const failureIndex of [0,1,2])test(`failure at item ${failureIndex+1} retains identities and resumes only unfinished work`,async()=>{
  const {batches}=harness(),calls=[];let fail=true,refreshes=0;
  const driver={blocked:()=>false,prepare:async()=>{},process:async item=>{
    calls.push(item.jobId);
    if(fail&&item.jobId===`JOB-${failureIndex+1}`){outcome(batches,item,422);throw new Error('Authored failure');}
    outcome(batches,item);
  },refresh:async()=>{refreshes++;}};
  await batches.run('matching',driver);
  assert.equal(batches.counts(batches.get('matching')).completed,failureIndex);
  assert.equal(batches.counts(batches.get('matching')).failed,1);
  const failed=batches.get('matching').items[failureIndex],retained=failed.attempts[0].operation_id;
  fail=false;await batches.run('matching',driver);
  assert.equal(batches.remaining('matching').length,0);
  assert.equal(refreshes,2);
  for(let i=0;i<failureIndex;i++)assert.equal(calls.filter(id=>id===`JOB-${i+1}`).length,1);
  assert.equal(failed.attempts[0].operation_id,retained);
  assert.equal(failed.attempts[0].state,'rejected');
  assert.equal(failed.attempts.length,2);
});

test('each pass is bounded and continuation excludes every completed item',async()=>{
  const {batches}=harness(45),calls=[];
  const driver={blocked:()=>false,prepare:async()=>{},process:async item=>{calls.push(item.jobId);outcome(batches,item);},refresh:async()=>{}};
  await batches.run('matching',driver);assert.equal(calls.length,batchLimit);assert.equal(batches.remaining('matching').length,25);
  await batches.run('matching',driver);assert.equal(calls.length,40);
  await batches.run('matching',driver);assert.equal(calls.length,45);assert.equal(new Set(calls).size,45);
});
test('uncertain delivery blocks new passes and reconciliation preserves the saved result',async()=>{
  const {batches}=harness(),item=batches.get('matching').items[0],context=batches.context('matching',item.jobId,'match');
  batches.observe(context,{operation_id:'opaque-id',state:'uncertain'},()=> '');
  await assert.rejects(batches.run('matching',{blocked:()=>true}),/Resolve/);
  await assert.rejects(batches.run('matching',{blocked:()=>false}),/Resolve/);
  assert.equal(batches.remaining('matching').length,3);
  batches.observe(context,{operation_id:'opaque-id',state:'committed',http_status:200,result:{match_run_id:'saved-once'}},()=> '');
  assert.equal(item.state,'completed');assert.equal(item.attempts.length,1);assert.equal(item.resultId,'saved-once');
});
test('confirmed commit with failed display read remains completed and refresh is attempted',async()=>{
  const {batches}=harness(),item=batches.get('matching').items[0];let refreshes=0;
  await batches.run('matching',{blocked:()=>false,prepare:async()=>{},process:async()=>{outcome(batches,item);throw new Error('display unavailable');},refresh:async()=>{refreshes++;throw new Error('GET unavailable');}});
  assert.equal(item.state,'completed');assert.equal(refreshes,1);assert.match(batches.get('matching').refreshError,/GET unavailable/);
});
test('reload recovers ID-only journal and attaches the pending operation to its original item',()=>{
  const {batches,store}=harness(),item=batches.get('matching').items[1];
  batches.observe(batches.context('matching',item.jobId,'match'),{operation_id:'opaque-id',state:'pending',result:{private_text:'private sentinel'}},()=> 'private error sentinel');
  item.error='private error sentinel';item.privateBody='private posting sentinel';batches.changed();
  const serialized=[...store.values.values()].join('');assert.doesNotMatch(serialized,/private|sentinel/);
  const restored=new CorpusBatches({storage:store});
  assert.equal(restored.get('matching').running,false);assert.equal(restored.get('matching').items[1].state,'uncertain');
  assert.deepEqual(restored.pendingContext('opaque-id'),batches.context('matching',item.jobId,'match'));
});
test('explicit source replan changes only remaining inputs and retains original candidate and attempts',()=>{
  const {batches}=harness(),batch=batches.get('matching');outcome(batches,batch.items[0]);outcome(batches,batch.items[1],409);
  const completed=JSON.stringify(batch.items[0]),failure=batch.items[1].attempts[0].operation_id;
  batches.replan('matching',jobs(3).map(j=>({job_id:j.jobId,snapshot:{id:'new-source'},extraction:{run_id:'new-run'}})));
  assert.equal(JSON.stringify(batch.items[0]),completed);assert.equal(batch.items[1].expectedRunId,'new-run');
  assert.equal(batch.items[1].attempts[0].operation_id,failure);assert.equal(batch.selection.profile_revision_id,'revision-1');
});
test('preparation and empty-batch exits refresh authoritative state without attempting items',async()=>{
  const {batches}=harness(0);let refreshes=0,processed=0;
  const driver={blocked:()=>false,prepare:async()=>{},process:async()=>{processed++;},refresh:async()=>{refreshes++;}};
  await batches.run('matching',driver);assert.equal(processed,0);assert.equal(refreshes,1);
  driver.prepare=async()=>{throw new Error('selection changed');};await batches.run('matching',driver);
  assert.equal(processed,0);assert.equal(refreshes,2);assert.match(batches.get('matching').error,/selection changed/);
});
test('saved snapshot stages survive rejection and reload without repeating source writes',()=>{
  const store=storage(),batches=new CorpusBatches({storage:store,identity:()=> 'batch'});
  const batch=batches.start('extraction',[{jobId:'JOB-1',stage:'snapshot',expectedSnapshotId:null}],{configuration:'fixture_normalized'});
  const context=stage=>batches.context('extraction','JOB-1',stage);
  batches.observe(context('snapshot'),{operation_id:'snapshot-op',state:'committed',http_status:201,result:{snapshot_id:'source-1'}},r=>r.detail);
  batches.observe(context('extract'),{operation_id:'extract-op',state:'rejected',http_status:501,result:{detail:'unsupported'}},r=>r.detail);
  const restored=new CorpusBatches({storage:store}).get('extraction');
  assert.equal(restored.items[0].stage,'extract');assert.equal(restored.items[0].snapshotId,'source-1');
  assert.equal(restored.items[0].state,'failed');assert.equal(restored.items[0].attempts.length,2);assert.equal(batch.items[0].error,'501: unsupported');
});
