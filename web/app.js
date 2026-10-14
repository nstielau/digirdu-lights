import {overview,telemetry,change,currentUser} from './gateway.js';
import {initAccount} from './account.js';
import {describeDevice} from './view.mjs';
import {compareTelemetry,unmatchedTelemetry} from './telemetry.mjs';
import {summarizeDeviceTelemetry} from './device-telemetry.mjs';
const $=id=>document.getElementById(id);
let generation=0,busy=false;
function message(text){$('status').textContent=text;}
function locking(value){busy=value;document.querySelectorAll('#devices button,#devices select,#refresh').forEach(e=>e.disabled=value||e.dataset.revoked==='true');}
const fleetTabs=['releases','devices','session-telemetry'];
function selectFleetTab(name){
  for(const key of fleetTabs){
    const active=key===name,tab=$('tab-'+key);
    tab.setAttribute('aria-selected',String(active));
    tab.tabIndex=active?0:-1;
    $('panel-'+key).hidden=!active;
  }
}
for(const [index,name] of fleetTabs.entries()){
  const tab=$('tab-'+name);
  tab.addEventListener('click',()=>selectFleetTab(name));
  tab.addEventListener('keydown',event=>{
    const next=event.key==='Home'?0:event.key==='End'?fleetTabs.length-1:
      event.key==='ArrowRight'?(index+1)%fleetTabs.length:
      event.key==='ArrowLeft'?(index+fleetTabs.length-1)%fleetTabs.length:-1;
    if(next<0)return;
    event.preventDefault();selectFleetTab(fleetTabs[next]);$('tab-'+fleetTabs[next]).focus();
  });
}
function addDiagnostic(list,label,value){
  const term=document.createElement('dt'),detail=document.createElement('dd');
  term.textContent=label;detail.textContent=String(value);list.append(term,detail);
}
function renderDeviceRf(node,device,batches,sessions){
  const section=node.querySelector('.device-rf'),list=section.querySelector('dl'),empty=section.querySelector('.rf-empty');
  if(!batches){empty.textContent='RF telemetry unavailable; refresh to retry.';empty.hidden=false;return;}
  const summary=summarizeDeviceTelemetry(device,batches,sessions);
  if(!summary){empty.textContent='No RF uploads for this device among the 40 most recent fleet uploads.';empty.hidden=false;return;}
  addDiagnostic(list,'Uploads',summary.uploads);
  addDiagnostic(list,'Latest upload',new Date(summary.lastUpload).toLocaleString());
  if(device.role==='consumer'){
    addDiagnostic(list,'Accepted features',summary.features);
    const paired=summary.matched;
    addDiagnostic(list,'Paired delivery (retained)',paired?
      `${paired.observed-paired.missing}/${paired.observed} (${Math.round(100*(paired.observed-paired.missing)/paired.observed)}%)`:
      summary.producerEvidence?'No paired interval yet':'Producer upload needed');
    addDiagnostic(list,'Latest RSSI',summary.rssi?
      `${summary.rssi.mean} dBm (${summary.rssi.min} to ${summary.rssi.max})`:'Unavailable in latest upload');
    const history=summary.rssiHistory;
    addDiagnostic(list,'RSSI history',history?
      `${history.mean} dBm (mean of ${history.uploads} upload${history.uploads===1?'':'s'}; range ${history.min} to ${history.max})`:'Unavailable');
    addDiagnostic(list,'Native RX drops',summary.nativeDrops);
    addDiagnostic(list,'Rejected packets',summary.rejected);
    addDiagnostic(list,'Link losses',summary.linkLosses);
  }else{
    addDiagnostic(list,'Feature attempts',summary.features);
    addDiagnostic(list,'Native completions (retained)',summary.send.completed);
    addDiagnostic(list,'Send failures (retained)',summary.send.failed);
    addDiagnostic(list,'Unresolved sends (retained)',summary.send.unresolved);
    addDiagnostic(list,'Skipped sends',summary.skipped);
    addDiagnostic(list,'Native RX drops',summary.nativeDrops);
    addDiagnostic(list,'Audio gaps',summary.audioDiscontinuities);
  }
  if(summary.truncatedWindows)addDiagnostic(list,'Truncated windows',summary.truncatedWindows);
}
function render(data,batches,sessions){
  $('stable').textContent=`Newest stable: ${data.stable?.version||'No release published'}`;
  $('devices').replaceChildren();
  for(const d of data.devices){
    const node=$('device-card').content.firstElementChild.cloneNode(true),v=describeDevice(d,data.stable);
    node.querySelector('h3').textContent=v.title;node.querySelector('.badge').textContent=v.state;
    node.querySelector('.identity').textContent=d.id;
    const dl=node.querySelector('dl');for(const [key,value]of Object.entries(v.fields)){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;dl.append(dt,dd);
    }
    renderDeviceRf(node,d,batches,sessions);
    const select=node.querySelector('select');for(const r of data.releases.filter(r=>!r.revoked)){
      const o=document.createElement('option');o.value=r.version;o.textContent=r.version;select.append(o);
    }
    node.querySelectorAll('button').forEach(button=>{
      button.disabled=!d.enabled;button.dataset.revoked=String(!d.enabled);
      button.addEventListener('click',async()=>{
        if(busy)return;const action=button.dataset.action;
        const payload={id:d.id,action,requestId:crypto.randomUUID(),timestamp:Date.now()};
        if(action==='pin'){if(!select.value)return;payload.version=select.value;}
        if(action==='rename'){const name=prompt('Device name',d.name||d.id);if(!name?.trim())return;payload.name=name.trim();}
        if(action==='disable'&&!confirm(`Revoke ${v.title}? Re-enrollment over USB will be needed to restore updates.`))return;
        locking(true);message('Saving…');
        try{await change(payload);await refresh();message('Saved. The device will receive its target at its next check-in.');}
        catch{message('Change could not be confirmed. Refresh reports before retrying.');}
        finally{locking(false);}
      });
    });
    $('devices').append(node);
  }
  if(!data.devices.length)$('devices').textContent='No devices enrolled yet.';
  $('releases').replaceChildren();for(const r of data.releases){
    const row=document.createElement('div');row.className='release';
    row.textContent=`${r.version}${r.revoked?' · revoked':''} · ${r.manifest.git_commit.slice(0,8)} · base ${r.manifest.minimum_base}+ · protocol ${r.manifest.protocol_send}`;
    $('releases').append(row);
  }
  $('fleet').hidden=false;
}
function renderTelemetry(data,devices,sessions){
  const target=$('telemetry');target.replaceChildren();
  const unmatched=unmatchedTelemetry(data.batches||[],devices);
  if(!sessions.length&&!unmatched.length){target.textContent='No RF sessions uploaded yet.';return;}
  for(const batch of unmatched){
    const row=document.createElement('p');row.className='card telemetry-row';
    row.textContent=`${batch.name} (${batch.role}) uploaded ${new Date(batch.receivedAt).toLocaleString()} with no accepted packets; boot totals: native drops ${batch.counts.native_drops}, rejected ${batch.counts.rejected}, link losses ${batch.counts.link_losses}. Producer session unobserved.`;
    target.append(row);
  }
  for(const session of sessions){
    const section=document.createElement('section');section.className='card telemetry-session';
    const heading=document.createElement('h3');heading.textContent=`Producer session ${session.id.toString(16).padStart(8,'0')}`;
    const summary=document.createElement('p');summary.textContent=`${session.producerDevice||'Producer record unavailable'} · uploaded ${new Date(session.receivedAt).toLocaleString()} · feature attempts ${session.producerAttempts}, native completions ${session.producerDelivered}, failures ${session.producerFailures}, unresolved ${session.producerUnknown}; producer boot ${session.producerBootId||'unknown'} totals: audio overruns ${session.producerOverruns}, discontinuities ${session.producerDiscontinuities}`;
    section.append(heading,summary);
    for(const consumer of session.consumers){
      const row=document.createElement('p');row.className='telemetry-row';
      const signal=consumer.rssi?`latest boot RSSI ${consumer.rssi.mean} dBm (${consumer.rssi.min} to ${consumer.rssi.max})`:'RSSI unavailable';
      const age=consumer.receivedAt?new Date(consumer.receivedAt).toLocaleString():'no upload';
      const examples=consumer.missing.length?` · missing IDs ${consumer.missing.slice(0,24).join(', ')}${consumer.missing.length>24?'…':''}`:'';
      row.textContent=`${consumer.name}: received ${consumer.received}, missing ${consumer.missing.length}, unobserved ${consumer.unobserved}${consumer.ambiguous?' (wrap epoch uncertain)':''}; boot totals (${consumer.bootIds.join(', ')||'unknown'}): native drops ${consumer.nativeDrops}, rejected ${consumer.rejected}, link losses ${consumer.linkLosses}; ${signal}; uploaded ${age}${examples}`;
      section.append(row);
    }
    target.append(section);
  }
}
async function refresh(){
  const current=generation;
  const [{data},telemetryResult]=await Promise.all([overview(),telemetry().catch(()=>null)]);
  if(current===generation&&currentUser()){
    const batches=telemetryResult?.data?.batches||null;
    const sessions=batches?compareTelemetry(batches,data.devices):[];
    render(data,batches,sessions);
    if(telemetryResult)renderTelemetry(telemetryResult.data,data.devices,sessions);
    else $('telemetry').textContent='RF telemetry is unavailable; refresh to retry.';
  }
}
$('refresh').onclick=async()=>{locking(true);try{await refresh();message('Reports refreshed.');}catch{message('Unable to load reports. Check your connection and administrator access.');}finally{locking(false);}};
initAccount(async user=>{
  generation++;$('refresh').hidden=!user;
  $('fleet').hidden=true;$('devices').replaceChildren();$('releases').replaceChildren();$('telemetry').replaceChildren();
  selectFleetTab('devices');
  $('account').textContent=user?.email||'Sign in to manage your devices.';message('');
  if(user){try{await refresh();}catch{message('Administrator access is required, or the service is unavailable.');}}
});
