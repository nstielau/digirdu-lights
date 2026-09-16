import {overview,change,currentUser} from './gateway.js';
import {initAccount} from './account.js';
import {describeDevice} from './view.mjs';
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
async function refresh(){const current=generation;const {data}=await overview();if(current===generation&&currentUser())render(data);}
$('refresh').onclick=async()=>{locking(true);try{await refresh();message('Reports refreshed.');}catch{message('Unable to load reports. Check your connection and administrator access.');}finally{locking(false);}};
initAccount(async user=>{
  generation++;$('refresh').hidden=!user;
  $('fleet').hidden=true;$('devices').replaceChildren();$('releases').replaceChildren();
  $('account').textContent=user?.email||'Sign in to manage your devices.';message('');
  if(user){try{await refresh();}catch{message('Administrator access is required, or the service is unavailable.');}}
});
