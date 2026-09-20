import {test} from 'node:test';import assert from 'node:assert/strict';import {describeDevice} from '../view.mjs';
test('assigned target never becomes reported version',()=>{
 const v=describeDevice({id:'a',enabled:true,board:'feather',role:'consumer',pin:'2.0.0'}, {version:'3.0.0'});
 assert.equal(v.fields['Reported app'],'Not reported');assert.equal(v.fields['Desired app'],'2.0.0 (pinned)');assert.equal(v.state,'Awaiting report');
});
test('battery voltage is explicitly historical and unknown is not zero',()=>{
 const device=battery=>describeDevice({id:'a',enabled:true,report:{battery,protocol_receive:[]}},null).fields['Battery terminal (last report)'];
 assert.equal(device({voltage:3.876,status:'measured'}),'3.88 V');
 assert.equal(device({voltage:null,status:'unsupported'}),'Unavailable on this board');
 assert.equal(device({voltage:null,status:'read_error'}),'Reading unavailable');
 assert.equal(device(undefined),'Not reported');
});
test('paused reports remain historical',()=>{
 const v=describeDevice({id:'a',enabled:true,paused:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]}}, {version:'2.0.0'});
 assert.equal(v.state,'Updates paused');assert.equal(v.fields['Reported app'],'1.0.0');
});
