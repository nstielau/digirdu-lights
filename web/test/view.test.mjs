import {test} from 'node:test';import assert from 'node:assert/strict';import {describeDevice} from '../view.mjs';
test('assigned target never becomes reported version',()=>{
 const v=describeDevice({id:'a',enabled:true,board:'feather',role:'consumer',pin:'2.0.0'}, {version:'3.0.0'});
 assert.equal(v.fields['Reported app'],'Not reported');assert.equal(v.fields['Desired app'],'2.0.0 (pinned)');assert.equal(v.state,'Awaiting report');
});
test('paused reports remain historical',()=>{
 const v=describeDevice({id:'a',enabled:true,paused:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]}}, {version:'2.0.0'});
 assert.equal(v.state,'Updates paused');assert.equal(v.fields['Reported app'],'1.0.0');
});
