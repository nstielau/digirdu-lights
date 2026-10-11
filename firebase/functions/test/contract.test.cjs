const {test}=require('node:test');const assert=require('node:assert/strict');
const c=require('../contract.cjs');
function manifest(){const files=c.FILES.map(name=>({name,size:1,sha256:c.hash('x')}));return {
 schema:1,version:'1.2.0',git_commit:'a'.repeat(40),app_api:1,minimum_base:'1.0.0',circuitpython:'10.3.1',
 boards:c.BOARDS,roles:['producer','consumer'],protocol_send:3,protocol_receive:[3],files,
 sha256:c.hash(files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''))};}
test('manifest and numeric semantic ordering',()=>{assert.equal(c.validateManifest(manifest()).version,'1.2.0');assert.ok(c.compare('1.10.0','1.9.0')>0);});
test('manifest accepts bounded new app modules and old releases without a fixed file list',()=>{
 const old=manifest();old.version='1.0.8';old.files=old.files.filter(f=>f.name!=='telemetry.py');
 old.sha256=c.hash(old.files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''));
 assert.equal(c.validateManifest(old).version,'1.0.8');
 const dynamic=manifest();dynamic.files.push({name:'new_effect2.py',size:1,sha256:c.hash('x')});
 dynamic.files.sort((a,b)=>a.name.localeCompare(b.name));
 dynamic.sha256=c.hash(dynamic.files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''));
 assert.equal(c.validateManifest(dynamic).files.length,12);
 for(const name of ['palette.json','intro.bmp','frames.bin','effect.mpy'])assert.equal(c.safeAppName(name),true);
 for(const name of ['boot.py','code.py','node_config.py','ota_bootstrap.py','settings.toml','secrets.py',
  '../boot.py','/abs.py','a/b.py','a\\b.json','__import__.py','.hidden.json','a..json','a.json.py','a.PNG','a.json?x','a.'+'x'.repeat(9)])
  assert.equal(c.safeAppName(name),false);
 for(const name of ['palette.json','intro.bmp'])dynamic.files.push({name,size:1,sha256:c.hash('x')});
 dynamic.files.sort((a,b)=>a.name.localeCompare(b.name));
 dynamic.sha256=c.hash(dynamic.files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''));
 assert.equal(c.validateManifest(dynamic).files.length,14);
});
test('reject paths, duplicated files, bad digest and incompatible packet version',()=>{
 for(const edit of [m=>m.files[0].name='../boot.py',m=>m.files[0]=m.files[1],m=>m.sha256='b'.repeat(64),m=>m.protocol_send=2,m=>m.extra=true]){
  const m=manifest();edit(m);assert.throws(()=>c.validateManifest(m));
 }
});
test('hardware and base compatibility',()=>{
 const m=manifest();assert.ok(c.compatible(m,{board:c.BOARDS[1],role:'consumer',base_version:'1.0.0',circuitpython:'10.3.1'}));
 assert.equal(c.compatible(m,{board:c.BOARDS[1],role:'producer',base_version:'1.0.0',circuitpython:'10.3.1'}),false);
});
module.exports={manifest};

function report(){return {device_id:'test',board:c.BOARDS[1],role:'consumer',version:'1.0.7',base_version:'1.0.4',
 circuitpython:'10.3.1',protocol_send:3,protocol_receive:[3],session:'a'.repeat(16),report_sequence:1,
 state:'current',deployment_sequence:11,error:'',health:{}};}
test('optional battery reports preserve old devices and validate voltage/status pairs',()=>{
 assert.equal(c.validateReport(report(),'test').battery,undefined);
 for(const battery of [{voltage:3.87,status:'measured'},{voltage:null,status:'unsupported'},
   {voltage:null,status:'out_of_range'},{voltage:null,status:'read_error'}]) {
  assert.deepEqual(c.validateReport({...report(),battery},'test').battery,battery);
 }
 for(const battery of [null,{}, {voltage:0,status:'measured'},{voltage:NaN,status:'measured'},
   {voltage:6,status:'measured'},{voltage:'3.9',status:'measured'},{voltage:3.9,status:'unsupported'},
   {voltage:null,status:'measured'},{voltage:3.9,status:'measured',percent:100}]) {
  assert.throws(()=>c.validateReport({...report(),battery},'test'),/invalid_report/);
 }
});

function telemetry(role='consumer'){
 const zero='00'.repeat(32),one='02'+zero.slice(2);
 return {schema:1,device_id:'a'.repeat(16),batch_id:'b'.repeat(16),record:{
  schema:1,role,boot_id:'c'.repeat(16),windows:[{session:7,base:0,
   received:role==='consumer'?one:zero,attempted:role==='producer'?one:zero,
   delivered:role==='producer'?one:zero,failed:zero,controls:zero}],
  counts:{features:1,controls:0,skipped:0,rejected:0,native_drops:0,link_losses:0,audio_overruns:0,audio_discontinuities:0},
  truncated_windows:0,epoch_uncertain:false,rssi:role==='consumer'?{min:-80,max:-70,mean:-75}:null}};
}
test('telemetry accepts bounded packet evidence and rejects malformed or mismatched data',()=>{
 assert.equal(c.validateTelemetry(telemetry(),'a'.repeat(16),'consumer').batch_id,'b'.repeat(16));
 for(const edit of [b=>b.extra=true,b=>b.device_id='d'.repeat(16),b=>b.record.windows[0].received='xx',
  b=>b.record.windows[0].base=1,b=>b.record.windows[0].delivered='ff'.repeat(32),
  b=>b.record.windows=Array(129).fill(b.record.windows[0]),b=>b.record.rssi.mean=12]){
  const b=telemetry();edit(b);assert.throws(()=>c.validateTelemetry(b,'a'.repeat(16),'consumer'),/invalid_telemetry/);
 }
 assert.throws(()=>c.validateTelemetry(telemetry('producer'),'a'.repeat(16),'consumer'),/invalid_telemetry/);
});
module.exports.telemetry=telemetry;
