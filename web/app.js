import {overview,telemetry,change,currentUser} from './gateway.js';
import {initAccount} from './account.js';
import {describeDevice} from './view.mjs';
import {compareTelemetry,unmatchedTelemetry} from './telemetry.mjs';
import {summarizeDeviceTelemetry} from './device-telemetry.mjs';
import {sortDevices,sortReleases,sessionHealth} from './fleet-model.mjs';
import {fetchReleaseMetadata,githubReleaseUrl} from './release-metadata.mjs';
const $=id=>document.getElementById(id);
let generation=0,busy=false,lastSnapshot=null,releaseRequest=null,releaseMetadata=new Map();
let deviceSort={key:'checkin',direction:'desc'};
const expandedDevices=new Set(),expandedReleases=new Set();
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
for(const key of ['checkin','version'])$('sort-'+key).addEventListener('click',()=>{
  deviceSort=deviceSort.key===key?{key,direction:deviceSort.direction==='desc'?'asc':'desc'}:{key,direction:'desc'};
  if(lastSnapshot)renderDevices(...lastSnapshot);
});
$('device-sort').addEventListener('change',event=>{
  const [key,direction]=event.target.value.split('-');deviceSort={key,direction};
  if(lastSnapshot)renderDevices(...lastSnapshot);
});
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
function renderDevices(data,batches,sessions){
  lastSnapshot=[data,batches,sessions];
  $('device-sort').value=`${deviceSort.key}-${deviceSort.direction}`;
  for(const key of ['checkin','version'])$(''+key+'-heading').setAttribute('aria-sort',
    deviceSort.key===key?(deviceSort.direction==='desc'?'descending':'ascending'):'none');
  $('devices').replaceChildren();
  for(const d of sortDevices(data.devices,deviceSort.key,deviceSort.direction)){
    const node=$('device-card').content.firstElementChild.cloneNode(true),v=describeDevice(d,data.stable);
    node.querySelector('h3').textContent=v.title;node.querySelector('.badge').textContent=v.state;
    node.querySelector('.identity').textContent=d.id;
    const dl=node.querySelector('dl');for(const [key,value]of Object.entries(v.fields)){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;dl.append(dt,dd);
    }
    renderDeviceRf(node,d,batches,sessions);
    const select=node.querySelector('select');for(const r of sortReleases(data.releases.filter(r=>!r.revoked))){
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
    const summary=document.createElement('tr'),details=document.createElement('tr');
    summary.className='device-row';summary.dataset.deviceId=d.id;
    details.className='device-details';details.id=`device-details-${d.id}`;
    details.hidden=!expandedDevices.has(d.id);
    const name=document.createElement('td'),expand=document.createElement('button');
    expand.type='button';expand.className='device-expand';expand.textContent=v.title;
    expand.setAttribute('aria-controls',details.id);
    const toggle=()=>{
      details.hidden=!details.hidden;
      if(details.hidden)expandedDevices.delete(d.id);else expandedDevices.add(d.id);
      expand.setAttribute('aria-expanded',String(!details.hidden));
      expand.setAttribute('aria-label',`${details.hidden?'Expand':'Collapse'} ${v.title}`);
    };
    expand.setAttribute('aria-expanded',String(!details.hidden));
    expand.setAttribute('aria-label',`${details.hidden?'Expand':'Collapse'} ${v.title}`);
    expand.addEventListener('click',toggle);
    summary.addEventListener('click',event=>{if(!event.target.closest('button,a,select'))toggle();});
    name.append(expand,document.createElement('small'));name.querySelector('small').textContent=d.id;
    summary.append(name);
    for(const value of [`${d.role} / ${d.board}`,d.report?.version||'Not reported',
      d.report?.base_version||'Not reported',d.lastCheckIn?new Date(d.lastCheckIn).toLocaleString():'Never',v.state]){
      const cell=document.createElement('td');cell.textContent=value;summary.append(cell);
    }
    const detailCell=document.createElement('td');detailCell.colSpan=6;detailCell.append(node);details.append(detailCell);
    $('devices').append(summary,details);
  }
  if(!data.devices.length){
    const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=6;
    cell.textContent='No devices enrolled yet.';row.append(cell);$('devices').append(row);
  }
  if(busy)locking(true);
}
function releaseText(target,text){
  const plain=text.replace(/\*\*/g,'');
  const links=/https:\/\/[^\s)]+/g;let start=0,match;
  while((match=links.exec(plain))){
    target.append(document.createTextNode(plain.slice(start,match.index)));
    const link=document.createElement('a');link.href=match[0];link.textContent=match[0];
    link.target='_blank';link.rel='noopener noreferrer';target.append(link);
    start=links.lastIndex;
  }
  target.append(document.createTextNode(plain.slice(start)));
}
function fillReleaseNotes(target,body){
  target.replaceChildren();let list=null;
  for(const source of (body||'Release notes unavailable from GitHub.').split(/\r?\n/)){
    const line=source.trim();
    if(!line){list=null;continue;}
    const heading=/^#{1,4}\s+(.+)$/.exec(line),bullet=/^[-*]\s+(.+)$/.exec(line);
    if(heading){const title=document.createElement('h4');releaseText(title,heading[1]);target.append(title);list=null;}
    else if(bullet){
      if(!list){list=document.createElement('ul');target.append(list);}
      const item=document.createElement('li');releaseText(item,bullet[1]);list.append(item);
    }else{const paragraph=document.createElement('p');releaseText(paragraph,line);target.append(paragraph);list=null;}
  }
}
function renderReleases(releases){
  $('releases').replaceChildren();
  for(const r of sortReleases(releases)){
    const info=releaseMetadata.get(r.version),entry=document.createElement('section');
    entry.className='release-entry';entry.dataset.version=r.version;
    const line=document.createElement('div');line.className='release-line';
    const button=document.createElement('button');button.type='button';button.className='release-expand';
    button.textContent=`${r.version}${r.revoked?' · revoked':''}`;
    const notes=document.createElement('div');notes.className='release-notes';notes.id=`release-notes-${r.version}`;
    fillReleaseNotes(notes,info?.notes);
    notes.hidden=!expandedReleases.has(r.version);
    button.setAttribute('aria-expanded',String(!notes.hidden));button.setAttribute('aria-controls',notes.id);
    const toggle=()=>{
      notes.hidden=!notes.hidden;
      if(notes.hidden)expandedReleases.delete(r.version);else expandedReleases.add(r.version);
      button.setAttribute('aria-expanded',String(!notes.hidden));
    };
    button.addEventListener('click',toggle);
    line.addEventListener('click',event=>{if(!event.target.closest('button,a'))toggle();});
    const date=document.createElement('time');date.className='release-date';
    if(info?.publishedAt&&!Number.isNaN(Date.parse(info.publishedAt))){
      date.dateTime=info.publishedAt;
      date.textContent=new Date(info.publishedAt).toLocaleString('en-US',
        {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'});
    }else date.textContent='Date unavailable';
    const link=document.createElement('a');link.href=info?.url||githubReleaseUrl(r.version);
    link.textContent='GitHub release';link.target='_blank';link.rel='noopener noreferrer';
    line.append(button,date,link);
    const details=document.createElement('p');details.className='hint';
    details.textContent=`${r.manifest.git_commit.slice(0,8)} · base ${r.manifest.minimum_base}+ · protocol ${r.manifest.protocol_send}`;
    entry.append(line,details,notes);$('releases').append(entry);
  }
}
function render(data,batches,sessions){
  $('stable').textContent=`Newest stable: ${data.stable?.version||'No release published'}`;
  renderDevices(data,batches,sessions);
  renderReleases(data.releases);
  $('fleet').hidden=false;
}
function formatRate(result){
  if(result.percent===null)return `${result.count} (rate unavailable)`;
  const percent=Number.isInteger(result.percent)?result.percent.toFixed(0):result.percent.toFixed(1);
  return `${result.count}/${result.total} (${percent}%)`;
}
let tooltipNumber=0;
function telemetryMetric(parent,label,value,issue=false,explanation='',helpLabel=label){
  const metric=document.createElement('p');metric.className='telemetry-metric';
  if(issue)metric.classList.add('metric-issue');
  const content=document.createElement('span');content.textContent=`${label} ${value}`;metric.append(content);
  if(issue){
    const help=document.createElement('span'),button=document.createElement('button'),tip=document.createElement('span');
    help.className='issue-help';button.type='button';button.className='issue-tip';button.textContent='?';
    button.setAttribute('aria-label',`Explain ${helpLabel}`);
    tip.className='tooltip';tip.id=`telemetry-tooltip-${++tooltipNumber}`;tip.setAttribute('role','tooltip');
    tip.textContent=explanation;button.setAttribute('aria-describedby',tip.id);
    help.append(button,tip);metric.append(help);
  }
  parent.append(metric);
}
function renderTelemetry(data,devices,sessions){
  const target=$('telemetry');target.replaceChildren();
  const unmatched=unmatchedTelemetry(data.batches||[],devices);
  if(!sessions.length&&!unmatched.length){target.textContent='No sessions in the 40 most recent fleet uploads.';return;}
  for(const session of sessions){
    const section=document.createElement('section');section.className='card telemetry-session';
    const heading=document.createElement('h3');
    heading.textContent=`Session ${session.id.toString(16).padStart(8,'0')} · latest upload ${new Date(session.receivedAt).toLocaleString()}`;
    const duration=document.createElement('p');duration.className='hint';
    duration.textContent='Duration unavailable · Telemetry has no session start or end timestamp; upload time is when the cloud received it.';
    const health=sessionHealth(session);section.append(heading,duration);
    if(session.producerDevice){
      const producer=document.createElement('div');producer.className='telemetry-device';
      const name=devices.find(device=>device.id===session.producerDevice)?.name||session.producerDevice;
      const title=document.createElement('h4');title.textContent=`Producer ${name}`;producer.append(title);
      telemetryMetric(producer,'feature attempts',`${session.producerAttempts} (retained windows)`);
      telemetryMetric(producer,'native completions',session.producerDelivered);
      const failure={count:session.producerFailures,total:session.producerAttempts,percent:health.producer.failurePercent};
      telemetryMetric(producer,'send failures',formatRate(failure),health.producer.failureIssue,
        'At least 2% of 20 or more retained feature attempts failed in the native send callback. Check local radio state, ESP-NOW contention, power, or interference; this does not by itself measure over-air delivery.');
      const unresolved={count:session.producerUnknown,total:session.producerAttempts,percent:health.producer.unresolvedPercent};
      telemetryMetric(producer,'unresolved sends',formatRate(unresolved));
      telemetryMetric(producer,'audio overruns',`${session.producerOverruns} (boot total)`);
      telemetryMetric(producer,'audio gaps',`${session.producerDiscontinuities} (boot total)`);
      section.append(producer);
    }else{
      const notice=document.createElement('p');notice.textContent='Producer upload unavailable for this session.';section.append(notice);
    }
    for(const metric of health.consumers){
      const consumer=session.consumers.find(entry=>entry.id===metric.id);
      const row=document.createElement('div');row.className='telemetry-device';
      const title=document.createElement('h4');title.textContent=`Consumer ${consumer.name}`;row.append(title);
      const uploaded=document.createElement('p');uploaded.className='hint';
      uploaded.textContent=`Uploaded ${new Date(consumer.receivedAt).toLocaleString()} · boot ${consumer.bootIds.join(', ')||'unknown'}`;
      row.append(uploaded);
      telemetryMetric(row,'received',consumer.received);
      telemetryMetric(row,'missing',formatRate(metric.missing),metric.missing.issue,
        'At least 5% of 20 or more producer feature sends were missing inside this consumer\'s observed interval. Antenna placement, distance, interference, or power could contribute; time outside the interval is excluded.',
        'missing feature rate');
      telemetryMetric(row,'unobserved',consumer.unobserved);
      telemetryMetric(row,'native drops',`${formatRate(metric.nativeDrops)} (boot RX outcomes)`,metric.nativeDrops.issue,
        'At least 2% of 20 or more recorded receive outcomes failed at the native RX stage. Weak signal, antenna placement, interference, or local processing could contribute. These totals cover the whole consumer boot.');
      telemetryMetric(row,'rejected',`${formatRate(metric.rejected)} (boot RX outcomes)`,metric.rejected.issue,
        'At least 2% of 20 or more recorded receive outcomes were rejected. Check packet format, group, firmware compatibility, or corrupt reception. These totals cover the whole consumer boot.');
      telemetryMetric(row,'link losses',`${consumer.linkLosses} (boot total)`);
      telemetryMetric(row,'RSSI',consumer.rssi?
        `${consumer.rssi.mean} dBm (${consumer.rssi.min} to ${consumer.rssi.max})`:'unavailable',
        consumer.rssi?.mean<=-85,
        'Mean RSSI is at or below -85 dBm in this upload. Antenna placement, distance, enclosure shielding, or interference may contribute to weak reception.');
      if(consumer.ambiguous)telemetryMetric(row,'sequence wrap','epoch uncertain; missing rate may be incomplete');
      if(consumer.missing.length)telemetryMetric(row,'missing IDs',
        `${consumer.missing.slice(0,24).join(', ')}${consumer.missing.length>24?'…':''}`);
      section.append(row);
    }
    if(!health.consumers.length){
      const notice=document.createElement('p');notice.textContent='No consumers uploaded telemetry for this session.';section.append(notice);
    }
    target.append(section);
  }
  if(unmatched.length){
    const title=document.createElement('h3');title.textContent='Uploads without a session ID';target.append(title);
    for(const batch of unmatched){
      const row=document.createElement('p');row.className='card telemetry-row';
      row.textContent=`${batch.name} (${batch.role}) uploaded ${new Date(batch.receivedAt).toLocaleString()} with no session packets; boot totals: native drops ${batch.counts.native_drops}, rejected ${batch.counts.rejected}, link losses ${batch.counts.link_losses}. Producer session unobserved.`;
      target.append(row);
    }
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
    if(!releaseRequest){
      releaseRequest=fetchReleaseMetadata().then(metadata=>{
        releaseMetadata=metadata;
        if(currentUser()&&lastSnapshot)renderReleases(lastSnapshot[0].releases);
      }).catch(()=>{releaseRequest=null;});
    }
  }
}
$('refresh').onclick=async()=>{locking(true);try{await refresh();message('Reports refreshed.');}catch{message('Unable to load reports. Check your connection and administrator access.');}finally{locking(false);}};
initAccount(async user=>{
  generation++;$('refresh').hidden=!user;
  $('fleet').hidden=true;$('devices').replaceChildren();$('releases').replaceChildren();$('telemetry').replaceChildren();
  lastSnapshot=null;expandedDevices.clear();expandedReleases.clear();deviceSort={key:'checkin',direction:'desc'};
  selectFleetTab('devices');
  $('account').textContent=user?.email||'Sign in to manage your devices.';message('');
  if(user){try{await refresh();}catch{message('Administrator access is required, or the service is unavailable.');}}
});
