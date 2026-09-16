const crypto=require('node:crypto');
const {hash,version,digest,compare,validateManifest,validateReport,compatible}=require('./contract.cjs');
function fail(code,status=400){const e=new Error(code);e.status=status;throw e;}
const idOK=id=>typeof id==='string'&&/^[a-f0-9]{12,32}$/.test(id);
function createService(db,now=()=>Date.now()) {
  async function authenticate(id,token) {
    if(!idOK(id)||typeof token!=='string'||!digest(token))fail('unauthorized',401);
    const snap=await db.doc(`devices/${id}`).get(),d=snap.data();
    if(!d?.enabled||!digest(d.tokenHash)||!crypto.timingSafeEqual(Buffer.from(hash(token),'hex'),Buffer.from(d.tokenHash,'hex')))fail('unauthorized',401);
    return d;
  }
  async function selected(tx,d,report) {
    if(d.paused)return {manifest:null,reason:'paused'};
    const target=d.pin ? {version:d.pin,sequence:d.sequence} :
      (await tx.get(db.doc('channels/stable'))).data();
    if(!target?.version)return {manifest:null,reason:'no_release'};
    const candidates=d.pin ? [(await tx.get(db.doc(`releases/${target.version}`))).data()] :
      (await tx.get(db.collection('releases').limit(200))).docs.map(s=>s.data())
        .filter(r=>r.approved&&!r.revoked).sort((a,b)=>compare(b.manifest.version,a.manifest.version));
    for(const r of candidates){
      if(!r?.approved||r.revoked)continue;
      validateManifest(r.manifest);
      if(compatible(r.manifest,report)){
        if(!d.pin&&compare(r.manifest.version,report.version)<0)return {manifest:null,reason:'already_newer'};
        return {manifest:{...r.manifest,sequence:target.sequence},reason:'selected'};
      }
    }
    return {manifest:null,reason:'incompatible_base_or_board'};
  }
  async function checkIn(id,token,body,reportOnly=false) {
    await authenticate(id,token);
    try{validateReport(body,id);}catch{fail('invalid_report');}
    return db.runTransaction(async tx=>{
      const ref=db.doc(`devices/${id}`),d=(await tx.get(ref)).data();
      // Recheck revocation inside the write transaction.
      if(!d?.enabled||d.tokenHash!==hash(token))fail('unauthorized',401);
      if(d.board!==body.board||d.role!==body.role)fail('identity_mismatch',403);
      const t=now(), prior=d.report;
      const duplicate=prior?.session===body.session&&body.report_sequence<=prior.report_sequence;
      if(prior&&prior.session!==body.session&&(d.recentSessions||[]).includes(body.session))fail('stale_session',409);
      if(!duplicate&&d.lastCheckIn&&t-d.lastCheckIn<1000)fail('rate_limited',429);
      const response=reportOnly?{manifest:null,reason:'reported'}:await selected(tx,d,body);
      if(!duplicate) {
        tx.update(ref,{report:body,lastCheckIn:t,
          recentSessions:[body.session,...(d.recentSessions||[]).filter(s=>s!==body.session)].slice(0,16)});
      }
      return response;
    });
  }
  async function artifact(id,token,bundle,name) {
    const d=await authenticate(id,token);
    if(d.paused||!digest(bundle))fail('not_found',404);
    if(!d.report)fail('incompatible',409);
    const candidates=d.pin ? [(await db.doc(`releases/${d.pin}`).get()).data()] :
      (await db.collection('releases').limit(200).get()).docs.map(s=>s.data())
        .filter(r=>r.approved&&!r.revoked).sort((a,b)=>compare(b.manifest.version,a.manifest.version));
    const r=candidates.find(r=>r?.approved&&!r.revoked&&compatible(r.manifest,d.report));
    if(!r||r.manifest.sha256!==bundle)fail('not_found',404);
    validateManifest(r.manifest);
    const f=r.manifest.files.find(f=>f.name===name);
    if(!f)fail('not_found',404);
    return {object:`releases/${r.manifest.version}/${bundle}/${name}`,size:f.size};
  }
  function user(request){
    const t=request.auth?.token;
    if(!request.auth?.uid||!t?.email_verified||t.firebase?.sign_in_provider!=='google.com'||typeof t.email!=='string')fail('unauthenticated',401);
    if(!request.app)fail('app_check_required',401);
    return {uid:request.auth.uid,email:t.email.trim().toLowerCase()};
  }
  async function admin(request,tx=null) {
    const u=user(request),ref=db.doc(`admins/${hash(u.email)}`);
    const a=tx?await tx.get(ref):await ref.get();
    if(!a.data()?.enabled)fail('forbidden',403);
    return u;
  }
  async function overview(request){
    await admin(request);
    const [devices,releases,channel]=await Promise.all([db.collection('devices').limit(200).get(),
      db.collection('releases').limit(200).get(),db.doc('channels/stable').get()]);
    return {devices:devices.docs.map(s=>{const d=s.data();return {id:s.id,name:d.name,board:d.board,role:d.role,
      enabled:d.enabled,paused:!!d.paused,pin:d.pin||null,report:d.report||null,lastCheckIn:d.lastCheckIn||null};}),
      releases:releases.docs.map(s=>({version:s.id,manifest:s.data().manifest,revoked:!!s.data().revoked})),
      stable:channel.data()||null};
  }
  async function change(request){
    const u=await admin(request),b=request.data;
    if(!b||typeof b!=='object'||!idOK(b.id)||!['latest','pin','pause','resume','disable','rename'].includes(b.action)||
      !/^[a-f0-9-]{36}$/.test(b.requestId)||!Number.isFinite(b.timestamp)||Math.abs(now()-b.timestamp)>60000||
      (b.action==='pin'&&!version(b.version))||(b.action==='rename'&&(typeof b.name!=='string'||!b.name.trim()||b.name.length>80)))fail('invalid_change');
    const fingerprint=hash(JSON.stringify([b.id,b.action,b.version||'',b.name||'']));
    return db.runTransaction(async tx=>{
      await admin(request,tx);
      const audit=db.doc(`audit/${hash(u.uid+':'+b.requestId)}`),old=(await tx.get(audit)).data();
      if(old){if(old.fingerprint!==fingerprint)fail('request_conflict',409);return {ok:true};}
      const ref=db.doc(`devices/${b.id}`),d=(await tx.get(ref)).data();
      if(!d)fail('not_found',404);
      const counter=db.doc('control/sequence'),seq=(await tx.get(counter)).data()?.value||0;
      if(b.action==='pin'){
        const release=(await tx.get(db.doc(`releases/${b.version}`))).data();
        if(!release?.approved||release.revoked)fail('unavailable_release',409);
      }
      let patch={};
      if(b.action==='latest')patch={pin:null,paused:false};
      if(b.action==='pin')patch={pin:b.version,sequence:seq+1,paused:false};
      if(b.action==='pause'||b.action==='resume')patch={paused:b.action==='pause'};
      if(b.action==='disable')patch={enabled:false,paused:true,tokenHash:null};
      if(b.action==='rename')patch={name:b.name.trim()};
      // Switching to latest must issue a sequence above any pinned/failed attempt.
      if(b.action==='latest'){
        const channel=db.doc('channels/stable'),current=(await tx.get(channel)).data();
        if(current?.version)tx.update(channel,{sequence:seq+1});
      }
      if(b.action==='latest'||b.action==='pin')tx.set(counter,{value:seq+1});
      tx.update(ref,patch);
      tx.create(audit,{uid:u.uid,email:u.email,device:b.id,action:b.action,version:b.version||null,
        timestamp:now(),fingerprint});
      return {ok:true};
    });
  }
  return {authenticate,checkIn,artifact,overview,change};
}
module.exports={createService,idOK};
