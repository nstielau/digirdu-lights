import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareTelemetry,unmatchedTelemetry} from '../telemetry.mjs';

const mask=(...bits)=>{const bytes=new Uint8Array(32);for(const bit of bits)bytes[bit>>3]|=1<<(bit&7);return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');};
const zero=mask();
const window=(session,base,fields={})=>({session,base,received:zero,attempted:zero,delivered:zero,failed:zero,controls:zero,...fields});
const batch=(device_id,role,windows,receivedAt=1000,epoch_uncertain=false)=>({device_id,receivedAt,record:{role,windows,epoch_uncertain,
 counts:{features:0,controls:0,skipped:0,rejected:0,native_drops:0,link_losses:0,audio_overruns:0,audio_discontinuities:0},rssi:null,truncated_windows:0}});

test('compare delivered features only within consumer observation range',()=>{
 const p=batch('p','producer',[window(7,0,{attempted:mask(1,2,3,4,5),delivered:mask(1,2,3,4),controls:mask(3)})]);
 const c=batch('c','consumer',[window(7,0,{received:mask(2,4),controls:mask(3)})]);
 const sessions=compareTelemetry([p,c],[{id:'p',role:'producer'},{id:'c',role:'consumer'}]);
 assert.equal(sessions.length,1);
 assert.deepEqual(sessions[0].consumers[0].missing,[ ]);
 assert.equal(sessions[0].consumers[0].unobserved,1); // sequence 1, before first observation
 assert.equal(sessions[0].producerFailures,0);
});

test('holes are missing, producer failures are separate, and absent nodes are unobserved',()=>{
 const p=batch('p','producer',[window(7,0,{attempted:mask(1,2,3,4),delivered:mask(1,2,4),failed:mask(3)})]);
 const c=batch('c','consumer',[window(7,0,{received:mask(1,4)})]);
 const s=compareTelemetry([p,c],[{id:'p',role:'producer'},{id:'c',role:'consumer'},{id:'d',role:'consumer'}])[0];
 assert.deepEqual(s.consumers[0].missing,[2]);
 assert.equal(s.producerFailures,1);
 assert.equal(s.consumers[1].unobserved,3);
});

test('late join after sequence wrap is marked ambiguous',()=>{
 const p=batch('p','producer',[window(7,65536,{attempted:mask(1),delivered:mask(1)})]);
 const c=batch('c','consumer',[window(7,0,{received:mask(1)})],1000,true);
 const s=compareTelemetry([p,c],[{id:'p',role:'producer'},{id:'c',role:'consumer'}])[0];
 assert.equal(s.consumers[0].ambiguous,true);
 assert.equal(s.consumers[0].unobserved,1);
});
test('consumer observation across first wrap retains known gap after wrap',()=>{
 const p=batch('p','producer',[window(7,65280,{attempted:mask(255),delivered:mask(255)}),
   window(7,65536,{attempted:mask(0,1,2),delivered:mask(0,1,2)})]);
 const c=batch('c','consumer',[window(7,65280,{received:mask(255)}),
   window(7,65536,{received:mask(0,2)})],1000,true);
 const s=compareTelemetry([p,c],[{id:'p',role:'producer'},{id:'c',role:'consumer'}])[0];
 assert.deepEqual(s.consumers[0].missing,[65537]);
 assert.equal(s.consumers[0].unobserved,0);
});
test('separate consumer boots do not turn their downtime into missing packets',()=>{
 const p=batch('p','producer',[window(7,0,{attempted:mask(1,2,3,4,5),delivered:mask(1,2,3,4,5)})]);
 const first=batch('c','consumer',[window(7,0,{received:mask(1)})]);
 const second=batch('c','consumer',[window(7,0,{received:mask(5)})],2000);
 const s=compareTelemetry([p,first,second],[{id:'p',role:'producer'},{id:'c',role:'consumer'}])[0];
 assert.deepEqual(s.consumers[0].missing,[]);
 assert.equal(s.consumers[0].unobserved,3);
});
test('zero-reception batches remain visible as unmatched evidence',()=>{
 const empty=batch('c','consumer',[],2000);
 empty.record.counts.native_drops=9;
 assert.equal(compareTelemetry([empty],[{id:'c',role:'consumer'}]).length,0);
 assert.equal(unmatchedTelemetry([empty],[{id:'c',name:'North',role:'consumer'}])[0].counts.native_drops,9);
});
test('boot-wide diagnostics retain scope and newest RSSI across producer sessions',()=>{
 const p=batch('p','producer',[window(7,0,{delivered:mask(1)}),window(8,0,{delivered:mask(2)})]);
 p.record.boot_id='producer-boot';p.record.counts.audio_overruns=3;
 const older=batch('c','consumer',[window(7,0,{received:mask(1)}),window(8,0,{received:mask(2)})],1000);
 older.record.boot_id='consumer-boot-a';older.record.counts.native_drops=4;
 older.record.rssi={min:-90,max:-80,mean:-85};
 const newer=batch('c','consumer',[window(8,0,{received:mask(2)})],2000);
 newer.record.boot_id='consumer-boot-b';newer.record.counts.native_drops=2;
 newer.record.rssi={min:-70,max:-60,mean:-65};
 const sessions=compareTelemetry([newer,p,older],[{id:'p',role:'producer'},{id:'c',role:'consumer'}]);
 const first=sessions.find(s=>s.id===7),second=sessions.find(s=>s.id===8);
 assert.equal(first.producerBootId,'producer-boot');
 assert.equal(first.producerOverruns,3);
 assert.equal(first.consumers[0].nativeDrops,4);
 assert.deepEqual(first.consumers[0].bootIds,['consumer-boot-a']);
 assert.equal(second.consumers[0].nativeDrops,6);
 assert.deepEqual(second.consumers[0].bootIds,['consumer-boot-b','consumer-boot-a']);
 assert.equal(second.consumers[0].rssi.mean,-65);
});
