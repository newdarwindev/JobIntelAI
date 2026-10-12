export const storedMutation = path => ['/jobs/import','/candidates/import','/evaluate'].includes(path)||/^\/jobs\/[^/]+\/(snapshots|fetch|extract|match)$/.test(path);
const storageKey = 'jobintel-pending-operation';

export class PendingOperationError extends Error {}

export class MutationClient {
  constructor({fetcher=globalThis.fetch.bind(globalThis),identity=()=>crypto.randomUUID(),storage,onChange=()=>{},apply=async()=>{},readableError=()=> 'Operation rejected.'}) {
    Object.assign(this,{fetcher,identity,storage,onChange,apply,readableError});
    const id=storage?.getItem(storageKey);
    this.pending=id?{id,path:null,encoded:null,context:null,timeout:20000}:null;
    this.latest=null;
  }

  get blocked(){return Boolean(this.pending);}
  get canRetry(){return this.blocked&&this.latest?.state==='not_received'&&this.pending.encoded!==null;}
  get canCancel(){return this.blocked&&this.latest?.state==='not_received';}

  notify(outcome){
    this.latest={...outcome,operation_id:this.pending?.id??outcome.operation_id,path:outcome.path??this.pending?.path};
    this.onChange(this.latest);
  }

  async execute(path,body,timeout=20000,context=null){
    if(this.pending)throw new PendingOperationError('Resolve the saved operation outcome before starting new work.');
    this.pending={id:this.identity(),path,encoded:JSON.stringify(body),timeout,context};
    try{this.storage?.setItem(storageKey,this.pending.id);}
    catch{this.notify({state:'not_received'});throw new PendingOperationError('Recovery identity could not be stored. No request was sent.');}
    this.notify({state:'pending'});
    return this.send();
  }

  async send(){
    const operation=this.pending;
    let response,result;
    try{
      response=await this.fetcher(operation.path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':operation.id},body:operation.encoded,signal:AbortSignal.timeout(operation.timeout)});
      result=await response.json();
    }catch{
      this.notify({state:'uncertain'});
      return this.check();
    }
    const state=response.headers.get('X-Operation-State');
    if(!['committed','rejected'].includes(state))return this.check();
    return this.finish({operation_id:operation.id,path:operation.path,state,http_status:response.status,result});
  }

  async check(){
    if(!this.pending)return;
    let record;
    try{
      const response=await this.fetcher(`/operations/${encodeURIComponent(this.pending.id)}`,{signal:AbortSignal.timeout(20000)});
      if(!response.ok)throw new Error();
      record=await response.json();
      if(record.operation_id.replaceAll('-','').toLowerCase()!==this.pending.id.replaceAll('-','').toLowerCase())throw new Error();
    }catch{
      this.notify({state:'uncertain'});
      throw new PendingOperationError('Connection unavailable or timed out. Outcome uncertain; check saved outcome before retrying.');
    }
    if(!['committed','rejected'].includes(record.state)){
      this.notify(record);
      throw new PendingOperationError(record.state==='not_received'?'Connection unavailable: operation not received. Retry the same operation identity, or cancel it before starting new work.':'Outcome uncertain: work may still be running. Check saved outcome; no new attempt was started.');
    }
    return this.finish(record);
  }

  async finish(outcome){
    const operation=this.pending;
    operation.path=outcome.path??operation.path;
    this.notify(outcome);
    try{await this.apply(operation,outcome);}
    catch{
      this.notify({...outcome,display_pending:true});
      throw new PendingOperationError('Saved outcome confirmed, but display refresh is unavailable. Check saved outcome again; do not repeat the mutation.');
    }
    this.storage?.removeItem(storageKey);
    this.pending=null;
    this.notify(outcome);
    if(outcome.http_status>=400){
      const error=new Error(`${outcome.http_status}: ${this.readableError(outcome.result)}`);
      if(outcome.result.evaluation_run_id){const {detail,...report}=outcome.result;error.report=report;}
      throw error;
    }
    return outcome.result;
  }

  async retry(){
    if(!this.canRetry)throw new PendingOperationError('Check saved outcome; this operation cannot be safely retransmitted.');
    this.notify({state:'pending'});
    return this.send();
  }

  async cancel(){
    if(!this.canCancel)throw new PendingOperationError('Only an operation confirmed not received can be cancelled.');
    let response,record;
    try{response=await this.fetcher(`/operations/${encodeURIComponent(this.pending.id)}/cancel-unsent`,{method:'POST',signal:AbortSignal.timeout(20000)});if(!response.ok)throw new Error();record=await response.json();}
    catch{return this.check();}
    if(record.state!=='rejected'){this.notify(record);throw new PendingOperationError('Work has already been reserved. Check saved outcome; cancellation did not restart or interrupt it.');}
    try{await this.finish(record);}catch(error){if(this.blocked)throw error;}
    return record;
  }
}
