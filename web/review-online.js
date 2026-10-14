import {initAccount} from './account.js';
import {reviewCatalog,reviewRecording} from './gateway.js';

const recordingSelect=document.querySelector('#review-recording');
const selectedRecording=document.querySelector('#review-selected-recording');
const protectedContent=document.querySelector('#review-protected');
const retry=document.querySelector('#review-retry');

function permissionDenied(error){
 return error?.status===403||error?.code==='functions/permission-denied'||error?.code==='permission-denied';
}

function audioBlobUrl(payload){
 if(typeof payload?.audio_base64!=='string'||payload.audio_mime_type!=='audio/wav')throw new Error('Invalid recording audio');
 const binary=atob(payload.audio_base64),bytes=new Uint8Array(binary.length);
 for(let index=0;index<binary.length;index+=1)bytes[index]=binary.charCodeAt(index);
 return URL.createObjectURL(new Blob([bytes],{type:payload.audio_mime_type}));
}

export function initOnlineReview(renderer){
 let generation=0,currentUrl=null,catalog=[];
 function releaseAudio(){if(currentUrl){URL.revokeObjectURL(currentUrl);currentUrl=null;}}
 function clear(){generation++;releaseAudio();renderer.clearReview();recordingSelect.replaceChildren();selectedRecording.textContent='';retry.hidden=true;protectedContent.hidden=true;}
 async function loadRecording(id){
  const entry=catalog.find(recording=>recording.id===id);if(!entry)return;
  const requestGeneration=++generation;
  releaseAudio();renderer.clearReview();retry.hidden=true;protectedContent.hidden=false;
  renderer.setStatus(`Loading ${entry.name}…`);
  try{
   const {data}=await reviewRecording({id});
   if(requestGeneration!==generation)return;
   if(data?.id!==id||!data.bundle)throw new Error('Invalid recording response');
   currentUrl=audioBlobUrl(data);
   renderer.configureBundle({...data.bundle,audio_url:currentUrl},window.location.href);
   selectedRecording.textContent=`${entry.name} · ${(entry.duration_ms/1000).toFixed(2)} s`;
   renderer.setStatus('Review loaded.');
  }catch(error){
   if(requestGeneration!==generation)return;
   releaseAudio();renderer.clearReview();protectedContent.hidden=false;retry.hidden=false;
   renderer.setStatus('Recording could not load. Choose another recording or retry.',true);
  }
 }
 recordingSelect.addEventListener('change',()=>loadRecording(recordingSelect.value));
 retry.addEventListener('click',()=>loadRecording(recordingSelect.value));
 initAccount(async user=>{
  clear();
  if(!user){renderer.setStatus('Sign in with Google to review recordings.');return;}
  const requestGeneration=++generation;renderer.setStatus('Loading recording catalog…');
  try{
   const {data}=await reviewCatalog();
   if(requestGeneration!==generation)return;
   if(!Array.isArray(data?.recordings)||!data.recordings.length)throw new Error('Invalid recording catalog');
   catalog=data.recordings;
   catalog.forEach(entry=>{
    const option=document.createElement('option');option.value=entry.id;option.textContent=entry.name;recordingSelect.append(option);
   });
   protectedContent.hidden=false;
   await loadRecording(catalog[0].id);
  }catch(error){
   if(requestGeneration!==generation)return;
   protectedContent.hidden=true;
   renderer.setStatus(permissionDenied(error)?'Administrator access is required to review recordings.':'Recording catalog could not load.',true);
  }
 });
}
