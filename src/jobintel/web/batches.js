// Session recovery stores identifiers and states; posting/profile bodies stay in memory.
const key='jobintel-corpus-batches';
export const batchLimit=20;
const savedId=result=>result?.match_run_id??result?.run_id??result?.snapshot_id??null;
const safeAttempt=a=>({operation_id:a.operation_id,stage:a.stage,state:a.state,http_status:a.http_status??null,result_id:a.result_id??null});

export class CorpusBatches {
  constructor({storage,identity=()=>crypto.randomUUID(),onChange=()=>{}}={}){
    Object.assign(this,{storage,identity,onChange});
    this.entries=new Map();
    try{const saved=JSON.parse(storage?.getItem(key)??'[]');for(const batch of saved){batch.running=false;batch.refreshError=null;this.entries.set(batch.kind,batch);}}
    catch{this.restoreError='Batch journal unavailable. Resolve any saved operation before starting new work.';}
  }
  get(kind){return this.entries.get(kind);}
  remaining(kind){return this.get(kind)?.items.filter(item=>item.state!=='completed')??[];}
  counts(batch){return Object.fromEntries(['completed','failed','unattempted','uncertain','running'].map(state=>[state,batch.items.filter(item=>item.state===state).length]));}
  start(kind,jobs,selection={}){
    if(this.remaining(kind).length)throw new Error('Continue the remaining items in this batch before starting another.');
    const batch={id:this.identity(),kind,selection:{...selection},running:false,refreshError:null,registry:{state:kind==='extraction'?'unattempted':'completed',attempts:[]},items:jobs.map(job=>({...job,state:'unattempted',attempts:[],error:null,resultId:null}))};
    this.entries.set(kind,batch);this.changed();return batch;
  }
  changed(){
    const saved=[...this.entries.values()].map(batch=>({id:batch.id,kind:batch.kind,selection:batch.selection,registry:{state:batch.registry.state,attempts:batch.registry.attempts.map(safeAttempt)},items:batch.items.map(item=>({jobId:item.jobId,stage:item.stage,expectedSnapshotId:item.expectedSnapshotId??null,snapshotId:item.snapshotId??null,expectedRunId:item.expectedRunId??null,state:item.state==='running'?'uncertain':item.state,resultId:item.resultId??null,attempts:item.attempts.map(safeAttempt)}))}));
    this.storage?.setItem(key,JSON.stringify(saved));this.onChange();
  }
  context(kind,jobId,stage){const batch=this.get(kind);return {kind,batchId:batch.id,jobId,stage};}
  pendingContext(operationId){
    for(const batch of this.entries.values()){
      for(const item of [batch.registry,...batch.items]){
        const attempt=item.attempts.find(a=>a.operation_id.replaceAll('-','')===operationId.replaceAll('-',''));
        if(attempt)return this.context(batch.kind,item.jobId??null,attempt.stage);
      }
    }
    return null;
  }
  unresolvedOperation(){
    for(const batch of this.entries.values())for(const item of [batch.registry,...batch.items]){
      if(item.state==='uncertain')return item.attempts.at(-1)?.operation_id??null;
    }
    return null;
  }
  observe(context,outcome,errorText){
    if(!context)return;
    const batch=this.get(context.kind);if(batch?.id!==context.batchId)return;
    const item=context.jobId===null?batch.registry:batch.items.find(i=>i.jobId===context.jobId);
    if(!item)return;
    let attempt=item.attempts.find(a=>a.operation_id.replaceAll('-','')===outcome.operation_id.replaceAll('-',''));
    if(!attempt){attempt={operation_id:outcome.operation_id,stage:context.stage};item.attempts.push(attempt);}
    Object.assign(attempt,{state:outcome.state,http_status:outcome.http_status??null,result_id:savedId(outcome.result)});
    if(outcome.state==='committed'&&outcome.http_status<400){
      item.error=null;
      if(context.stage==='snapshot'){item.snapshotId=outcome.result.snapshot_id;item.stage='extract';item.state='unattempted';}
      else{item.state='completed';item.resultId=savedId(outcome.result);}
    }else if(['committed','rejected'].includes(outcome.state)){
      item.state='failed';item.error=`${outcome.http_status}: ${errorText(outcome.result)}`;attempt.error=item.error;
    }else item.state=outcome.state==='pending'?'running':'uncertain';
    this.changed();
  }
  async restoreErrors(read,errorText){
    for(const batch of this.entries.values())for(const item of [batch.registry,...batch.items]){
      for(const attempt of item.attempts.filter(a=>a.http_status>=400)){
        try{const saved=await read(`/operations/${encodeURIComponent(attempt.operation_id)}`);attempt.error=`${saved.http_status}: ${errorText(saved.result)}`;}
        catch{attempt.error='Saved error details unavailable; check this operation identity when the server is ready.';}
      }
      if(item.state==='failed')item.error=item.attempts.at(-1)?.error??item.error;
    }
    this.onChange();
  }
  fail(item,error){if(!['completed','failed','uncertain'].includes(item.state)){item.state='failed';item.error=error.message;}this.changed();}
  async run(kind,{blocked,prepare,process,refresh}){
    const batch=this.get(kind);
    if(batch.running||blocked()||batch.items.some(item=>item.state==='uncertain'))throw new Error('Resolve the saved operation outcome before continuing this batch.');
    batch.running=true;batch.refreshError=null;this.changed();
    try{
      await prepare(batch);
      const remaining=this.remaining(kind).slice(0,batchLimit);
      for(const item of remaining){
        try{await process(item,batch);}catch(error){this.fail(item,error);break;}
        if(item.state!=='completed')break;
      }
    }catch(error){batch.error=error.message;}
    finally{
      try{await refresh();batch.refreshError=null;}catch(error){batch.refreshError=error.message;}
      batch.running=false;this.changed();
    }
    return batch;
  }
  replan(kind,jobs){
    const batch=this.get(kind),byId=new Map(jobs.map(job=>[job.job_id,job]));
    for(const item of this.remaining(kind)){
      if(item.state==='uncertain')throw new Error('Reconcile the saved operation before changing batch inputs.');
      const job=byId.get(item.jobId);
      item.expectedSnapshotId=job?.snapshot?.id??null;
      item.snapshotId=job?.snapshot?.id??null;
      item.expectedRunId=job?.extraction?.run_id??null;
      item.stage=kind==='matching'?'match':item.snapshotId?'extract':'snapshot';
      item.state='unattempted';item.error=null;
    }
    batch.error=null;this.changed();
  }
}
