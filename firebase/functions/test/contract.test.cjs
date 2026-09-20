const {test}=require('node:test');const assert=require('node:assert/strict');
const c=require('../contract.cjs');
function manifest(){const files=c.FILES.map(name=>({name,size:1,sha256:c.hash('x')}));return {
 schema:1,version:'1.2.0',git_commit:'a'.repeat(40),app_api:1,minimum_base:'1.0.0',circuitpython:'10.3.1',
 boards:c.BOARDS,roles:['producer','consumer'],protocol_send:3,protocol_receive:[3],files,
 sha256:c.hash(files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''))};}
test('manifest and numeric semantic ordering',()=>{assert.equal(c.validateManifest(manifest()).version,'1.2.0');assert.ok(c.compare('1.10.0','1.9.0')>0);});
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
