import {test} from 'node:test';
import assert from 'node:assert/strict';
import {partitionFiles} from '../../scripts/ui_artifact_parts.mjs';
test('part boundaries retain every file once and respect an exact byte limit',()=>{
  const files=[{file:'metadata',bytes:2},{file:'a',bytes:8},{file:'b',bytes:6},{file:'c',bytes:4}];
  const parts=partitionFiles(files,10);assert.deepEqual(parts.flat(),files);assert.equal(parts.length,2);
  assert.deepEqual(parts.map(part=>part.reduce((sum,file)=>sum+file.bytes,0)),[10,10]);
});
test('oversize files, excessive parts and empty publication cannot silently lose evidence',()=>{
  assert.throws(()=>partitionFiles([{file:'oversize',bytes:11}],10));
  assert.throws(()=>partitionFiles(Array.from({length:5},(_,i)=>({file:String(i),bytes:10})),10,4));
  assert.throws(()=>partitionFiles([]));
});
