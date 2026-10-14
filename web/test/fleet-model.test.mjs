import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sortDevices,sortReleases,sessionHealth} from '../fleet-model.mjs';
import {fetchReleaseMetadata,githubReleaseUrl} from '../release-metadata.mjs';

test('device sorting puts unknown reports last and compares numeric versions',()=>{
  const devices=[
    {id:'old',lastCheckIn:100,report:{version:'1.1.9'}},
    {id:'new',lastCheckIn:300,report:{version:'1.1.10'}},
    {id:'missing',lastCheckIn:null,report:null},
    {id:'middle',lastCheckIn:200,report:{version:'1.1.2'}}
  ];
  assert.deepEqual(sortDevices(devices,'checkin','desc').map(d=>d.id),['new','middle','old','missing']);
  assert.deepEqual(sortDevices(devices,'checkin','asc').map(d=>d.id),['old','middle','new','missing']);
  assert.deepEqual(sortDevices(devices,'version','desc').map(d=>d.id),['new','old','middle','missing']);
  assert.deepEqual(sortDevices(devices,'version','asc').map(d=>d.id),['middle','old','new','missing']);
  assert.equal(devices[0].id,'old');
});

test('releases sort by numeric version newest first',()=>{
  const releases=['1.1.9','1.0.8','1.1.10','1.1.2'].map(version=>({version}));
  assert.deepEqual(sortReleases(releases).map(r=>r.version),['1.1.10','1.1.9','1.1.2','1.0.8']);
});

test('session rates use comparable denominators and only uploaded consumers',()=>{
  const session={producerDevice:'producer',producerAttempts:100,producerDelivered:95,
    producerFailures:5,producerUnknown:0,consumers:[
      {id:'one',receivedAt:1000,unobserved:15,missing:Array(8).fill(1),
        rxAccepted:90,nativeDrops:5,rejected:5,rssi:{mean:-88}},
      {id:'absent',receivedAt:null,unobserved:95,missing:[],
        rxAccepted:0,nativeDrops:0,rejected:0,rssi:null}
    ]};
  const health=sessionHealth(session);
  assert.equal(health.producer.failurePercent,5);
  assert.equal(health.producer.failureIssue,true);
  assert.equal(health.consumers.length,1);
  assert.deepEqual(health.consumers[0].missing,{count:8,total:80,percent:10,issue:true});
  assert.deepEqual(health.consumers[0].nativeDrops,{count:5,total:100,percent:5,issue:true});
  assert.equal(health.consumers[0].weakSignal,true);
});

test('small or unpaired samples have no alarming percentage',()=>{
  const session={producerDevice:null,producerAttempts:0,producerDelivered:0,
    producerFailures:0,producerUnknown:0,consumers:[
      {id:'one',receivedAt:1000,unobserved:0,missing:[],rxAccepted:1,
        nativeDrops:1,rejected:0,rssi:null}
    ]};
  const health=sessionHealth(session);
  assert.equal(health.producer.failurePercent,null);
  assert.equal(health.consumers[0].missing.percent,null);
  assert.equal(health.consumers[0].nativeDrops.issue,false);
});

test('warning thresholds use raw counts before display rounding',()=>{
  const session={producerDevice:'producer',producerAttempts:51,producerDelivered:50,
    producerFailures:1,producerUnknown:0,consumers:[
      {id:'one',receivedAt:1000,unobserved:0,missing:[1,2],rxAccepted:50,
        nativeDrops:1,rejected:0,rssi:null}
    ]};
  const health=sessionHealth(session);
  assert.equal(health.producer.failurePercent,2);
  assert.equal(health.producer.failureIssue,false);
  assert.equal(health.consumers[0].nativeDrops.percent,2);
  assert.equal(health.consumers[0].nativeDrops.issue,false);
  assert.equal(health.consumers[0].missing.percent,4);
  assert.equal(health.consumers[0].missing.issue,false);
});

test('GitHub release metadata maps only matching firmware tags',async()=>{
  let requested;
  const fetcher=async(url)=>{
    requested=url;
    return {ok:true,json:async()=>[
      {tag_name:'firmware-v1.1.7',published_at:'2026-10-13T22:14:49Z',body:'## Changes\n- Telemetry',html_url:githubReleaseUrl('1.1.7')},
      {tag_name:'other-v1.0.0',published_at:'2026-01-01T00:00:00Z',body:'Ignore',html_url:'https://example.org'}
    ]};
  };
  const metadata=await fetchReleaseMetadata(fetcher);
  assert.match(requested,/api\.github\.com\/repos\/nstielau\/digirdu-lights\/releases/);
  assert.deepEqual(metadata.get('1.1.7'),{publishedAt:'2026-10-13T22:14:49Z',notes:'## Changes\n- Telemetry',url:githubReleaseUrl('1.1.7')});
  assert.equal(metadata.size,1);
  assert.equal(githubReleaseUrl('1.1.7'),'https://github.com/nstielau/digirdu-lights/releases/tag/firmware-v1.1.7');
});
