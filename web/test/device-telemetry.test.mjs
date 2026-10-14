import {test} from 'node:test';
import assert from 'node:assert/strict';

test('summarizes recent consumer uploads and only paired observation intervals', async()=>{
  const {summarizeDeviceTelemetry}=await import('../device-telemetry.mjs');
  const counts={features:12,controls:3,rejected:4,native_drops:1,link_losses:2,
    skipped:0,audio_overruns:0,audio_discontinuities:0};
  const batches=[
    {device_id:'consumer-a',receivedAt:1000,record:{role:'consumer',counts,rssi:{mean:-76,min:-89,max:-64}}},
    {device_id:'consumer-a',receivedAt:2000,record:{role:'consumer',counts:{...counts,features:5,rejected:1},rssi:{mean:-71,min:-80,max:-61}}},
    {device_id:'consumer-b',receivedAt:3000,record:{role:'consumer',counts,rssi:null}}
  ];
  const sessions=[
    {producerDevice:'producer',producerDelivered:10,consumers:[{id:'consumer-a',missing:[3,7],unobserved:3}]},
    {producerDevice:null,producerDelivered:0,consumers:[{id:'consumer-a',missing:[],unobserved:0}]}
  ];
  const summary=summarizeDeviceTelemetry({id:'consumer-a',role:'consumer'},batches,sessions);
  assert.equal(summary.uploads,2);
  assert.equal(summary.features,17);
  assert.equal(summary.rejected,5);
  assert.equal(summary.nativeDrops,2);
  assert.equal(summary.linkLosses,4);
  assert.deepEqual(summary.matched,{observed:7,missing:2});
  assert.deepEqual(summary.rssi,{mean:-71,min:-80,max:-61});
  assert.deepEqual(summary.rssiHistory,{uploads:2,mean:-74,min:-89,max:-61});
  assert.equal(summary.lastUpload,2000);
});

test('producer summary separates native send outcomes from radio reception', async()=>{
  const {summarizeDeviceTelemetry}=await import('../device-telemetry.mjs');
  const counts={features:20,controls:2,rejected:0,native_drops:3,link_losses:0,
    skipped:4,audio_overruns:1,audio_discontinuities:2};
  const batches=[{device_id:'producer',receivedAt:1000,record:{role:'producer',counts,rssi:null,truncated_windows:9}}];
  const sessions=[{producerDevice:'producer',producerDelivered:16,producerFailures:2,producerUnknown:2}];
  const summary=summarizeDeviceTelemetry({id:'producer',role:'producer'},batches,sessions);
  assert.deepEqual(summary.send,{completed:16,failed:2,unresolved:2});
  assert.equal(summary.skipped,4);
  assert.equal(summary.nativeDrops,3);
  assert.equal(summary.audioDiscontinuities,2);
  assert.equal(summary.truncatedWindows,9);
  assert.equal(summarizeDeviceTelemetry({id:'new',role:'consumer'},batches,sessions),null);
});

test('a zero-reception latest upload does not inherit stale RSSI',async()=>{
  const {summarizeDeviceTelemetry}=await import('../device-telemetry.mjs');
  const counts={features:0,controls:0,rejected:0,native_drops:0,link_losses:0,
    skipped:0,audio_overruns:0,audio_discontinuities:0};
  const batches=[
    {device_id:'consumer',receivedAt:1000,record:{role:'consumer',counts,rssi:{mean:-70,min:-80,max:-60},truncated_windows:0}},
    {device_id:'consumer',receivedAt:2000,record:{role:'consumer',counts,rssi:null,truncated_windows:2}}
  ];
  const summary=summarizeDeviceTelemetry({id:'consumer',role:'consumer'},batches,[]);
  assert.equal(summary.rssi,null);
  assert.deepEqual(summary.rssiHistory,{uploads:1,mean:-70,min:-80,max:-60});
  assert.equal(summary.truncatedWindows,2);
  assert.equal(summary.lastUpload,2000);
});
