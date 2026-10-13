import {overview,telemetry,change,currentUser} from './gateway.js';
import {initAccount} from './account.js';
import {describeDevice} from './view.mjs';
import {compareTelemetry,unmatchedTelemetry} from './telemetry.mjs';
const $=id=>document.getElementById(id);
let generation=0,busy=false;
function message(text){$('status').textContent=text;}
function locking(value){busy=value;document.querySelectorAll('#fleet button,#fleet select,#refresh').forEach(e=>e.disabled=value||e.dataset.revoked==='true');}
function render(data){
  $('stable').textContent=`Newest stable: ${data.stable?.version||'No release published'}`;
  $('devices').replaceChildren();
  for(const d of data.devices){
    const node=$('device-card').content.firstElementChild.cloneNode(true),v=describeDevice(d,data.stable);
    node.querySelector('h3').textContent=v.title;node.querySelector('.badge').textContent=v.state;
    node.querySelector('.identity').textContent=d.id;
    const dl=node.querySelector('dl');for(const [key,value]of Object.entries(v.fields)){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;dl.append(dt,dd);
    }
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
function renderTelemetry(data,devices){
  const target=$('telemetry');target.replaceChildren();
  const sessions=compareTelemetry(data.batches||[],devices);
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
    render(data);
    if(telemetryResult)renderTelemetry(telemetryResult.data,data.devices);
    else $('telemetry').textContent='RF telemetry is unavailable; refresh to retry.';
  }
}
$('refresh').onclick=async()=>{locking(true);try{await refresh();message('Reports refreshed.');}catch{message('Unable to load reports. Check your connection and administrator access.');}finally{locking(false);}};
initAccount(async user=>{
  generation++;$('refresh').hidden=!user;
  $('fleet').hidden=true;$('devices').replaceChildren();$('releases').replaceChildren();$('telemetry').replaceChildren();
  $('account').textContent=user?.email||'Sign in to manage your devices.';message('');
  if(user){try{await refresh();}catch{message('Administrator access is required, or the service is unavailable.');}}
});
