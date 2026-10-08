const fs=require('node:fs');
const path=require('node:path');

const ID=/^[a-z0-9]+(?:-[a-z0-9]+)*$/;
function fail(message,status=500){const error=new Error(message);error.status=status;throw error;}
function object(value){return value&&typeof value==='object'&&!Array.isArray(value);}

function createReviewLibrary(root){
 root=path.resolve(root);
 let catalog;
 try{catalog=JSON.parse(fs.readFileSync(path.join(root,'catalog.json'),'utf8'));}
 catch{fail('review_catalog_unavailable');}
 if(!object(catalog)||catalog.schema_version!==1||!Array.isArray(catalog.recordings)||!catalog.recordings.length){
  fail('invalid_review_catalog');
 }
 const entries=new Map();
 for(const entry of catalog.recordings){
  if(!object(entry)||!ID.test(entry.id||'')||entries.has(entry.id)||typeof entry.name!=='string'||!entry.name||
    !Number.isInteger(entry.duration_ms)||entry.duration_ms<=0||!object(entry.label_counts)||!object(entry.event_counts)){
   fail('invalid_review_catalog');
  }
  entries.set(entry.id,entry);
 }
 return {
  catalog:()=>JSON.parse(JSON.stringify(catalog)),
  recording:id=>{
   if(typeof id!=='string'||!ID.test(id))fail('invalid_recording_id',400);
   const entry=entries.get(id);if(!entry)fail('recording_not_found',404);
   const directory=path.join(root,id);
   let bundle,audio;
   try{
    bundle=JSON.parse(fs.readFileSync(path.join(directory,'bundle.json'),'utf8'));
    audio=fs.readFileSync(path.join(directory,'audio.wav'));
   }catch{fail('review_recording_unavailable');}
   if(!object(bundle)||bundle.duration_ms!==entry.duration_ms||!audio.length)fail('invalid_review_recording');
   return {id,bundle,audio_mime_type:'audio/wav',audio_base64:audio.toString('base64')};
  }
 };
}

function createReviewHandlers(authorize,library){
 if(typeof authorize!=='function'||!library)throw new TypeError('Review handlers require authorization and a library');
 return {
  catalog:async request=>{await authorize(request);return library.catalog();},
  recording:async request=>{await authorize(request);return library.recording(request.data?.id);}
 };
}

module.exports={createReviewHandlers,createReviewLibrary};
