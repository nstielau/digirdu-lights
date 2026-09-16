const {test,beforeEach,after}=require('node:test');const assert=require('node:assert/strict');
if(process.env.FIRESTORE_EMULATOR_HOST!=='127.0.0.1:8081')throw new Error('Refusing non-local database tests');
const {Firestore}=require('@google-cloud/firestore');
const {createService}=require('../service.cjs');const c=require('../contract.cjs');
const db=new Firestore({projectId:'demo-digirdu'});
let clock=100000,svc=createService(db,()=>clock);
const id='4133c5792f0a',token='a'.repeat(64),email='owner@example.test';
function report(seq=1){return {device_id:id,board:c.BOARDS[1],role:'consumer',version:'1.0.0',base_version:'1.0.0',
 circuitpython:'10.3.1',protocol_send:3,protocol_receive:[3],session:'1'.repeat(16),report_sequence:seq,
 state:'current',deployment_sequence:0,error:'',health:{}};}
function manifest(ver='1.1.0',base='1.0.0'){
 const files=c.FILES.map(name=>({name,size:1,sha256:c.hash('x')}));
 return {schema:1,version:ver,git_commit:'a'.repeat(40),app_api:1,minimum_base:base,circuitpython:'10.3.1',
 boards:c.BOARDS,roles:['producer','consumer'],protocol_send:3,protocol_receive:[3],files,
 sha256:c.hash(files.map(f=>`${f.name}:${f.size}:${f.sha256}\n`).join(''))};
}
const admin={auth:{uid:'owner',token:{email,email_verified:true,firebase:{sign_in_provider:'google.com'}}},app:{appId:'test'}};
beforeEach(async()=>{
 await fetch('http://127.0.0.1:8081/emulator/v1/projects/demo-digirdu/databases/(default)/documents',{method:'DELETE'});
 clock=100000;await db.doc('devices/'+id).set({enabled:true,tokenHash:c.hash(token),board:c.BOARDS[1],role:'consumer'});
 await db.doc('admins/'+c.hash(email)).set({enabled:true});
 await db.doc('releases/1.1.0').set({approved:true,manifest:manifest()});
 await db.doc('channels/stable').set({version:'1.1.0',sequence:1});await db.doc('control/sequence').set({value:1});
});
after(()=>db.terminate());
test('check-in persists actual version and returns newest target',async()=>{
 const result=await svc.checkIn(id,token,report());assert.equal(result.manifest.version,'1.1.0');
 assert.equal((await db.doc('devices/'+id).get()).data().report.version,'1.0.0');
 const view=await svc.overview(admin);assert.equal(view.devices[0].report.version,'1.0.0');assert.ok(!JSON.stringify(view).includes(c.hash(token)));
});
test('bad credentials, disabled identity and cross-device reports rejected',async()=>{
 await assert.rejects(svc.checkIn(id,'b'.repeat(64),report()),e=>e.status===401);
 await assert.rejects(svc.checkIn(id,token,{...report(),device_id:'c'.repeat(12)}),e=>e.status===400);
 await db.doc('devices/'+id).update({enabled:false});await assert.rejects(svc.authenticate(id,token),e=>e.status===401);
});
test('repeat report is idempotent; older session cannot overwrite a newer report',async()=>{
 await svc.checkIn(id,token,report());await svc.checkIn(id,token,report());clock+=2000;
 await svc.checkIn(id,token,{...report(),session:'2'.repeat(16)});clock+=2000;
 await assert.rejects(svc.checkIn(id,token,report()),e=>e.status===409);
});
test('report-only does not select an update',async()=>{assert.equal((await svc.checkIn(id,token,report(),true)).manifest,null);});
test('pause, incompatible base and missing producer are independent',async()=>{
 await db.doc('devices/'+id).update({paused:true});assert.equal((await svc.checkIn(id,token,report())).reason,'paused');
 await db.doc('devices/'+id).update({paused:false});await db.doc('releases/1.1.0').update({manifest:manifest('1.1.0','9.0.0')});clock+=2000;
 assert.equal((await svc.checkIn(id,token,report(2))).manifest,null);
});
test('download requires assigned compatible bundle and exact file',async()=>{
 await svc.checkIn(id,token,report());const m=manifest();
 assert.equal((await svc.artifact(id,token,m.sha256,'effects.py')).size,1);
 await assert.rejects(svc.artifact(id,token,m.sha256,'../settings.toml'),e=>e.status===404);
 await db.doc('devices/'+id).update({paused:true});await assert.rejects(svc.artifact(id,token,m.sha256,'effects.py'),e=>e.status===404);
});
test('browser authentication, App Check and admin role all required',async()=>{
 for(const bad of [{},{...admin,app:null},{...admin,auth:{...admin.auth,token:{...admin.auth.token,email_verified:false}}},
  {...admin,auth:{...admin.auth,token:{...admin.auth.token,email:'other@example.test'}}}])await assert.rejects(svc.overview(bad));
});
test('pin rollback issues a newer sequence and retry is deduplicated',async()=>{
 await db.doc('releases/1.0.0').set({approved:true,manifest:manifest('1.0.0')});
 const req={...admin,data:{id,action:'pin',version:'1.0.0',requestId:'12345678-1234-1234-1234-123456789012',timestamp:clock}};
 await svc.change(req);await svc.change(req);const d=(await db.doc('devices/'+id).get()).data();assert.equal(d.sequence,2);assert.equal(d.pin,'1.0.0');
 await assert.rejects(svc.change({...req,data:{...req.data,version:'1.1.0'}}),e=>e.status===409);
});
test('revocation blocks subsequent admin mutation and device token',async()=>{
 await db.doc('admins/'+c.hash(email)).update({enabled:false});await assert.rejects(svc.change({...admin,data:{}}),e=>e.status===403);
 await db.doc('devices/'+id).update({tokenHash:null});await assert.rejects(svc.authenticate(id,token),e=>e.status===401);
});
test('newest compatible stable falls back below a base-incompatible release',async()=>{
 await db.doc('releases/2.0.0').set({approved:true,manifest:manifest('2.0.0','2.0.0')});
 await db.doc('channels/stable').set({version:'2.0.0',sequence:3});
 const result=await svc.checkIn(id,token,report());assert.equal(result.manifest.version,'1.1.0');assert.equal(result.manifest.sequence,3);
 assert.equal((await svc.artifact(id,token,manifest().sha256,'effects.py')).size,1);
});
test('direct unauthenticated Firestore reads are denied by deployed emulator rules',async()=>{
 const response=await fetch('http://127.0.0.1:8081/v1/projects/demo-digirdu/databases/(default)/documents/devices/'+id);
 assert.equal(response.status,403);
});
