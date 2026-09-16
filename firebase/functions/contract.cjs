const crypto = require('node:crypto');
const BOARDS = ['unexpectedmaker_feathers2', 'adafruit_feather_esp32_v2'];
const FILES = ['animation.py','app_version.py','audio_features.py','audio_spectrum.py','config.py',
  'effects.py','lights_app.py','radio_protocol.py','sound_reactive.py','wireless.py'];
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
    JSON.stringify(m.protocol_receive)!=='[3]' || !Array.isArray(m.files) || m.files.length!==FILES.length) {
    throw new Error('invalid_manifest');
  }
  const seen=new Set(); let size=0;
  for (const f of m.files) {
    if (!exact(f,['name','size','sha256']) || !FILES.includes(f.name) || seen.has(f.name) ||
      !Number.isInteger(f.size) || f.size<1 || f.size>65536 || !digest(f.sha256)) throw new Error('invalid_file');
    seen.add(f.name); size+=f.size;
  }
  const text=[...m.files].sort((a,b)=>a.name.localeCompare(b.name)).map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join('');
  if (size>262144 || !digest(m.sha256) || hash(text)!==m.sha256) throw new Error('invalid_bundle');
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
  return b;
}
module.exports={BOARDS,FILES,hash,digest,version,compare,validateManifest,validateReport,compatible};
