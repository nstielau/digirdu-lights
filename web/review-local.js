const recordingSelect=document.querySelector('#review-recording');
const selectedRecording=document.querySelector('#review-selected-recording');
const protectedContent=document.querySelector('#review-protected');
const retry=document.querySelector('#review-retry');
const RECORDING_ID=/^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function normalizeCatalog(value){
 if(value?.schema_version!==1||!Array.isArray(value.recordings)||!value.recordings.length)throw new Error('Invalid recording catalog');
 return value.recordings.map(entry=>{
  if(!RECORDING_ID.test(entry?.id)||typeof entry?.name!=='string'||!entry.name.trim()||!Number.isFinite(entry?.duration_ms)||entry.duration_ms<=0){
   throw new Error('Invalid recording catalog');
  }
  return {...entry,name:entry.name.trim()};
 });
}

export async function initLocalReview(renderer,catalogUrl){
 let generation=0,catalog=[];
 const resolvedCatalogUrl=new URL(catalogUrl,window.location.href);
 async function loadRecording(id){
  const entry=catalog.find(recording=>recording.id===id);if(!entry)return;
  const requestGeneration=++generation;
  renderer.clearReview();retry.hidden=true;protectedContent.hidden=false;
  renderer.setStatus(`Loading ${entry.name}…`);
  try{
   const recordingRoot=new URL(`./${encodeURIComponent(entry.id)}/`,resolvedCatalogUrl);
   const response=await fetch(new URL('bundle.json',recordingRoot),{cache:'no-store'});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   const bundle=await response.json();
   if(requestGeneration!==generation)return;
   renderer.configureBundle({...bundle,audio_url:new URL('audio.wav',recordingRoot).href},response.url);
   selectedRecording.textContent=`${entry.name} · ${(entry.duration_ms/1000).toFixed(2)} s`;
   renderer.setStatus('Review loaded.');
  }catch(error){
   if(requestGeneration!==generation)return;
   renderer.clearReview();protectedContent.hidden=false;retry.hidden=false;
   renderer.setStatus('Recording could not load. Choose another recording or retry.',true);
  }
 }
 recordingSelect.addEventListener('change',()=>loadRecording(recordingSelect.value));
 retry.addEventListener('click',()=>loadRecording(recordingSelect.value));
 renderer.clearReview();protectedContent.hidden=false;retry.hidden=true;
 renderer.setStatus('Loading recording catalog…');
 try{
  const response=await fetch(resolvedCatalogUrl,{cache:'no-store'});
  if(!response.ok)throw new Error(`HTTP ${response.status}`);
  catalog=normalizeCatalog(await response.json());
  catalog.forEach(entry=>{
   const option=document.createElement('option');option.value=entry.id;option.textContent=entry.name;recordingSelect.append(option);
  });
  await loadRecording(catalog[0].id);
 }catch(error){
  protectedContent.hidden=false;
  renderer.setStatus('Recording catalog could not load.',true);
 }
}
