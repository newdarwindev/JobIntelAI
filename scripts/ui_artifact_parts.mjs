export function partitionFiles(files,limit=22*1024*1024,maxParts=4){
  const parts=[[]];let bytes=0;
  for(const file of files){
    if(!Number.isSafeInteger(file.bytes)||file.bytes<=0||file.bytes>limit)throw new Error('Evidence file exceeds the publication part limit.');
    if(bytes+file.bytes>limit){parts.push([]);bytes=0;}
    if(parts.length>maxParts)throw new Error('Evidence needs more publication parts than CI uploads.');
    parts.at(-1).push(file);bytes+=file.bytes;
  }
  if(!files.length)throw new Error('No evidence to publish.');
  return parts;
}
