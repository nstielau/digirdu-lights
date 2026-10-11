const crypto = require('node:crypto');
const BOARDS = ['unexpectedmaker_feathers2', 'adafruit_feather_esp32_v2'];
const FILES = ['animation.py','app_version.py','audio_features.py','audio_spectrum.py','config.py',
  'effects.py','lights_app.py','radio_protocol.py','sound_reactive.py','telemetry.py','wireless.py'];
const RESERVED_APP_FILES=new Set(['boot.py','code.py','node_config.py','battery.py','ota_manifest.py',
  'ota_store.py','ota_http.py','ota_bootstrap.py','telemetry_store.py']);
const safeAppName=name=>typeof name==='string'&&/^[a-z][a-z0-9_]{0,39}\.py$/.test(name)&&!RESERVED_APP_FILES.has(name);
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const version = value => typeof value === 'string' && /^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})$/.test(value);
function compare(a,b) {
  if (!version(a) || !version(b)) throw new Error('invalid_version');
  const x=a.split('.').map(Number), y=b.split('.').map(Number);
  return x[0]-y[0] || x[1]-y[1] || x[2]-y[2];
}
function exact(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}
function validateManifest(m) {
  if (!exact(m, ['schema','version','git_commit','app_api','minimum_base','circuitpython','boards','roles',
    'protocol_send','protocol_receive','files','sha256']) || m.schema!==1 || !version(m.version) ||
    !/^[a-f0-9]{40}$/.test(m.git_commit) || m.app_api!==1 || !version(m.minimum_base) ||
    m.circuitpython!=='10.3.1' || JSON.stringify(m.boards)!==JSON.stringify(BOARDS) ||
    JSON.stringify(m.roles)!==JSON.stringify(['producer','consumer']) || m.protocol_send!==3 ||
    JSON.stringify(m.protocol_receive)!=='[3]' || !Array.isArray(m.files) || m.files.length<2 || m.files.length>24) {
    throw new Error('invalid_manifest');
  }
  const seen=new Set(); let size=0;
  for (const f of m.files) {
    if (!exact(f,['name','size','sha256']) || !safeAppName(f.name) || seen.has(f.name) ||
      !Number.isInteger(f.size) || f.size<1 || f.size>65536 || !digest(f.sha256)) throw new Error('invalid_file');
    seen.add(f.name); size+=f.size;
  }
  const text=[...m.files].sort((a,b)=>a.name.localeCompare(b.name)).map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join('');
  if (!seen.has('app_version.py')||!seen.has('lights_app.py')||size>262144 || !digest(m.sha256) || hash(text)!==m.sha256) throw new Error('invalid_bundle');
  return m;
}
function compatible(m, report) {
  return m.boards.includes(report.board) && m.roles.includes(report.role) &&
    !(report.board===BOARDS[1] && report.role!=='consumer') &&
    compare(report.base_version,m.minimum_base)>=0 && report.circuitpython===m.circuitpython;
}
function validateReport(b,id) {
  const keys=['device_id','board','role','version','base_version','circuitpython','protocol_send',
    'protocol_receive','session','report_sequence','state','deployment_sequence','error','health'];
  // Optional for older USB bases; when present, validate the complete reading.
  if (Object.hasOwn(b || {},'battery')) keys.push('battery');
  if (!exact(b,keys) || b.device_id!==id || !BOARDS.includes(b.board) || !['producer','consumer'].includes(b.role) ||
    (b.board===BOARDS[1] && b.role!=='consumer') || !version(b.version) || !version(b.base_version) ||
    !version(b.circuitpython) || !Number.isInteger(b.protocol_send) || !Array.isArray(b.protocol_receive) ||
    b.protocol_receive.length>4 || b.protocol_receive.some(v=>!Number.isInteger(v)||v<1||v>255) ||
    !/^[a-f0-9]{16}$/.test(b.session) || !Number.isInteger(b.report_sequence) || b.report_sequence<1 || b.report_sequence>1000 ||
    !['recovery','current','trial','rolled_back'].includes(b.state) || !Number.isInteger(b.deployment_sequence) ||
    b.deployment_sequence<0 || b.deployment_sequence>2147483647 || typeof b.error!=='string' || b.error.length>80 ||
    !b.health || typeof b.health!=='object' || Array.isArray(b.health) ||
    Object.keys(b.health).some(k=>!['frames','active','received','sent'].includes(k)) ||
    Object.entries(b.health).some(([k,v])=>k==='active'?typeof v!=='boolean':!Number.isInteger(v)||v<0||v>2147483647)) {
    throw new Error('invalid_report');
  }
  if (Object.hasOwn(b,'battery')) {
    const reading=b.battery;
    if (!exact(reading,['voltage','status']) ||
      !['measured','unsupported','out_of_range','read_error'].includes(reading.status) ||
      (reading.status==='measured' ? typeof reading.voltage!=='number' || !Number.isFinite(reading.voltage) ||
        reading.voltage<2 || reading.voltage>4.5 : reading.voltage!==null)) throw new Error('invalid_report');
  }
  return b;
}
const hex16=value=>typeof value==='string'&&/^[a-f0-9]{16}$/.test(value);
const mask=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const count=value=>Number.isInteger(value)&&value>=0&&value<=1000000000;
function validateTelemetry(b,id,role) {
 const invalid=()=>{throw new Error('invalid_telemetry');};
 if(!exact(b,['schema','device_id','batch_id','record'])||b.schema!==1||b.device_id!==id||!hex16(b.batch_id)||
    Buffer.byteLength(JSON.stringify(b))>49152)invalid();
 const r=b.record;
 if(!exact(r,['schema','role','boot_id','windows','counts','truncated_windows','epoch_uncertain','rssi'])||
    r.schema!==1||r.role!==role||!hex16(r.boot_id)||!Array.isArray(r.windows)||r.windows.length>128||
    !count(r.truncated_windows)||typeof r.epoch_uncertain!=='boolean'||
    !exact(r.counts,['features','controls','skipped','rejected','native_drops','link_losses','audio_overruns','audio_discontinuities'])||
    Object.values(r.counts).some(v=>!count(v)))invalid();
 if(r.rssi!==null && (!exact(r.rssi,['min','max','mean'])||
   Object.values(r.rssi).some(v=>!Number.isInteger(v)||v< -128||v>0)||
   r.rssi.min>r.rssi.mean||r.rssi.mean>r.rssi.max))invalid();
 if(role==='producer'&&r.rssi!==null)invalid();
 const seen=new Set();
 for(const w of r.windows){
  if(!exact(w,['session','base','received','attempted','delivered','failed','controls'])||
    !Number.isInteger(w.session)||w.session<0||w.session>0xffffffff||
    !Number.isInteger(w.base)||w.base<0||w.base>100000000||w.base%256!==0||
    ![w.received,w.attempted,w.delivered,w.failed,w.controls].every(mask))invalid();
  const key=`${w.session}:${w.base}`;if(seen.has(key))invalid();seen.add(key);
  if(role==='producer'&&w.received!== '00'.repeat(32))invalid();
  if(role==='consumer'&&[w.attempted,w.delivered,w.failed].some(v=>v!=='00'.repeat(32)))invalid();
  for(let i=0;i<64;i+=2){
   const a=parseInt(w.attempted.slice(i,i+2),16),d=parseInt(w.delivered.slice(i,i+2),16),
     f=parseInt(w.failed.slice(i,i+2),16),c=parseInt(w.controls.slice(i,i+2),16),
     received=parseInt(w.received.slice(i,i+2),16);
   if((d&~a)||(f&~a)||(d&f)||(role==='producer'&&(c&~a))||
      (role==='consumer'&&(c&received)))invalid();
  }
 }
 return b;
}
module.exports={BOARDS,FILES,safeAppName,hash,digest,version,compare,validateManifest,validateReport,validateTelemetry,compatible};
