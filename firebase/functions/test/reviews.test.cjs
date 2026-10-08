const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');

const {createReviewHandlers,createReviewLibrary}=require('../reviews.cjs');

function fixture(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'digirdu-reviews-'));
 fs.writeFileSync(path.join(root,'catalog.json'),JSON.stringify({schema_version:1,recordings:[{
  id:'take-one',name:'Take one',duration_ms:1000,label_counts:{yell:1},event_counts:{yell:1}
 }]}));
 fs.mkdirSync(path.join(root,'take-one'));
 fs.writeFileSync(path.join(root,'take-one','bundle.json'),JSON.stringify({duration_ms:1000,labels:[{type:'yell'}]}));
 fs.writeFileSync(path.join(root,'take-one','audio.wav'),'audio');
 return root;
}

test('review library returns catalog and one exact recording',t=>{
 const root=fixture();t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const library=createReviewLibrary(root);
 assert.deepEqual(library.catalog().recordings.map(item=>item.id),['take-one']);
 const recording=library.recording('take-one');
 assert.equal(recording.bundle.duration_ms,1000);
 assert.equal(recording.audio_mime_type,'audio/wav');
 assert.equal(Buffer.from(recording.audio_base64,'base64').toString(),'audio');
 for(const id of ['', '../take','Take One'])assert.throws(()=>library.recording(id),error=>error.status===400);
 assert.throws(()=>library.recording('missing'),error=>error.status===404);
});

test('review handlers authorize before returning protected data',async t=>{
 const root=fixture();t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const library=createReviewLibrary(root);
 let authorizations=0;
 const authorize=async request=>{
  authorizations++;
  if(!request.auth){const error=new Error('unauthenticated');error.status=401;throw error;}
 };
 const handlers=createReviewHandlers(authorize,library);
 await assert.rejects(handlers.catalog({}),error=>error.status===401);
 assert.equal(authorizations,1);
 assert.deepEqual((await handlers.catalog({auth:true})).recordings[0].id,'take-one');
 assert.equal((await handlers.recording({auth:true,data:{id:'take-one'}})).bundle.duration_ms,1000);
 assert.equal(authorizations,3);
});

test('review catalog rejects unsafe generated metadata',t=>{
 const root=fixture();t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.writeFileSync(path.join(root,'catalog.json'),JSON.stringify({schema_version:1,recordings:[{
  id:'../take',name:'Unsafe',duration_ms:1000,label_counts:{},event_counts:{}
 }]}));
 assert.throws(()=>createReviewLibrary(root),/catalog/i);
});
