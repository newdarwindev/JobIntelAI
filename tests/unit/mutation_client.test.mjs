import test from 'node:test';
import assert from 'node:assert/strict';
import {MutationClient} from '../../src/jobintel/web/operations.js';

const reply=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers});
const storage=()=>{
  const map=new Map();
  return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key),map};
};
const saved=(id='opaque-id')=>({operation_id:id,state:'committed',path:'/jobs/a/extract',http_status:200,result:{run_id:'saved-run'},execution_count:1});

test('lost committed response is recovered by a read with no second POST',async()=>{
  const calls=[],applied=[],stored=storage();
  const client=new MutationClient({identity:()=> 'opaque-id',storage:stored,apply:async(op,result)=>applied.push(result),fetcher:async(path,options)=>{calls.push([path,options]);if(options.method==='POST')throw new Error('lost');return reply(saved());}});
  assert.deepEqual(await client.execute('/jobs/a/extract',{}),{run_id:'saved-run'});
  assert.deepEqual(calls.map(x=>x[1].method??'GET'),['POST','GET']);
  assert.equal(applied.length,1);assert.equal(client.blocked,false);assert.equal(stored.map.size,0);
});

test('not-received recovery retries the same immutable request and identity',async()=>{
  const calls=[],stored=storage();let rejected=true;
  const client=new MutationClient({identity:()=> 'opaque-id',storage:stored,fetcher:async(path,options)=>{calls.push([path,options]);if(!options.method)return reply({operation_id:'opaque-id',state:'not_received'});if(rejected)throw new Error('before delivery');return reply({snapshot_id:'s'},201,{'X-Operation-State':'committed'});}});
  const body={text:'Authored private draft marker'};
  await assert.rejects(client.execute('/jobs/a/snapshots',body),/not received/);
  body.text='Changed after submission';
  assert.equal(client.canRetry,true);assert.equal(stored.map.get('jobintel-pending-operation'),'opaque-id');
  assert.ok(!JSON.stringify([...stored.map]).includes('private draft'));
  await assert.rejects(client.execute('/jobs/a/extract',{}),/Resolve/);
  rejected=false;await client.retry();
  const posts=calls.filter(x=>x[1].method==='POST');
  assert.equal(posts.length,2);assert.equal(posts[0][1].body,posts[1][1].body);
  assert.equal(posts[0][1].headers['Idempotency-Key'],posts[1][1].headers['Idempotency-Key']);
});

test('running or interrupted reservation blocks both retransmission and new work',async()=>{
  let posts=0;
  const client=new MutationClient({identity:()=> 'opaque-id',fetcher:async(path,options)=>{if(options.method){posts++;throw new Error('lost');}return reply({operation_id:'opaque-id',state:'uncertain',execution_count:null});}});
  await assert.rejects(client.execute('/evaluate',{configurations:['fixture_raw']}),/Outcome uncertain/);
  await assert.rejects(client.retry(),/cannot be safely/);await assert.rejects(client.cancel(),/confirmed not received/);
  await assert.rejects(client.execute('/evaluate',{}),/Resolve/);assert.equal(posts,1);
});

test('saved response survives a failed UI refresh without retransmitting mutation',async()=>{
  let posts=0,refreshFailed=true;
  const client=new MutationClient({identity:()=> 'opaque-id',apply:async()=>{if(refreshFailed)throw new Error('read lost');},fetcher:async(path,options)=>{if(options.method){posts++;return reply({run_id:'saved-run'},200,{'X-Operation-State':'committed'});}return reply(saved());}});
  await assert.rejects(client.execute('/jobs/a/extract',{}),/display refresh/);
  assert.equal(client.latest.state,'committed');assert.equal(client.blocked,true);
  refreshFailed=false;assert.deepEqual(await client.check(),{run_id:'saved-run'});assert.equal(posts,1);
});

test('reload retains only an opaque identity and restores its saved result',async()=>{
  const stored=storage();stored.setItem('jobintel-pending-operation','opaque-id');
  const calls=[],applied=[];
  const client=new MutationClient({storage:stored,apply:async(op,result)=>applied.push(result),fetcher:async(path,options)=>{calls.push(options.method??'GET');return reply(saved());}});
  assert.equal(client.pending.encoded,null);await client.check();assert.deepEqual(calls,['GET']);assert.equal(applied.length,1);
});

test('unavailable lookup preserves identity and never assumes rejection or success',async()=>{
  const stored=storage();let posts=0;
  const client=new MutationClient({identity:()=> 'opaque-id',storage:stored,fetcher:async(path,options)=>{if(options.method)posts++;throw new Error('offline');}});
  await assert.rejects(client.execute('/candidates/import',{profile_id:'authored-private-id'}),/Outcome uncertain/);
  assert.equal(client.latest.state,'uncertain');assert.equal(client.blocked,true);assert.equal(posts,1);
  assert.deepEqual([...stored.map.values()],['opaque-id']);
});

test('saved failed evaluation is retained and still reports failure',async()=>{
  const applied=[];
  const client=new MutationClient({identity:()=> 'opaque-id',readableError:data=>data.detail.message,apply:async(op,result)=>applied.push(result),fetcher:async()=>reply({evaluation_run_id:'report',status:'partial',detail:{message:'Provider failed'}},502,{'X-Operation-State':'committed'})});
  await assert.rejects(client.execute('/evaluate',{}),error=>error.message==='502: Provider failed'&&error.report.status==='partial');
  assert.equal(client.blocked,false);assert.equal(applied[0].state,'committed');
});

test('cancellation creates a rejection before forgetting an unsent identity',async()=>{
  const stored=storage();stored.setItem('jobintel-pending-operation','opaque-id');
  let cancelled=false;
  const client=new MutationClient({storage:stored,fetcher:async(path,options)=>{if(options.method==='POST'){cancelled=true;return reply({operation_id:'opaque-id',state:'rejected',http_status:409,result:{detail:'Cancelled'}});}return reply({operation_id:'opaque-id',state:'not_received'});}});
  await assert.rejects(client.check(),/not received/);assert.equal(client.canRetry,false);
  await client.cancel();assert.equal(cancelled,true);assert.equal(client.blocked,false);assert.equal(stored.map.size,0);
});
