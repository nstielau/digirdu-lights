const {test}=require('node:test');const assert=require('node:assert/strict');
const c=require('../contract.cjs');
const LEGACY_FILES=['animation.py','app_version.py','audio_features.py','audio_spectrum.py','config.py',
  'effects.py','lights_app.py','radio_protocol.py','sound_reactive.py','wireless.py'];
function manifest(){const files=LEGACY_FILES.map(name=>({name,size:1,sha256:c.hash('x')}));return {
 schema:1,version:'1.2.0',git_commit:'a'.repeat(40),app_api:1,minimum_base:'1.0.0',circuitpython:'10.3.1',
 boards:c.LEGACY_BOARDS,roles:['producer','consumer'],protocol_send:3,protocol_receive:[3],files,
 sha256:c.hash(files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''))};}
test('manifest and numeric semantic ordering',()=>{assert.equal(c.validateManifest(manifest()).version,'1.2.0');assert.ok(c.compare('1.10.0','1.9.0')>0);});
test('reject paths, duplicated files, bad digest and incompatible packet version',()=>{
 for(const edit of [m=>m.files[0].name='../boot.py',m=>m.files[0]=m.files[1],m=>m.sha256='b'.repeat(64),m=>m.protocol_send=256,m=>m.extra=true]){
  const m=manifest();edit(m);assert.throws(()=>c.validateManifest(m));
 }
});
test('hardware and base compatibility',()=>{
 const m=manifest();assert.ok(c.compatible(m,{board:c.BOARDS[1],role:'consumer',base_version:'1.0.0',circuitpython:'10.3.1'}));
 assert.equal(c.compatible(m,{board:c.BOARDS[1],role:'producer',base_version:'1.0.0',circuitpython:'10.3.1'}),false);
});
test('schema 1 remains the strict legacy device contract',()=>{
 for(const edit of [m=>m.files=m.files.slice(0,2),m=>m.boards=[c.LEGACY_BOARDS[0]],
   m=>m.roles=['consumer'],m=>m.protocol_send=4,m=>m.protocol_receive=[3,4]]){
  const m=manifest();edit(m);
  m.sha256=c.hash([...m.files].sort((a,b)=>a.name.localeCompare(b.name))
    .map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''));
  assert.throws(()=>c.validateManifest(m));
 }
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

test('schema 2 accepts bounded telemetry module and requires its USB base',()=>{
 const old=manifest();assert.equal(c.validateManifest(old).schema,1);
 const m=manifest();m.schema=2;m.minimum_base='1.1.0';
 m.boards=[...old.boards,'adafruit_feather_esp32s3_reverse_tft'];
 for(const name of ['dashboard.py','device_setup.py','telemetry.py'])m.files.push({name,size:1,sha256:c.hash('x')});
 m.sha256=c.hash([...m.files].sort((a,b)=>a.name.localeCompare(b.name)).map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''));
 assert.equal(c.validateManifest(m).schema,2);
 assert.equal(c.compatible(m,{board:old.boards[0],role:'producer',base_version:'1.0.4',circuitpython:'10.3.1'}),false);
 for(const edit of [x=>x.schema=1,x=>x.minimum_base='1.0.4',x=>x.files.push({name:'../boot.py',size:1,sha256:c.hash('x')})]){
  const bad=structuredClone(m);edit(bad);assert.throws(()=>c.validateManifest(bad));
 }
 assert.equal(c.validateReport({...report(),board:m.boards[2]},'test').board,m.boards[2]);
});

test('telemetry accepts bounded producer and consumer packet evidence',()=>{
 const zero='00'.repeat(32),one='02'+zero.slice(2);
 const record=role=>({schema:1,role,boot_id:'c'.repeat(16),windows:[{session:7,base:0,
  received:role==='consumer'?one:zero,attempted:role==='producer'?one:zero,
  delivered:role==='producer'?one:zero,failed:zero,controls:zero}],
  counts:{features:1,controls:0,skipped:0,rejected:0,native_drops:0,link_losses:0,
   audio_overruns:0,audio_discontinuities:0},truncated_windows:0,epoch_uncertain:false,
  rssi:role==='consumer'?{min:-80,max:-70,mean:-75}:null});
 const batch={schema:1,device_id:'a'.repeat(16),batch_id:'b'.repeat(16),record:record('consumer')};
 assert.equal(c.validateTelemetry(batch,batch.device_id,'consumer').batch_id,batch.batch_id);
 assert.throws(()=>c.validateTelemetry(batch,batch.device_id,'producer'),/invalid_telemetry/);
});
