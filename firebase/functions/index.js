const {onRequest,onCall,HttpsError}=require('firebase-functions/v2/https');
const {initializeApp}=require('firebase-admin/app');
const {getFirestore}=require('firebase-admin/firestore');
const {getStorage}=require('firebase-admin/storage');
const {pipeline}=require('node:stream/promises');
const {createService}=require('./service.cjs');
initializeApp();
const project=process.env.GCLOUD_PROJECT;
const service=createService(getFirestore());
const options={region:'us-east1',minInstances:0,maxInstances:3,timeoutSeconds:60,memory:'256MiB',
  serviceAccount:`digirdu-functions@${project}.iam.gserviceaccount.com`};
exports.deviceApi=onRequest({...options,cors:false},async(req,res)=>{
  res.set('Cache-Control','no-store');
  try{
    const id=req.get('X-Device-ID'),auth=req.get('Authorization')||'';
    if(!auth.startsWith('Bearer ')){res.status(401).json({error:'unauthorized'});return;}
    const token=auth.slice(7),route=req.path.replace(/^\/device-api\/v1\//,'');
    if(['check-in','report'].includes(route)&&req.method==='POST'){
      if(!req.is('application/json')||(req.rawBody?.length||0)>8192){res.status(400).json({error:'invalid_body'});return;}
      res.json(await service.checkIn(id,token,req.body,route==='report'));return;
    }
    const match=/^artifacts\/([a-f0-9]{64})\/([a-z_]+\.py)$/.exec(route);
    if(match&&req.method==='GET'){
      const file=await service.artifact(id,token,match[1],match[2]);
      const object=getStorage().bucket(`${project}-firmware`).file(file.object);
      res.set('Content-Type','application/octet-stream');res.set('Content-Length',String(file.size));
      await pipeline(object.createReadStream(),res);return;
    }
    res.status(404).json({error:'not_found'});
  }catch(e){
    if(res.headersSent){res.destroy();return;}
    res.status(e.status||500).json({error:e.status?e.message:'unavailable'});
  }
});
function callable(handler){return async request=>{
  try{return await handler(request);}catch(e){
    const codes={400:'invalid-argument',401:'unauthenticated',403:'permission-denied',404:'not-found',409:'failed-precondition',429:'resource-exhausted'};
    throw new HttpsError(codes[e.status]||'internal',e.status?e.message:'Request failed; refresh the dashboard.');
  }
};}
const browser={...options,enforceAppCheck:true,cors:[`https://${project}.firebaseapp.com`,`https://${project}.web.app`]};
exports.fleetOverview=onCall(browser,callable(service.overview));
exports.fleetChange=onCall(browser,callable(service.change));
