const recordingSelect=document.querySelector('#review-recording');
const selectedRecording=document.querySelector('#review-selected-recording');
const protectedContent=document.querySelector('#review-protected');
const retry=document.querySelector('#review-retry');
const audio=document.querySelector('#review-audio');
const RECORDING_ID=/^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function normalizeCatalog(value){
 if(value?.schema_version!==1||!Array.isArray(value.recordings)||!value.recordings.length)throw new Error('Invalid local recording catalog');
 const seen=new Set();
 return value.recordings.map(entry=>{
  if(!RECORDING_ID.test(entry?.id)||seen.has(entry.id)||typeof entry.name!=='string'||!entry.name.trim()||!Number.isFinite(entry.duration_ms)||entry.duration_ms<=0)throw new Error('Invalid local recording catalog');
  seen.add(entry.id);
  return {...entry,name:entry.name.trim()};
 });
}

export function initLocalReview(renderer,catalogUrl){
 let generation=0,catalog=[],catalogResponseUrl=catalogUrl,currentRecording=null,retryAction=()=>loadCatalog();

 function showControls(){protectedContent.hidden=false;}
 function showRetry(action,label){retryAction=action;retry.textContent=label;retry.hidden=false;}

 async function loadRecording(id){
  const entry=catalog.find(recording=>recording.id===id);if(!entry)return;
  const requestGeneration=++generation;
  currentRecording=null;
  renderer.clearReview();showControls();retry.hidden=true;recordingSelect.disabled=true;
  renderer.setStatus(`Loading ${entry.name}…`);
  try{
   const bundleUrl=new URL(`${entry.id}/bundle.json`,catalogResponseUrl);
   const response=await fetch(bundleUrl,{cache:'no-store'});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const bundle=await response.json();
   if(requestGeneration!==generation)return;
   const audioUrl=new URL(`${entry.id}/audio.wav`,catalogResponseUrl).href;
   currentRecording=entry;
   renderer.configureBundle({...bundle,audio_url:audioUrl},response.url);
   recordingSelect.value=entry.id;recordingSelect.disabled=false;
   selectedRecording.textContent=`${entry.name} · ${(bundle.duration_ms/1000).toFixed(2)} s`;
   renderer.setStatus('Review loaded.');
  }catch(error){
   if(requestGeneration!==generation)return;
   currentRecording=null;
   renderer.clearReview();showControls();recordingSelect.disabled=false;
   showRetry(()=>loadRecording(entry.id),'Retry recording');
   renderer.setStatus('Local recording could not load. Choose another recording or retry.',true);
  }
 }

 async function loadCatalog(){
  const requestGeneration=++generation;
  currentRecording=null;
  renderer.clearReview();showControls();retry.hidden=true;recordingSelect.disabled=true;
  recordingSelect.replaceChildren();selectedRecording.textContent='';
  renderer.setStatus('Loading local recording catalog…');
  try{
   const response=await fetch(catalogUrl,{cache:'no-store'});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const loadedCatalog=normalizeCatalog(await response.json());
   if(requestGeneration!==generation)return;
   catalog=loadedCatalog;catalogResponseUrl=response.url;
   catalog.forEach(entry=>{
    const option=document.createElement('option');option.value=entry.id;option.textContent=entry.name;recordingSelect.append(option);
   });
   recordingSelect.disabled=false;
   await loadRecording(catalog[0].id);
  }catch(error){
   if(requestGeneration!==generation)return;
   renderer.clearReview();showControls();recordingSelect.disabled=true;
   showRetry(()=>loadCatalog(),'Retry catalog');
   renderer.setStatus('Local recording catalog could not load.',true);
  }
 }

 recordingSelect.addEventListener('change',()=>loadRecording(recordingSelect.value));
 audio.addEventListener('error',()=>{
  const entry=currentRecording;if(!entry)return;
  recordingSelect.disabled=false;
  showRetry(()=>loadRecording(entry.id),'Retry recording');
  renderer.setStatus('Audio could not load for this review. Retry the recording.',true);
 });
 retry.addEventListener('click',()=>retryAction());
 loadCatalog();
}
